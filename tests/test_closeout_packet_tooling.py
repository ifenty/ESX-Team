"""Closeout and packet tooling friction found on a second project (MITgcm_new_runoff).

B5: issue_candidates accepts a reference inline or as a file path, like doc_contract.
B6: a recovered orphan turn can be selected, and a same-round continuation of the
same retained agent resolves its failed turn. B7/E4: rebind-receipt binds the
passing execution to the prepared closeout in one command, without running the
suite. B8: the closeout draft and the doctor name the expected shape of each
judged field. B10: a stale candidate names the paths that changed.
"""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_framework
import closeout_doctor
import final_verification
import issue_candidates
import loop_lifecycle
import project
import verify
import workflow_policy as policy
import workflow_records as records

TS = '2026-09-28T10:00:00+00:00'
LATER = '2026-09-28T11:00:00+00:00'
SHA = 'a' * 64


class ReferenceArgumentTests(unittest.TestCase):
    def test_reference_is_accepted_inline_or_as_a_file_path(self):
        ref = {'path': f'devel-loop/loop_state/maintenance/{SHA}.json', 'sha256': SHA}
        self.assertEqual(issue_candidates.ref_arg(json.dumps(ref)), ref)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'baseline-ref.json'
            path.write_text(json.dumps(ref, indent=2) + '\n')
            self.assertEqual(issue_candidates.ref_arg(str(path)), ref)

    def test_bad_references_say_what_is_expected(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, 'path of a file containing one'):
            issue_candidates.ref_arg('no-such-file.json')
        with self.assertRaisesRegex(argparse.ArgumentTypeError, '"path" and "sha256"'):
            issue_candidates.ref_arg('{"path": "x"}')
        with self.assertRaisesRegex(argparse.ArgumentTypeError, 'not valid JSON'):
            issue_candidates.ref_arg('{broken')


class StaleCandidateTests(unittest.TestCase):
    def test_stale_paths_names_added_removed_and_changed_files(self):
        captured = {'src/a.py': {'sha256': '1'}, 'src/b.py': {'sha256': '2'}, 'docs/c.md': {'sha256': '3'}}
        current = {'src/a.py': {'sha256': '1'}, 'src/b.py': {'sha256': 'changed'}, 'esx/approvals/note.md': {'sha256': '4'}}
        text = issue_candidates.stale_paths(captured, current)
        self.assertIn('added: esx/approvals/note.md', text)
        self.assertIn('removed: docs/c.md', text)
        self.assertIn('changed: src/b.py', text)
        self.assertNotIn('src/a.py', text)

    def test_long_lists_are_capped_with_a_count(self):
        captured = {}
        current = {f'new/{i:02d}.py': {'sha256': str(i)} for i in range(12)}
        text = issue_candidates.stale_paths(captured, current, limit=3)
        self.assertIn('new/00.py, new/01.py, new/02.py (+9 more)', text)

    def test_check_current_error_carries_the_changed_path(self):
        record = {'files': {'src/a.py': {'sha256': '1'}}, 'scope': {'inventory': True, 'extra': []}}
        with mock.patch.object(issue_candidates, 'load', return_value=record), \
                mock.patch.object(issue_candidates, 'measure',
                                  return_value={'src/a.py': {'sha256': '1'}, 'esx/approvals/note.md': {'sha256': '2'}}):
            with self.assertRaisesRegex(ValueError, r'stale.*added: esx/approvals/note\.md'):
                issue_candidates.check_current('.', {}, 'X-1')
        with mock.patch.object(issue_candidates, 'load', return_value=record), \
                mock.patch.object(issue_candidates, 'measure', return_value=dict(record['files'])):
            self.assertIs(issue_candidates.check_current('.', {}, 'X-1'), record)


