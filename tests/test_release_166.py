"""1.6.6: closeout and record tooling.

A: prepare-done --packet and prior-iteration history. B: closeout record helpers and
declared parallel reviewers. C: early kind-amendment notices. D: documentation_paths.
E: agent_runtime turn-status. F: final_verification reuse diagnostics.
Offline, synthetic deployment fixtures.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_framework
import agent_runtime
import closeout_doctor
import doc_contract as maintenance
import final_verification
import hooks
import issue_candidates
import loop_gate
import loop_lifecycle
import project
import verify
import workflow_handoff as handoff
import workflow_policy as policy
import workflow_records as records

TS = '2026-10-10T10:00:00+00:00'
LATER = '2026-10-10T11:00:00+00:00'
SOON = '2026-10-10T12:00:00+00:00'
TARGETS = ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>']
BRIEF = dict(outcome='Qualify periodic diffusion', constraints=['mass conservation'], acceptance_tests=['Fourier solution'])


class Deployment(unittest.TestCase):
    """A disposable ESX project whose hook footers carry their correction round."""

    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        real = hooks.capture

        def capture(root, event):
            message = event['last_assistant_message']
            body = json.loads(message.split('```json\n', 1)[1].rsplit('\n```', 1)[0])
            body.setdefault('correction_round', 0)
            return real(root, dict(event, last_assistant_message='```json\n' + json.dumps(body) + '\n```'))
        patcher = mock.patch.object(hooks, 'capture', capture)
        patcher.start()
        self.addCleanup(patcher.stop)

    def configure(self, **changes):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg.update(changes)
        path.write_text(json.dumps(cfg, indent=2) + '\n')

    def reviewed(self, kind='scientific_change'):
        if kind != 'scientific_change':
            self.fixture.prepare = lambda risks=(): test_framework.FrameworkTests.prepare(self.fixture, kind=kind, risks=risks)
        done = self.fixture.complete(qualify=False)
        self.start = self.fixture.start
        return done

    def log(self):
        return records.read_jsonl(self.root / project.STATE / 'dispatch_log.jsonl')

    def selections(self, events=None):
        return [dict(agent=e['agent_type'], dispatch_id=e['agent_id'], dispatch_event_id=e['event_id'], correction_round=0)
                for e in (self.log() if events is None else events)]

    def review(self, agent, report=None, candidate_signature=None):
        """A fresh, fully navigated and independently checked reviewer completion."""
        base = self.start['maintenance']['baseline']
        with contextlib.redirect_stderr(io.StringIO()):
            nav = maintenance.navigate(self.root, self.fixture.issue, base, 'richard', 'docs/code_map.md#pipeline', TARGETS,
                                       ['docs/model_contract.md'],
                                       'Read the periodic owner and exact Fourier oracle to assess conservation and stability.')
        evidence = verify.run(self.root, 'focused', agent, fresh=True)['evidence']
        footer = {'agent': 'richard', 'issue_id': self.fixture.issue, 'iteration_timestamp': self.start['timestamp'],
                  'orientation': nav, 'candidate_signature': candidate_signature or project.source_signature(self.root),
                  'verdict': 'APPROVE', 'must_fix': [],
                  'independent_check': {'cmd': 'python3 tests/check_diffusion.py', 'exit': 0, 'executed': True, 'evidence': evidence},
                  'documentation_review': {'report': report, 'status': 'confirmed',
                                           'notes': 'Checked the mapped owner and Fourier oracle contracts against the candidate.'}}
        return hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': agent, 'session_id': 'synthetic-session',
                                         'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})

    def packet(self, done, selections=None, events=None, **extra):
        events = self.log() if events is None else events
        return handoff.assemble(self.root, self.start, events, self.selections(events) if selections is None else selections,
                                done['candidate'], done['maintenance']['documentation'], BRIEF, **extra)


class PacketTests(Deployment):
    def test_prepare_done_with_a_packet_leaves_only_judgments_pending(self):
        done = self.reviewed()
        packet = self.packet(done)
        draft = records.prepare_done(self.start, self.log(), self.selections(), packet=packet)
        self.assertEqual(draft['candidate'], packet['candidate'])
        self.assertEqual(draft['map_delta'], packet['map_delta'])
        self.assertEqual(draft['maintenance']['documentation'], packet['maintenance']['documentation'])
        self.assertEqual(draft['maintenance']['orientation'], packet['maintenance']['orientation'])
        self.assertEqual(draft['maintenance']['baseline'], self.start['maintenance']['baseline'])
        self.assertEqual(draft['agent_continuity']['bob'], ['bob-runtime-1'])
        self.assertEqual(draft['agent_continuity']['richard'], ['richard-runtime-1'])
        pending = ' | '.join(draft['preparation']['pending'])
        for judgment in ('outcome, summary, tests_status', 'scope decisions', 'milestone, lesson and rule',
                         'git and communication', 'verification evidence'):
            self.assertIn(judgment, pending)
        for structural in ('candidate', 'map_delta', 'documentation', 'orientation', 'continuity', 'independent_check'):
            self.assertNotIn(structural, pending)
        self.assertEqual(len(draft['preparation']['pending']), 5)

    def test_a_draft_from_a_packet_passes_the_doctor_once_judgments_are_filled(self):
        done = self.reviewed()
        packet = self.packet(done)
        run = final_verification.run(self.root, packet, 'arch')
        draft = records.prepare_done(self.start, self.log(), self.selections(), packet=packet)
        # Unfilled, the doctor lists the missing judgment next to the other open items in one call.
        self.fixture.save_done(draft)
        codes = {row['code'] for row in closeout_doctor.diagnose(self.fixture.gate)['findings']}
        self.assertIn('OUTCOME_MISSING', codes)
        self.assertGreater(len(codes), 1)
        for structural in ('CANDIDATE_INVALID', 'CONTINUITY_IDENTITIES', 'DOCUMENTATION_INVALID', 'ORIENTATION_INVALID',
                           'COMPLETION_MISSING', 'REPLACEMENT_UNEXPLAINED'):
            self.assertNotIn(structural, codes)
        draft.pop('preparation')
        draft.update(outcome='completed', summary='Qualified the synthetic stencil from a review packet.', tests_status='passing',
                     verification=dict(done['verification'], scientific=run['scientific'], receipt=run['receipt']))
        self.fixture.save_done(draft)
        loop_lifecycle.rebind_receipt(self.root)
        result = closeout_doctor.diagnose(self.fixture.gate)
        self.assertEqual(result['status'], 'ready', result['findings'])

    def test_a_packet_of_another_iteration_or_baseline_is_refused(self):
        done = self.reviewed()
        packet = self.packet(done)
        with self.assertRaisesRegex(ValueError, 'another issue or iteration'):
            records.prepare_done(self.start, self.log(), self.selections(), packet=dict(packet, timestamp=TS))
        other = json.loads(json.dumps(packet))
        other['maintenance']['baseline'] = {'path': 'x', 'sha256': 'f' * 64}
        with self.assertRaisesRegex(ValueError, 'different issue baseline'):
            records.prepare_done(self.start, self.log(), self.selections(), packet=other)

    def test_command_line_packet_option(self):
        done = self.reviewed()
        packet = self.packet(done)
        state = self.root / project.STATE
        (state / 'p.json').write_text(json.dumps(packet))
        (state / 's.json').write_text(json.dumps(self.selections()))
        run = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/workflow_records.py'), 'prepare-done',
                              '--select', 'devel-loop/loop_state/s.json', '--packet', 'devel-loop/loop_state/p.json',
                              '--no-prior'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['candidate'], packet['candidate'])

    def test_loop_lifecycle_prepare_done_lists_the_stable_identities(self):
        done = self.reviewed(kind='documentation')
        packet = self.packet(done)
        self.assertNotIn('bob', packet.get('agent_continuity') or {})
        loop_lifecycle.prepare_done(self.root, packet, {}, {
            'summary': 'Documented the synthetic stencil without changing any scientific file.', 'tests_status': 'passing',
            'git': {'committed': False, 'reason': 'Not committed; the synthetic task creates no commits.'},
            'communication': {'status': 'disabled', 'detail': 'Synthetic tests send no external messages.'}})
        prepared = json.loads((self.root / project.STATE / 'issue-done.json').read_text())
        self.assertEqual(prepared['agent_continuity']['bob'], ['bob-runtime-1'])
        self.assertEqual(prepared['agent_continuity']['richard'], ['richard-runtime-1'])


class PriorIterationTests(unittest.TestCase):
    """What the gate needs visible from an earlier iteration, found by reading it (item A.2)."""
    SIG_OLD, SIG_NEW = 'a' * 64, 'b' * 64
    start = {'id': 'X-1', 'title': 'prior', 'timestamp': LATER, 'iteration': 2,
             'maintenance': {'baseline': {'sha256': 'b'}},
             'workflow': {'kind': 'scientific_change', 'final_verify_owner': 'arch'}}

    @staticmethod
    def event(agent, role, event_id, iteration, ts, status='completed', signature=None, round_number=0):
        footer = {'agent': role, 'issue_id': 'X-1', 'iteration_timestamp': iteration, 'correction_round': round_number,
                  'orientation': {'ok': True}, 'candidate_signature': signature, 'verdict': 'APPROVE', 'must_fix': [],
                  'independent_check': {'cmd': 'check', 'exit': 0, 'executed': True}}
        row = {'agent_type': role, 'agent_id': agent, 'event_id': event_id, 'ts': ts, 'status': status,
               'issue_id': 'X-1', 'iteration_timestamp': iteration, 'correction_round': round_number}
        if status == 'completed':
            row['footer'] = footer
        else:
            row['error'] = 'timeout'
        return row

    def log(self):
        return [self.event('B1', 'bob', 'EB0', TS, TS, signature=None),
                self.event('R1', 'richard', 'ER0', TS, TS, signature=self.SIG_OLD),
                self.event('R2', 'richard', 'ER1', TS, TS, status='failed'),
                self.event('R3', 'richard', 'ER2', LATER, SOON, signature=self.SIG_NEW)]

    def prior(self):
        return {'id': 'X-1', 'timestamp': TS, 'maintenance': {'baseline': {'sha256': 'b'}}, 'subagents': {
            'bob': [{'dispatch_id': 'B1', 'dispatch_event_id': 'EB0'}],
            'richard': [{'dispatch_id': 'R1', 'dispatch_event_id': 'ER0'},
                        {'dispatch_id': 'R2', 'dispatch_event_id': 'ER1', 'status': 'failed', 'correction_round': 0}]}}

    def draft(self):
        selections = [dict(agent='richard', dispatch_id='R3', dispatch_event_id='ER2', correction_round=0)]
        return records.prepare_done(self.start, self.log(), selections, self.prior())

    def test_prior_reviewer_approval_is_history_and_not_a_current_subagent(self):
        draft = self.draft()
        self.assertEqual([e['dispatch_id'] for e in draft['subagents']['richard']], ['R2', 'R3'])
        self.assertNotIn('carried_from_prior_iteration', draft['subagents']['richard'][1])
        by_event = {row['dispatch_event_id']: row for row in draft['preparation']['prior']['completions']}
        self.assertEqual(by_event['ER0']['disposition'], 'history_only')
        self.assertEqual(by_event['ER0']['candidate_signature'], self.SIG_OLD)
        self.assertEqual(by_event['ER0']['iteration_timestamp'], TS)

    def test_what_the_gate_needs_stays_visible_and_is_marked(self):
        draft = self.draft()
        failed = draft['subagents']['richard'][0]
        self.assertEqual((failed['dispatch_id'], failed['status']), ('R2', 'failed'))
        self.assertTrue(failed['carried_from_prior_iteration'])
        self.assertTrue(draft['subagents']['bob'][0]['carried_from_prior_iteration'])
        by_event = {row['dispatch_event_id']: row for row in draft['preparation']['prior']['completions']}
        self.assertEqual(by_event['ER1']['disposition'], 'kept_in_subagents')
        self.assertEqual(by_event['EB0']['disposition'], 'kept_in_subagents')

    def test_the_gate_refuses_the_prior_approval_as_a_current_one_and_wants_the_failed_turn(self):
        log = self.log()
        done = {'id': 'X-1', 'timestamp': LATER, 'outcome': 'completed', 'workflow': {'minimum_reviewers': 1},
                'agent_continuity': {}, 'subagents': {'richard': [
                    {'dispatch_id': 'R1', 'dispatch_event_id': 'ER0'}, {'dispatch_id': 'R3', 'dispatch_event_id': 'ER2'},
                    {'dispatch_id': 'R2', 'dispatch_event_id': 'ER1', 'status': 'failed'}]}}
        errors = policy.validate_reviews(done, log, self.SIG_NEW)
        self.assertTrue(any('R1' in e and 'iteration_timestamp' in e for e in errors), errors)
        done['subagents']['richard'] = [e for e in done['subagents']['richard'] if e['dispatch_id'] != 'R1']
        self.assertFalse(any(e.startswith('R1') for e in policy.validate_reviews(done, log, self.SIG_NEW)))
        # A failed turn left out of subagents is a missing completion, so it has to stay visible.
        done['subagents']['richard'] = [e for e in done['subagents']['richard'] if e['dispatch_id'] != 'R2']
        self.assertTrue(any(e.startswith('R2') and 'missing from subagents.richard' in e
                            for e in policy.validate_reviews(done, log, self.SIG_NEW)))

    def test_a_prior_identity_is_resolved_through_the_closeout_that_retained_it(self):
        bob = self.log()[0]
        history = [dict(self.prior(), maintenance={'baseline': {'sha256': 'b'}})]
        self.assertTrue(policy.known_completion_iteration(bob, self.start, history))
        self.assertFalse(policy.known_completion_iteration(bob, self.start, []))


class ParallelAndHelperTests(Deployment):
    """B: record helpers and declared parallel reviewers."""

    def two_reviewers(self, kind='documentation'):
        done = self.reviewed(kind)
        report = done['maintenance']['documentation']
        event = self.review('richard-runtime-2', report)
        done['subagents']['richard'].append({'dispatch_id': 'richard-runtime-2', 'dispatch_event_id': event['event_id']})
        done['agent_continuity']['richard'] = ['richard-runtime-1', 'richard-runtime-2']
        self.fixture.save_done(done)
        return done

    def codes(self):
        return [row['code'] for row in closeout_doctor.diagnose(self.fixture.gate)['findings']]

    def saved(self):
        return json.loads((self.root / project.STATE / 'issue-done.json').read_text())

    def test_an_undeclared_second_reviewer_is_still_an_unexplained_replacement(self):
        self.two_reviewers()
        self.assertIn('REPLACEMENT_UNEXPLAINED', self.codes())
        with self.assertRaisesRegex(ValueError, 'explain each replacement'):
            self.fixture.gate._check_done()

    def test_add_parallel_explains_the_second_reviewer_in_doctor_and_gate(self):
        self.two_reviewers()
        entry = loop_lifecycle.add_parallel(self.root, 'richard', 'richard-runtime-2',
                                            'A second reviewer was dispatched in parallel on purpose.')
        self.assertEqual(entry['id'], 'richard-runtime-2')
        self.assertEqual(self.saved()['agent_continuity']['parallel'], [entry])
        self.assertNotIn('REPLACEMENT_UNEXPLAINED', self.codes())
        self.assertEqual(self.fixture.gate._check_done()['outcome'], 'completed')

    def test_add_parallel_refuses_an_id_that_was_never_dispatched_or_a_short_reason(self):
        self.two_reviewers()
        with self.assertRaisesRegex(ValueError, 'never dispatched'):
            loop_lifecycle.add_parallel(self.root, 'richard', 'richard-ghost', 'Declared although it never ran at all.')
        with self.assertRaisesRegex(ValueError, 'at least 20 characters'):
            loop_lifecycle.add_parallel(self.root, 'richard', 'richard-runtime-2', 'too short')
        self.assertNotIn('parallel', self.saved()['agent_continuity'])

    def test_a_declaration_without_a_dispatch_for_this_iteration_explains_nothing(self):
        done = {'id': 'X-1', 'timestamp': LATER, 'agent_continuity': {'parallel': [
            {'role': 'richard', 'id': 'R2', 'reason': 'Declared although it ran in another iteration.'},
            {'role': 'richard', 'id': 'R9', 'reason': 'Declared although it never ran at all.'}]}}
        log = [PriorIterationTests.event('R2', 'richard', 'E1', TS, TS, signature='a' * 64)]
        self.assertEqual(policy.parallel_ids(done, log, 'richard'), set())
        log.append(PriorIterationTests.event('R2', 'richard', 'E2', LATER, SOON, signature='a' * 64))
        self.assertEqual(policy.parallel_ids(done, log, 'richard'), {'R2'})
        # A malformed declaration (reason too short) is never trusted.
        done['agent_continuity']['parallel'][0]['reason'] = 'short'
        self.assertEqual(policy.parallel_ids(done, log, 'richard'), set())

    def test_the_draft_does_not_propose_a_replacement_for_a_declared_parallel_reviewer(self):
        start = dict(PriorIterationTests.start)
        log = [PriorIterationTests.event('R1', 'richard', 'E1', LATER, SOON, status='failed'),
               PriorIterationTests.event('R2', 'richard', 'E2', LATER, SOON, signature='b' * 64)]
        draft = {'subagents': {'richard': [{'dispatch_id': 'R1', 'dispatch_event_id': 'E1'}]}, 'agent_continuity': {}}
        proposed = records.replacement_skeleton(start, log, draft)
        self.assertEqual([(e['old_id'], e['new_id']) for e in proposed], [('R1', 'R2')])
        draft['agent_continuity'] = {'parallel': [{'role': 'richard', 'id': 'R2',
                                                   'reason': 'A second reviewer was dispatched in parallel on purpose.'}]}
        # R1's own failure still needs a disposition, but the parallel reviewer is not offered as its successor.
        self.assertEqual([(e['old_id'], e['new_id']) for e in records.replacement_skeleton(start, log, draft)], [('R1', None)])

    def test_add_replacement_explains_a_replaced_identity(self):
        self.two_reviewers()
        self.assertIn('REPLACEMENT_UNEXPLAINED', self.codes())
        for bad, message in ((dict(reason='short'), 'at least 20 characters'), (dict(evidence_refs=[]), 'evidence-ref'),
                             (dict(old_id='richard-nobody'), 'not among subagents'), (dict(new_id='richard-runtime-1'), 'must differ')):
            args = dict(role='richard', old_id='richard-runtime-1', new_id='richard-runtime-2',
                        reason='The first reviewer was retired after its context grew too large.',
                        evidence_refs=['docs/code_map.md'])
            args.update(bad)
            with self.assertRaisesRegex(ValueError, message):
                loop_lifecycle.add_replacement(self.root, **args)
        entry = loop_lifecycle.add_replacement(self.root, 'richard', 'richard-runtime-1', 'richard-runtime-2',
                                               'The first reviewer was retired after its context grew too large.',
                                               ['docs/code_map.md'])
        self.assertEqual(self.saved()['agent_continuity']['replacements'], [entry])
        self.assertNotIn('REPLACEMENT_UNEXPLAINED', self.codes())

    def test_amend_kind_removes_the_amendment_findings_and_names_the_moved_file(self):
        self.reviewed(kind='documentation')
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text() + '\n# a comment that moves the scientific signature\n')
        found = {row['code']: row for row in closeout_doctor.diagnose(self.fixture.gate)['findings']}
        self.assertIn('KIND_AMENDMENT_REQUIRED', found)
        self.assertIn('changed: src/diffusion.py', found['KIND_AMENDMENT_REQUIRED']['observed'])
        with self.assertRaisesRegex(ValueError, 'already documentation and its transition'):
            loop_lifecycle.amend_kind(self.root, 'documentation', 'Nothing to amend here at all.')
        with self.assertRaisesRegex(ValueError, 'reason'):
            loop_lifecycle.amend_kind(self.root, 'scientific_change', '  ')
        result = loop_lifecycle.amend_kind(self.root, 'scientific_change', 'The edit to the diffusion owner is scientific.')
        self.assertEqual(result['workflow']['kind'], 'scientific_change')
        done = self.saved()
        self.assertEqual(done['workflow_amendment']['previous'], self.start['workflow'])
        self.assertEqual(done['workflow']['required_roles'], ['bob', 'richard'])
        codes = self.codes()
        for gone in ('KIND_AMENDMENT_REQUIRED', 'WORKFLOW_TRANSITION', 'WORKFLOW_INVALID'):
            self.assertNotIn(gone, codes)

    def test_a_hand_changed_kind_is_a_transition_finding_until_amended(self):
        done = self.reviewed(kind='documentation')
        done['workflow'] = dict(done['workflow'], kind='investigation')
        self.fixture.save_done(done)
        self.assertIn('WORKFLOW_TRANSITION', self.codes())
        loop_lifecycle.amend_kind(self.root, 'investigation', 'Reclassified after the review settled on an investigation.')
        self.assertNotIn('WORKFLOW_TRANSITION', self.codes())
        # Returning to the start kind needs no amendment record at all.
        loop_lifecycle.amend_kind(self.root, 'documentation', 'Restored to the kind the iteration started with.')
        self.assertNotIn('workflow_amendment', self.saved())

    def test_command_line_helpers_print_the_new_entry(self):
        self.two_reviewers()
        run = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_lifecycle.py'), 'add-parallel',
                              '--role', 'richard', '--id', 'richard-runtime-2',
                              '--reason', 'A second reviewer was dispatched in parallel on purpose.'],
                             cwd=self.root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)['id'], 'richard-runtime-2')
        refused = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_lifecycle.py'), 'add-parallel',
                                  '--role', 'richard', '--id', 'ghost', '--reason', 'Declared although it never ran at all.'],
                                 cwd=self.root, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 1)
        self.assertIn('never dispatched', refused.stdout)


class KindNoticeTests(Deployment):
    """C: the contradiction is reported when it becomes knowable."""

    def setUp(self):
        super().setUp()
        (self.root / 'config').mkdir()
        (self.root / 'config/model.cfg').write_text('ratio = 0.1\n')
        self.configure(configuration_paths=['config'])

    def event(self, name):
        return {'tool_name': 'Edit', 'tool_input': {'file_path': str(self.root / name)}}

    def test_kind_contradiction_names_an_owning_target_in_the_scientific_inventory(self):
        cfg = project.config(self.root)
        message = loop_gate.kind_contradiction(self.root, cfg, 'documentation', TARGETS)
        self.assertIn('src/diffusion.py', message)
        self.assertIn('scientific_change', message)
        self.assertIsNone(loop_gate.kind_contradiction(self.root, cfg, 'scientific_change', TARGETS))
        self.assertIsNone(loop_gate.kind_contradiction(self.root, cfg, 'documentation', ['docs/model_contract.md::x', TARGETS[0]]))
        self.assertIsNone(loop_gate.kind_contradiction(self.root, cfg, 'documentation', []))

    def test_prepare_reports_the_contradiction_as_a_notice_not_a_refusal(self):
        self.fixture.write_issue()
        self.fixture.reflect()
        gate = loop_gate.Gate(self.root)
        with contextlib.redirect_stderr(io.StringIO()):
            gate.prepare(self.fixture.issue, 'documentation', (), 'arch', 'Qualify the periodic boundary update.',
                         'docs/code_map.md#pipeline', TARGETS, ['docs/model_contract.md'],
                         'Trace the periodic update into its Fourier and conservation oracle before evaluating acceptance.')
        self.assertEqual(len(gate.notices), 1)
        self.assertTrue(gate.notices[0].startswith('KIND NOTICE: '))

    def test_editing_a_configuration_file_in_a_documentation_issue_prints_a_notice(self):
        self.fixture.prepare(kind='documentation')
        notice = hooks.kind_notice(self.root, self.event('config/model.cfg'))
        self.assertIn('config/model.cfg', notice)
        self.assertIn('kind amendment', notice)
        self.assertEqual(notice.count('\n'), 0)
        relative = hooks.kind_notice(self.root, {'tool_input': {'file_path': 'src/diffusion.py'}})
        self.assertIn('src/diffusion.py', relative)
        self.assertIsNone(hooks.kind_notice(self.root, self.event('docs/model_contract.md')))
        self.assertIsNone(hooks.kind_notice(self.root, {'tool_input': {}}))
        self.assertIsNone(hooks.kind_notice(self.root, self.event('../outside.txt')))

    def test_no_notice_for_a_scientific_change_issue(self):
        self.fixture.prepare(kind='scientific_change')
        self.assertIsNone(hooks.kind_notice(self.root, self.event('config/model.cfg')))
        self.assertIsNone(hooks.kind_notice(self.root, self.event('src/diffusion.py')))

    def test_the_records_hook_prints_the_notice_and_never_fails(self):
        self.fixture.prepare(kind='documentation')
        command = [sys.executable, '-B', str(self.root / 'tools/esx/hooks.py'), 'records', '--root', str(self.root)]
        run = subprocess.run(command, input=json.dumps(self.event('config/model.cfg')), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('config/model.cfg', run.stdout)
        run = subprocess.run(command, input='{not json', capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('kind amendment', run.stdout)

    def test_the_closeout_finding_names_the_moved_configuration_file(self):
        done = self.reviewed(kind='documentation')
        (self.root / 'config/model.cfg').write_text('ratio = 0.2\n')
        row = next(r for r in closeout_doctor.diagnose(self.fixture.gate)['findings'] if r['code'] == 'KIND_AMENDMENT_REQUIRED')
        self.assertIn('changed: config/model.cfg', row['observed'])
        self.assertIn('amend-kind', row['recovery'])
        # The helper compares only the scientific inventory: a documentation edit is not named.
        (self.root / 'docs/model_contract.md').write_text((self.root / 'docs/model_contract.md').read_text() + '\nProse.\n')
        text = issue_candidates.moved_scientific(self.root, self.start['maintenance']['baseline'], self.fixture.issue)
        self.assertEqual(text, 'changed: config/model.cfg')
        self.assertTrue(done)


class DocumentationPathsTests(Deployment):
    """D: documentation outside the tracked footprint."""

    def setUp(self):
        super().setUp()
        (self.root / 'extdoc').mkdir()
        (self.root / 'extdoc/guide.md').write_text('# Guide\n\nA short statement of the periodic update.\n')

    def sign(self, scientific=False):
        return project.source_signature(self.root, scientific=scientific)

    def test_a_configured_path_joins_the_non_scientific_inventory_only(self):
        before = self.sign()
        self.assertNotIn('extdoc/guide.md', project.inventory_paths(self.root, project.config(self.root)))
        self.configure(documentation_paths=['extdoc'])
        cfg = project.config(self.root)
        self.assertIn('extdoc/guide.md', project.inventory_paths(self.root, cfg))
        self.assertNotIn('extdoc/guide.md', project.inventory_paths(self.root, cfg, True))
        self.assertTrue(project.selected('extdoc/guide.md', cfg))
        self.assertFalse(project.selected('extdoc/guide.md', cfg, True))
        self.assertNotEqual(self.sign(), before)
        scientific, general = self.sign(True), self.sign()
        (self.root / 'extdoc/guide.md').write_text('# Guide\n\nA changed statement.\n')
        self.assertEqual(self.sign(True), scientific)
        self.assertNotEqual(self.sign(), general)

    def test_a_change_under_the_path_appears_in_a_candidate_capture(self):
        self.configure(documentation_paths=['extdoc'])
        first = issue_candidates.capture(self.root, 'SAMPLE-001')
        (self.root / 'extdoc/guide.md').write_text('# Guide\n\nA changed statement.\n')
        with self.assertRaisesRegex(ValueError, 'changed: extdoc/guide.md'):
            issue_candidates.check_current(self.root, first, 'SAMPLE-001')
        self.assertIn('extdoc/guide.md', issue_candidates.load(self.root, first, 'SAMPLE-001')['files'])
        import doc_inventory
        self.assertIn('extdoc/guide.md', doc_inventory.paths(self.root))

    def test_an_absent_key_changes_nothing(self):
        self.fixture.prepare(kind='documentation')
        baseline = maintenance.load(self.root, self.fixture.start['maintenance']['baseline'], 'baseline', 'SAMPLE-001')
        self.assertNotIn('scope', baseline)
        self.assertEqual(maintenance.check_start(self.root, self.fixture.start), [])
        self.configure(documentation_paths=[])
        self.assertEqual(maintenance.check_start(self.root, self.fixture.start), [])

    def test_the_baseline_guard_refuses_a_changed_list(self):
        self.configure(documentation_paths=['extdoc'])
        start = self.fixture.prepare(kind='documentation')
        baseline = maintenance.load(self.root, start['maintenance']['baseline'], 'baseline', 'SAMPLE-001')
        self.assertEqual(baseline['scope'], {'documentation_paths': ['extdoc']})
        self.assertEqual(maintenance.check_start(self.root, start), [])
        (self.root / 'more').mkdir()
        self.configure(documentation_paths=['extdoc', 'more'])
        errors = maintenance.check_start(self.root, start)
        self.assertEqual(len(errors), 1)
        self.assertIn('documentation_paths changed', errors[0])
        with self.assertRaisesRegex(ValueError, 'documentation_paths changed'):
            self.fixture.gate.check_start()
        self.configure(documentation_paths=[])
        self.assertIn('documentation_paths changed', maintenance.check_start(self.root, start)[0])

    def test_a_list_added_after_the_baseline_is_refused_too(self):
        start = self.fixture.prepare(kind='documentation')
        self.configure(documentation_paths=['extdoc'])
        self.assertIn('documentation_paths changed', maintenance.check_start(self.root, start)[0])

    def test_invalid_lists_are_refused(self):
        for value, message in ((['src/docs'], 'overlaps a source'), (['src'], 'overlaps a source'),
                               (['tests/notes'], 'overlaps a source'), (['results/notes'], 'overlaps an output'),
                               (['results'], 'overlaps an output'), ('extdoc', 'must be a list'), ([3], 'must be a list'),
                               (['../outside'], 'invalid project path')):
            self.configure(documentation_paths=value)
            with self.assertRaisesRegex(ValueError, message):
                project.config(self.root)


class TurnStatusTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'devel-loop/loop_state').mkdir(parents=True)

    def write(self, *rows):
        (self.root / 'devel-loop/loop_state/dispatch_log.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))

    @staticmethod
    def row(event, status='completed', ts=SOON, footer=True, agent='R1', **extra):
        row = {'event_id': event, 'agent_id': agent, 'agent_type': 'richard', 'ts': ts, 'status': status}
        if footer:
            row['footer'] = {'agent': 'richard', 'issue_id': 'X-1'}
        return dict(row, **extra)

    def transcript(self, footer=True):
        text = 'Review finished.' + ('\n```json\n{"agent": "richard", "issue_id": "X-1"}\n```' if footer else '')
        path = self.root / ('t-%s.jsonl' % footer)
        path.write_text(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [
            {'type': 'text', 'text': text}]}}) + '\n')
        return str(path)

    def status(self, **kwargs):
        return agent_runtime.turn_status(self.root, kwargs.pop('agent', 'R1'), kwargs.pop('since', LATER))

    def test_a_completed_event_with_a_footer_at_or_after_the_notification_is_advisory(self):
        self.write(self.row('E0', ts=TS), self.row('E1', 'failed', footer=False, ts=LATER), self.row('E2', ts=SOON))
        result = self.status()
        self.assertEqual((result['verdict'], result['witness'], result['event_id']), ('ADVISORY', 'dispatch_log', 'E2'))
        self.assertEqual(self.status(since=SOON)['event_id'], 'E2')

    def test_an_earlier_completion_does_not_cover_a_later_notification(self):
        self.write(self.row('E0', ts=TS))
        result = self.status(since=LATER)
        self.assertEqual((result['verdict'], result['event_id']), ('RESUME', None))

    def test_failed_only_and_completed_without_footer_both_resume(self):
        self.write(self.row('E1', 'failed', footer=False), self.row('E2', 'incomplete', footer=False))
        self.assertEqual(self.status()['verdict'], 'RESUME')
        self.assertIn('failed or incomplete', self.status()['detail'])
        self.write(self.row('E3', footer=False))
        result = self.status()
        self.assertEqual(result['verdict'], 'RESUME')
        self.assertIn('no footer', result['detail'])
        self.write(self.row('E4', footer=False), self.row('E5', agent='R2'))
        self.assertEqual(self.status()['verdict'], 'RESUME')  # another agent's completion is no witness

    def test_a_repeated_stop_cites_the_completion_it_repeats(self):
        self.write(self.row('E2', duplicate_of='E1'))
        self.assertEqual(self.status()['event_id'], 'E1')

    def test_the_transcript_decides_when_the_log_has_no_completion(self):
        self.write(self.row('E1', 'failed', footer=False, transcript=self.transcript(True)))
        result = self.status()
        self.assertEqual((result['verdict'], result['witness'], result['event_id']), ('ADVISORY', 'agent_transcript', None))
        self.assertTrue(result['transcript'].endswith('.jsonl'))
        self.write(self.row('E1', 'failed', footer=False, agent_transcript_path=self.transcript(True)))
        self.assertEqual(self.status()['witness'], 'agent_transcript')
        self.write(self.row('E1', 'failed', footer=False, transcript=self.transcript(False)))
        result = self.status()
        self.assertEqual((result['verdict'], result['witness']), ('RESUME', 'agent_transcript'))
        self.write(self.row('E1', 'failed', footer=False, transcript=str(self.root / 'missing.jsonl')))
        self.assertEqual(self.status()['verdict'], 'RESUME')
        self.write()
        self.assertEqual(self.status()['verdict'], 'RESUME')

    def test_the_command_is_read_only_and_validates_the_timestamp(self):
        self.write(self.row('E2'))
        before = (self.root / 'devel-loop/loop_state/dispatch_log.jsonl').read_bytes()
        run = subprocess.run([sys.executable, '-B', str(Path(agent_runtime.__file__)), '--root', str(self.root), 'turn-status',
                              '--agent-id', 'R1', '--since', LATER], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['verdict'], 'ADVISORY')
        self.assertEqual((self.root / 'devel-loop/loop_state/dispatch_log.jsonl').read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'invalid --since'):
            agent_runtime.turn_status(self.root, 'R1', 'yesterday')
        with self.assertRaisesRegex(ValueError, 'timezone'):
            agent_runtime.turn_status(self.root, 'R1', '2026-10-10T10:00:00')

    def test_the_resume_guidance_is_documented(self):
        kit = Path(test_framework.KIT) / 'template'
        for name in ('devel-loop/execution.md', 'esx/project_instructions.md'):
            self.assertIn('turn-status', (kit / name).read_text())


class ReuseDiagnosticsTests(Deployment):
    """F: why final verification did not reuse an execution."""

    def qualified(self):
        done = self.reviewed()
        log = self.log()
        packet = self.packet(done, events=log)
        result = final_verification.run(self.root, packet, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        return done, packet, result

    def test_a_documentation_only_change_reuses_the_execution(self):
        done, packet, first = self.qualified()
        base = self.start['maintenance']['baseline']
        (self.root / 'docs/extra_notes.md').write_text('# Notes\n\nA short prose note on the periodic update.\n')
        plan = maintenance.draft(self.root, self.fixture.issue, base)
        for row in plan['dispositions']:
            row.update(action='reviewed_unchanged', reason='The prose addition leaves the described contract unchanged and accurate.',
                       references=[row['target']])
        plan['map_delta'] = done['map_delta']
        report = maintenance.seal(self.root, plan)
        candidate = issue_candidates.capture(self.root, self.fixture.issue, base)
        verify.run(self.root, 'structural', 'arch', fresh=True)
        event = self.review('richard-runtime-1', report)
        selections = [self.selections()[0], dict(agent='richard', dispatch_id='richard-runtime-1',
                                                 dispatch_event_id=event['event_id'], correction_round=0)]
        with contextlib.redirect_stderr(io.StringIO()):
            orientation = maintenance.navigate(self.root, self.fixture.issue, base, 'arch', 'docs/code_map.md#pipeline', TARGETS,
                                               ['docs/model_contract.md'], 'Trace the periodic update into its Fourier and '
                                               'conservation oracle before evaluating acceptance.')
        second = handoff.assemble(self.root, self.start, self.log(), selections, candidate, report, BRIEF, orientation=orientation)
        self.assertEqual(handoff.readiness(self.root, second, 'final', 'arch')['status'], 'ready')
        with mock.patch.object(verify, 'execute', side_effect=AssertionError('must reuse the measured execution')):
            reused = final_verification.run(self.root, second, 'arch')
        self.assertEqual(reused['status'], 'REUSED EVIDENCE')
        self.assertEqual(reused['scientific'], first['scientific'])

    def test_the_reasons_for_a_refused_reuse_are_surfaced(self):
        done, packet, first = self.qualified()
        index = self.root / project.STATE / 'final-verification/current.json'
        index.write_text(json.dumps({'path': f'{project.STATE}/final-verification/{"f" * 64}.json', 'sha256': 'f' * 64}))
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), mock.patch.object(verify, 'run', side_effect=RuntimeError('stop before the suite')):
            with self.assertRaisesRegex(RuntimeError, 'stop before the suite'):
                final_verification.run(self.root, packet, 'arch')
        text = errors.getvalue()
        self.assertIn('check_receipt refused', text)
        self.assertIn('_reissue refused', text)
        self.assertIn('FileNotFoundError', text)
        self.assertFalse(index.exists())  # exactly as before: a refused reuse still clears current.json

    def test_the_fresh_result_carries_the_reasons(self):
        done, packet, first = self.qualified()
        index = self.root / project.STATE / 'final-verification/current.json'
        index.write_text(json.dumps({'path': f'{project.STATE}/final-verification/{"f" * 64}.json', 'sha256': 'f' * 64}))
        with contextlib.redirect_stderr(io.StringIO()), mock.patch.object(verify, 'run', return_value={'evidence': first['scientific']}):
            result = final_verification.run(self.root, packet, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        self.assertEqual(len(result['reuse_refused']), 2)
        index.unlink()
        with contextlib.redirect_stderr(io.StringIO()), mock.patch.object(verify, 'run', return_value={'evidence': first['scientific']}):
            result = final_verification.run(self.root, packet, 'arch')
        self.assertEqual(result['reuse_refused'], ['current.json missing'])
        with contextlib.redirect_stderr(io.StringIO()) as quiet, mock.patch.object(verify, 'run', return_value={'evidence': first['scientific']}):
            result = final_verification.run(self.root, packet, 'arch', fresh=True)
        self.assertEqual((result['reuse_refused'], quiet.getvalue()), ([], ''))


if __name__ == '__main__':
    unittest.main()
