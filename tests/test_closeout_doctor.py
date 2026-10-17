"""Closeout requirements are reported together, and a reiteration closeout is drafted.

TEAM-CLOSEOUT-DOCTOR-001: `loop_gate.py --closeout-doctor` lists every unmet
closeout requirement in one read-only run and names the review_signature
ordering constraint. TEAM-REITERATION-CLOSEOUT-001: prepare-done locates the
prior closeout, drafts replacement dispositions for unresolved failed turns
without resolving them, and `separate_new` records review-discovered issues.
Strict --check-done behaviour is unchanged throughout.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_framework
import closeout_doctor
import final_verification
import project
import workflow_policy as policy
import workflow_records as records

TS = '2026-09-28T10:00:00+00:00'
LATER = '2026-09-28T11:00:00+00:00'


class CloseoutDoctorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def doctor_cli(self):
        return subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_gate.py'), '--closeout-doctor'],
                              cwd=self.root.parent, capture_output=True, text=True)

    def test_several_omitted_requirements_are_reported_in_one_invocation(self):
        done = self.fixture.complete(qualify=False)  # no scientific evidence and no receipt
        done['git'] = {}
        done['agent_continuity']['bob'] = []
        done['scope_decisions'] = [{'classification': 'found_by_review', 'status': 'open', 'evidence_refs': ['x']}]
        self.fixture.save_done(done)
        before = (self.root / project.STATE / 'issue-done.json').read_bytes()
        run = self.doctor_cli()
        self.assertEqual(run.returncode, 1, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['status'], 'blocked')
        codes = {row['code'] for row in result['findings']}
        for code in ('GIT_DISPOSITION', 'CONTINUITY_IDENTITIES', 'SCOPE_DECISION_INVALID', 'VERIFICATION_REFERENCE_MISSING'):
            self.assertIn(code, codes)
        fields = {row['field'] for row in result['findings'] if row['code'] == 'VERIFICATION_REFERENCE_MISSING'}
        self.assertEqual(fields, {'verification.scientific', 'verification.receipt'})
        identity = next(row for row in result['findings'] if row['code'] == 'CONTINUITY_IDENTITIES')
        self.assertIn('dispatch_ids already in subagents.bob', identity['recovery'])
        self.assertIn('bob-runtime-1', identity['recovery'])
        # The review_signature dependency and every field it covers are named.
        notice = result['review_signature']
        self.assertEqual(notice['fields'], list(final_verification.REVIEW_SIGNATURE_FIELDS))
        self.assertIn('Finalize every signed field before taking the final verification receipt', notice['ordering'])
        for field in final_verification.REVIEW_SIGNATURE_FIELDS:
            self.assertIn(field, run.stdout)
        # Read-only, and the strict gate still stops at its first failure.
        self.assertEqual((self.root / project.STATE / 'issue-done.json').read_bytes(), before)
        self.assertFalse((self.root / project.STATE / 'loop_history.jsonl').exists())
        self.assertTrue(result['strict_gate'].startswith('refused:'))
        with self.assertRaises(ValueError):
            self.fixture.gate.check_done()

    def test_ready_closeout_and_a_receipt_invalidated_by_a_later_signed_edit(self):
        done = self.fixture.complete()
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')
        result = closeout_doctor.diagnose(self.fixture.gate)
        self.assertEqual(result['status'], 'ready', result['findings'])
        self.assertEqual(result['unmet'], 0)
        # A bookkeeping edit to a signed field after the receipt voids it ...
        done['scope_decisions'] = [{'classification': 'separate_new', 'issue_id': 'SAMPLE-002', 'status': 'open',
                                    'evidence_refs': ['review found an untested boundary']}]
        self.fixture.save_done(done)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.fixture.gate.check_done()
        result = closeout_doctor.diagnose(self.fixture.gate)
        self.assertEqual(result['status'], 'blocked')
        stale = [row for row in result['findings'] if row['code'] == 'RECEIPT_SIGNATURE_STALE']
        self.assertEqual(len(stale), 1, result['findings'])
        self.assertIn('scope_decisions', stale[0]['observed'])
        self.assertIn('without --fresh', result['review_signature']['ordering'])
        # ... and the documented recovery rebinds the unchanged execution.
        rerun = final_verification.run(self.root, done, 'arch')
        self.assertEqual(rerun['status'], 'REUSED EVIDENCE')
        done['verification'].update(receipt=rerun['receipt'], scientific=rerun['scientific'])
        self.fixture.save_done(done)
        self.assertEqual(closeout_doctor.diagnose(self.fixture.gate)['status'], 'ready')
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')

    def test_strict_messages_name_the_wanted_values(self):
        done = self.fixture.complete(qualify=False)
        with self.assertRaises(ValueError) as caught:
            self.fixture.gate.check_done()
        for key in ('structural', 'scientific', 'receipt'):
            self.assertIn(f"'{key}'", str(caught.exception))
        self.assertIn('verification reference is required', str(caught.exception))
        done['agent_continuity']['bob'] = []
        self.fixture.save_done(done)
        with self.assertRaisesRegex(ValueError, r"dispatch_ids already in subagents\.bob.*bob-runtime-1"):
            self.fixture.gate.check_done()


class ReiterationCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.start = {'id': 'X-1', 'title': 'reiteration', 'timestamp': LATER, 'iteration': 2,
                      'maintenance': {'baseline': {'sha256': 'b'}}}

    @staticmethod
    def completion(role, agent, event, ts, round_number=0, iteration=LATER):
        return {'agent_type': role, 'agent_id': agent, 'event_id': event, 'ts': ts, 'status': 'completed',
                'issue_id': 'X-1', 'correction_round': round_number,
                'footer': {'agent': role, 'issue_id': 'X-1', 'correction_round': round_number,
                           'iteration_timestamp': iteration}}

    @staticmethod
    def failure(role, agent, event, ts, round_number=0):
        return {'agent_type': role, 'agent_id': agent, 'event_id': event, 'ts': ts, 'status': 'failed',
                'issue_id': 'X-1', 'correction_round': round_number, 'error': 'stale orientation receipt'}

    def test_replacement_skeleton_is_prefilled_and_still_refused_until_judged(self):
        failed = self.failure('bob', 'B1', 'E1', LATER)
        records_ = [failed, self.completion('bob', 'B2', 'E2', '2026-09-28T12:00:00+00:00')]
        selections = [dict(agent='bob', dispatch_id='B1', dispatch_event_id='E1', correction_round=0),
                      dict(agent='bob', dispatch_id='B2', dispatch_event_id='E2', correction_round=0)]
        draft = records.prepare_done(self.start, records_, selections)
        replacements = draft['agent_continuity']['replacements']
        self.assertEqual(len(replacements), 1)
        entry = replacements[0]
        self.assertEqual((entry['role'], entry['old_id'], entry['new_id']), ('bob', 'B1', 'B2'))
        self.assertEqual((entry['reason'], entry['evidence_refs']), ('', []))
        self.assertTrue(any('agent_continuity.replacements' in p for p in draft['preparation']['pending']))
        # Empty judgment fields are refused by the same validator every gate uses.
        self.assertFalse(policy.resolved_dispatch(failed, records_, draft))
        entry['reason'] = 'Original implementer failed on a stale orientation receipt; replaced.'
        self.assertFalse(policy.resolved_dispatch(failed, records_, draft))
        entry['evidence_refs'] = ['devel-loop/loop_state/dispatch_log.jsonl#E1']
        self.assertTrue(policy.resolved_dispatch(failed, records_, draft))

    def test_same_agent_continuation_needs_no_replacement(self):
        records_ = [self.failure('bob', 'B1', 'E1', LATER),
                    self.completion('bob', 'B1', 'E2', '2026-09-28T12:00:00+00:00', 1)]
        selections = [dict(agent='bob', dispatch_id='B1', dispatch_event_id='E1', correction_round=0),
                      dict(agent='bob', dispatch_id='B1', dispatch_event_id='E2', correction_round=1)]
        draft = records.prepare_done(self.start, records_, selections)
        self.assertEqual((draft.get('agent_continuity') or {}).get('replacements', []), [])

    def test_failed_reviewer_gets_a_skeleton_even_when_unselected(self):
        records_ = [self.failure('richard', 'R1', 'E1', LATER),
                    self.completion('richard', 'R2', 'E2', '2026-09-28T12:00:00+00:00')]
        draft = records.prepare_done(self.start, records_, [])
        entry, = draft['agent_continuity']['replacements']
        self.assertEqual((entry['role'], entry['old_id'], entry['new_id'], entry['reason']), ('richard', 'R1', 'R2', ''))

    def write_state(self, closeouts, history):
        state = self.root / project.STATE
        (state / 'closed').mkdir(parents=True)
        for name, record in closeouts.items():
            (state / 'closed' / name).write_text(json.dumps(record))
        (state / 'loop_history.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in history))
        return state

    def test_prior_closeout_is_located_automatically(self):
        old = self.failure('bob', 'B0', 'E0', TS)
        prior = {'id': 'X-1', 'timestamp': TS, 'outcome': 'partial', 'maintenance': self.start['maintenance'],
                 'subagents': {'bob': [dict(dispatch_id='B0', dispatch_event_id='E0', correction_round=0)]}}
        state = self.write_state({
            'issue-done-a.json': prior,
            'issue-done-b.json': dict(prior, timestamp='2026-09-28T10:30:00+00:00'),  # never accepted
            'issue-done-c.json': dict(prior, maintenance={'baseline': {'sha256': 'other'}}, timestamp='2026-09-28T10:45:00+00:00'),
            'issue-done-d.json': dict(prior, id='X-2')},
            [{'id': 'X-1', 'timestamp': TS}, {'id': 'X-1', 'timestamp': '2026-09-28T10:45:00+00:00'},
             {'id': 'X-2', 'timestamp': TS}])
        self.assertEqual(records.locate_prior(self.root, self.start), state / 'closed' / 'issue-done-a.json')
        self.assertIsNone(records.locate_prior(self.root, dict(self.start, id='X-3')))
        current = self.completion('bob', 'B1', 'E1', '2026-09-28T12:00:00+00:00')
        (state / 'dispatch_log.jsonl').write_text(json.dumps(old) + '\n' + json.dumps(current) + '\n')
        (state / 'issue-start.json').write_text(json.dumps(self.start))
        # Selecting the pre-iteration attempt used to demand --prior; now the
        # located prior retains it and the draft names where it came from.
        selection = self.root / 'select.json'
        selection.write_text(json.dumps([dict(agent='bob', dispatch_id='B0', dispatch_event_id='E0', correction_round=0),
                                         dict(agent='bob', dispatch_id='B1', dispatch_event_id='E1', correction_round=0)]))
        out = self.root / 'draft.json'
        with contextlib.redirect_stdout(io.StringIO()):
            code = records.main(['--root', str(self.root), 'prepare-done', '--select', str(selection), '--output', 'draft.json'])
        self.assertEqual(code, 0)
        draft = json.loads(out.read_text())
        # 1.6.6 adds the earlier completions ('completions') next to the located path.
        prior = draft['preparation']['prior']
        self.assertEqual({k: prior[k] for k in ('path', 'located')},
                         {'path': f'{project.STATE}/closed/issue-done-a.json', 'located': 'automatic'})
        self.assertEqual([c['dispatch_event_id'] for c in prior['completions']], ['E0'])
        self.assertEqual([e['dispatch_event_id'] for e in draft['subagents']['bob']], ['E0', 'E1'])
        self.assertEqual(draft['agent_continuity']['replacements'][0]['old_id'], 'B0')
        self.assertEqual(draft['agent_continuity']['replacements'][0]['new_id'], 'B1')
        # Opting out restores the explicit behaviour, including its rejection.
        with self.assertRaisesRegex(ValueError, 'predates this iteration'):
            records.prepare_done(self.start, [old, current], json.loads(selection.read_text()))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(records.main(['--root', str(self.root), 'prepare-done', '--no-prior',
                                           '--select', str(selection)]), 1)
        self.assertIn('selection_scope', err.getvalue())


class PolicyMessageTests(unittest.TestCase):
    def test_separate_new_requires_an_issue_id_in_both_directions(self):
        decision = {'classification': 'separate_new', 'status': 'open', 'evidence_refs': ['review report']}
        self.assertEqual(policy.validate_scope_decisions([dict(decision, issue_id='X-9')], completed=True), [])
        errors = policy.validate_scope_decisions([decision], completed=True)
        self.assertEqual(len(errors), 1)
        self.assertIn('needs the separate issue_id', errors[0])
        self.assertTrue(policy.validate_scope_decisions([dict(decision, classification='separate_existing')]))
        errors = policy.validate_scope_decisions([dict(decision, classification='filed', issue_id='X-9')])
        self.assertIn('separate_new', errors[0])

    def test_waiving_a_failed_review_is_explained_not_silently_repeated(self):
        done = {'id': 'X-1', 'timestamp': TS, 'outcome': 'completed',
                'workflow': {'minimum_reviewers': 1},
                'subagents': {'richard': [{'dispatch_id': 'R1', 'dispatch_event_id': 'E1', 'waived': True}]}}
        records_ = [{'agent_type': 'richard', 'agent_id': 'R1', 'event_id': 'E1', 'issue_id': 'X-1',
                     'status': 'failed', 'iteration_timestamp': TS}]
        errors = policy.validate_reviews(done, records_, 'a' * 64)
        message = next(e for e in errors if 'missing from subagents.richard' in e)
        self.assertIn('waiving is not a valid disposition', message)
        self.assertIn('agent_continuity.replacements', message)
        done['subagents']['richard'] = []
        message = next(e for e in policy.validate_reviews(done, records_, 'a' * 64) if 'missing from' in e)
        self.assertNotIn('waiv', message)

    def test_verification_message_names_all_three_keys(self):
        for kind in ('scientific_change', 'documentation'):
            message = policy.verification_reference_message(kind, 'structural')
            for key in ('structural', 'scientific', 'receipt'):
                self.assertIn(f"'{key}'", message)


if __name__ == '__main__':
    unittest.main()