class SelectionTests(unittest.TestCase):
    start = {'id': 'X-1', 'title': 'selection', 'timestamp': TS, 'iteration': 1,
             'maintenance': {'baseline': {'sha256': 'b'}}}

    @staticmethod
    def completion(agent, event, ts, round_number):
        return {'agent_type': 'bob', 'agent_id': agent, 'event_id': event, 'ts': ts, 'status': 'completed',
                'issue_id': 'X-1', 'correction_round': round_number,
                'footer': {'agent': 'bob', 'issue_id': 'X-1', 'correction_round': round_number,
                           'iteration_timestamp': TS}}

    @staticmethod
    def failure(agent, event, ts, round_number, **extra):
        return dict({'agent_type': 'bob', 'agent_id': agent, 'event_id': event, 'ts': ts, 'status': 'failed',
                     'issue_id': 'X-1', 'correction_round': round_number, 'error': 'timeout'}, **extra)

    def test_recovered_orphan_without_a_round_can_be_selected(self):
        orphan = self.failure('B1', 'E0', LATER, None, recovered=True, execution_phase='recovered_orphan',
                              error='orphaned turn recovered: dispatcher crashed')
        selection = dict(agent='bob', dispatch_id='B1', dispatch_event_id='E0', correction_round=None)
        imported = records.import_completion(self.start, [orphan], selection)
        self.assertEqual(imported['status'], 'failed')
        self.assertEqual(imported['dispatch_event_id'], 'E0')

    def test_an_ordinary_failed_turn_still_needs_its_round(self):
        failed = self.failure('B1', 'E1', LATER, None)  # not recovered: a missing round stays an error
        selection = dict(agent='bob', dispatch_id='B1', dispatch_event_id='E1', correction_round=None)
        with self.assertRaisesRegex(ValueError, 'correction round mismatch or absent'):
            records.import_completion(self.start, [failed], selection)
        orphan = self.failure('B1', 'E2', LATER, None, recovered=True)
        wrong = dict(agent='bob', dispatch_id='B1', dispatch_event_id='E2', correction_round=1)
        with self.assertRaisesRegex(ValueError, 'correction round mismatch or absent'):
            records.import_completion(self.start, [orphan], wrong)

    def done(self, *events):
        return {'id': 'X-1', 'timestamp': TS,
                'subagents': {'bob': [{'dispatch_id': e['agent_id'], 'dispatch_event_id': e['event_id']} for e in events]}}

    def test_same_round_continuation_of_the_same_agent_resolves_a_failed_turn(self):
        failed = self.failure('B1', 'E1', LATER, 0)                      # e.g. the turn limit
        resumed = self.completion('B1', 'E2', '2026-09-28T12:00:00+00:00', 0)
        log = [failed, resumed]
        self.assertTrue(policy.resolved_dispatch(failed, log, self.done(failed, resumed)))
        # The continuation must itself be referenced, completed and later in the log.
        self.assertFalse(policy.resolved_dispatch(failed, log, self.done(failed)))
        self.assertFalse(policy.resolved_dispatch(failed, [resumed, failed], self.done(failed, resumed)))

    def test_later_round_continuation_and_recovered_orphan_resolve(self):
        failed = self.failure('B1', 'E1', LATER, 1)
        later = self.completion('B1', 'E3', '2026-09-28T13:00:00+00:00', 2)
        self.assertTrue(policy.resolved_dispatch(failed, [failed, later], self.done(failed, later)))
        orphan = self.failure('B1', 'E0', LATER, None, recovered=True)
        first = self.completion('B1', 'E2', '2026-09-28T12:00:00+00:00', 0)
        self.assertTrue(policy.resolved_dispatch(orphan, [orphan, first], self.done(orphan, first)))

    def test_an_earlier_round_or_another_agent_does_not_resolve(self):
        failed = self.failure('B1', 'E1', LATER, 2)
        earlier_round = self.completion('B1', 'E2', '2026-09-28T12:00:00+00:00', 1)
        self.assertFalse(policy.resolved_dispatch(failed, [failed, earlier_round], self.done(failed, earlier_round)))
        other = self.completion('B2', 'E3', '2026-09-28T12:00:00+00:00', 2)
        self.assertFalse(policy.resolved_dispatch(failed, [failed, other], self.done(failed, other)))

    def test_draft_needs_no_replacement_for_a_same_round_continuation(self):
        log = [self.failure('B1', 'E1', LATER, 0), self.completion('B1', 'E2', '2026-09-28T12:00:00+00:00', 0)]
        selections = [dict(agent='bob', dispatch_id='B1', dispatch_event_id='E1', correction_round=0),
                      dict(agent='bob', dispatch_id='B1', dispatch_event_id='E2', correction_round=0)]
        draft = records.prepare_done(self.start, log, selections)
        self.assertEqual((draft.get('agent_continuity') or {}).get('replacements', []), [])


class SkeletonAndMessageTests(unittest.TestCase):
    def test_draft_names_the_shape_of_every_judged_field(self):
        start = {'id': 'X-1', 'title': 'shapes', 'timestamp': TS, 'iteration': 1,
                 'maintenance': {'baseline': {'sha256': 'b'}}}
        shapes = records.prepare_done(start, [], [])['preparation']['shapes']
        for key in ('scope_decisions[]', 'milestone', 'git', 'communication', 'verification.structural',
                    'agent_continuity.replacements[]', 'preparation'):
            self.assertIn(key, shapes)
        self.assertEqual(shapes['scope_decisions[]']['evidence_refs'],
                         ['project-relative path string, not a {path, sha256} object'])
        self.assertIn('rebind-receipt', shapes['verification.scientific / verification.receipt'])
        self.assertIn('delete this whole object', shapes['preparation'])

    def test_object_evidence_refs_get_a_specific_message(self):
        decision = {'classification': 'separate_existing', 'status': 'open', 'issue_id': 'X-2',
                    'evidence_refs': [{'path': 'a', 'sha256': SHA}]}
        errors = policy.validate_scope_decisions([decision])
        self.assertEqual(len(errors), 1)
        self.assertIn('must be project-relative path strings', errors[0])
        decision['evidence_refs'] = []
        self.assertIn('non-empty list of project-relative path strings', policy.validate_scope_decisions([decision])[0])
        decision['evidence_refs'] = ['devel-loop/loop_state/review.json']
        self.assertEqual(policy.validate_scope_decisions([decision]), [])

    def test_doctor_ordering_points_to_rebind_receipt(self):
        self.assertIn('loop_lifecycle.py rebind-receipt', closeout_doctor.ORDERING)
        self.assertIn('issue-done.json', closeout_doctor.ORDERING)
        self.assertIn('without --fresh', closeout_doctor.ORDERING)


class RebindReceiptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_rebind_binds_the_execution_to_the_closeout_without_running_the_suite(self):
        done = self.fixture.complete()
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')
        first = dict(done['verification']['receipt'])
        # Filling a signed closeout field after the receipt makes it stale ...
        done['scope_decisions'] = [{'classification': 'separate_new', 'issue_id': 'SAMPLE-002', 'status': 'open',
                                    'evidence_refs': ['review found an untested boundary']}]
        self.fixture.save_done(done)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.fixture.gate.check_done()
        stale = [row for row in closeout_doctor.diagnose(self.fixture.gate)['findings']
                 if row['code'] == 'RECEIPT_SIGNATURE_STALE']
        self.assertEqual(len(stale), 1)
        self.assertIn('loop_lifecycle.py rebind-receipt', stale[0]['recovery'])
        # ... and one command repairs it; the scientific suite must not run.
        with mock.patch.object(verify, 'run', side_effect=AssertionError('the suite must not run')):
            result = loop_lifecycle.rebind_receipt(self.root)
        self.assertEqual(result['status'], 'rebound')
        self.assertTrue(result['reissued'])
        self.assertFalse(result['executed'])
        self.assertNotEqual(result['receipt'], first)
        saved = json.loads((self.root / project.STATE / 'issue-done.json').read_text())
        self.assertEqual(saved['verification']['receipt'], result['receipt'])
        receipt = json.loads((self.root / result['receipt']['path']).read_text())
        self.assertFalse(receipt['executed'])
        self.assertEqual(receipt['identity']['review_signature'], final_verification.review_signature(saved))
        self.assertEqual(closeout_doctor.diagnose(self.fixture.gate)['status'], 'ready')
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')

    def test_rebind_is_a_no_op_reissue_when_the_receipt_already_matches(self):
        self.fixture.complete()
        result = loop_lifecycle.rebind_receipt(self.root)
        self.assertEqual(result['status'], 'rebound')
        self.assertFalse(result['reissued'])

    def test_rebind_refuses_a_closeout_with_pending_preparation(self):
        done = self.fixture.complete()
        done['scope_decisions'] = [{'classification': 'separate_new', 'issue_id': 'SAMPLE-002', 'status': 'open',
                                    'evidence_refs': ['x']}]
        done['preparation'] = {'pending': ['scope decisions and remaining blockers']}
        self.fixture.save_done(done)
        with mock.patch.object(verify, 'run', side_effect=AssertionError('the suite must not run')):
            with self.assertRaisesRegex(ValueError, 'pending preparation'):
                loop_lifecycle.rebind_receipt(self.root)

    def test_rebind_names_a_missing_final_owner(self):
        done = self.fixture.complete()
        done['scope_decisions'] = [{'classification': 'separate_new', 'issue_id': 'SAMPLE-002', 'status': 'open',
                                    'evidence_refs': ['x']}]
        done['verification'].pop('final_owner', None)
        done['workflow'] = dict(done['workflow'])
        done['workflow'].pop('final_verify_owner', None)
        self.fixture.save_done(done)
        with self.assertRaisesRegex(ValueError, 'names no final verification owner'):
            loop_lifecycle.rebind_receipt(self.root)

    def test_rebind_refuses_when_no_receipt_exists(self):
        self.fixture.complete()
        (self.root / project.STATE / 'final-verification' / 'current.json').unlink()
        with self.assertRaises(ValueError):
            final_verification.rebind(self.root, json.loads(
                (self.root / project.STATE / 'issue-done.json').read_text()), 'arch')


if __name__ == '__main__':
    unittest.main()
