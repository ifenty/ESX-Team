"""Prepared scientific execution, failure recovery and process ownership checks.

Each test deploys a complete independent diffusion project. Scientific checks
execute the finite difference model and its Fourier/conservation oracle.
"""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_framework
import final_verification
import hooks
import issue_candidates
import loop_gate
import project
import records
import verify
import workflow_policy as policy


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def reviewed(self):
        return self.fixture.complete(qualify=False)

    def append(self, event):
        with (self.root / project.STATE / 'dispatch_log.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')

    def test_packet_builder_and_current_acceptance_reuse_execution(self):
        import workflow_records as wr
        import workflow_handoff as wh
        done = self.reviewed()
        start = self.fixture.start
        events = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        selections = []
        for event in events:
            event['footer']['correction_round'] = 0
            selections.append(dict(agent=event['agent_type'], dispatch_id=event['agent_id'],
                                   dispatch_event_id=event['event_id'], correction_round=0))
        (self.root / project.STATE / 'dispatch_log.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        brief = dict(outcome='Qualify periodic diffusion', constraints=['mass conservation'],
                     acceptance_tests=['Fourier solution and mass oracle'])
        packet = wh.assemble(self.root, start, events, selections[:1], done['candidate'],
                             done['maintenance']['documentation'], brief)
        self.assertEqual(wh.readiness(self.root, packet, 'review')['status'], 'ready')
        self.assertEqual(wh.readiness(self.root, packet, 'final', 'arch')['status'], 'blocked')
        complete = wh.assemble(self.root, start, events, selections, done['candidate'],
                               done['maintenance']['documentation'], brief)
        ready = wh.readiness(self.root, complete, 'final', 'arch')
        self.assertEqual(ready['status'], 'ready', ready)
        result = final_verification.run(self.root, complete, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        # Change review evidence only; require fresh acceptance while retaining
        # the actual executed Fourier/conservation qualification receipt.
        events[-1]['footer']['documentation_review']['notes'] += ' Independently confirmed the unchanged stencil.'
        (self.root / project.STATE / 'dispatch_log.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        complete = wh.assemble(self.root, start, events, selections, done['candidate'],
                               done['maintenance']['documentation'], brief)
        with patch.object(verify, 'execute', side_effect=AssertionError('must reuse measured scientific execution')):
            reused = final_verification.run(self.root, complete, 'arch')
        self.assertEqual(reused['status'], 'REUSED EVIDENCE')
        self.assertEqual(reused['scientific'], result['scientific'])
        self.assertNotEqual(reused['receipt'], result['receipt'])
        complete['verification'] = dict(receipt=reused['receipt'], scientific=reused['scientific'])
        self.assertEqual(final_verification.check_receipt(self.root, complete)['status'], 'PASS')

    def test_command_line_qualification_shares_its_own_lease(self):
        """Qualify through the documented command, not only the in-process call.

        Executed as a script this module is registered as '__main__'. verify.py
        then resolves its own lazy `import final_verification` to whatever that
        name refers to, so without the module alias it receives a second
        instance whose _LEASES is empty and refuses the lease this very process
        granted -- reporting that the operator must run the command they are
        already running. Only a subprocess reproduces that arrangement.
        """
        done = self.reviewed()
        packet = self.root / project.STATE / 'review-packet-command-line.json'
        project.atomic_json(packet, done)
        run = subprocess.run([sys.executable, str(self.root / 'tools/esx/final_verification.py'),
                              'run', '--root', str(self.root), '--review', str(packet), '--owner', 'arch'],
                             capture_output=True, text=True)
        output = run.stdout + run.stderr
        self.assertNotIn('requires final_verification.py run', output)
        self.assertEqual(run.returncode, 0, output)
        self.assertIn('EXECUTED PASS', output)
        done['verification'].update(**{k: json.loads(run.stdout)[k] for k in ('scientific', 'receipt')})
        self.assertEqual(final_verification.check_receipt(self.root, done)['status'], 'PASS')

    def test_prepared_diffusion_pass_and_exact_reuse(self):
        done = self.reviewed()
        result = final_verification.run(self.root, done, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        self.fixture.save_done(done)
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')
        with patch.object(verify, 'execute', side_effect=AssertionError('cached final must execute no command')):
            reused = final_verification.run(self.root, done, 'arch')
        self.assertEqual(reused['status'], 'REUSED EVIDENCE')
        self.assertEqual(reused['receipt'], result['receipt'])
        self.assertEqual(final_verification.check_receipt(self.root, done)['status'], 'PASS')

    def test_partial_iteration_retains_prior_completions_and_requires_fresh_review(self):
        prior = self.reviewed()
        prior.update(outcome='partial', next_step='Continue the bounded transport and evidence qualification.')
        self.fixture.write_issue()
        (self.root / 'closed_issues.md').write_text('# Closed issues\n')
        self.fixture.save_done(prior)
        records.save_history(self.root, self.fixture.gate.check_done())
        done = self.reviewed()
        for role in ('bob', 'richard'):
            done['subagents'][role] = prior['subagents'][role] + done['subagents'][role]
        result = final_verification.run(self.root, done, 'arch')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        self.fixture.save_done(done)
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')

    def test_old_iteration_approval_cannot_qualify_new_iteration(self):
        prior = self.reviewed()
        prior.update(outcome='partial', next_step='Continue with a new bounded iteration after collecting evidence.')
        self.fixture.write_issue()
        (self.root / 'closed_issues.md').write_text('# Closed issues\n')
        self.fixture.save_done(prior)
        records.save_history(self.root, self.fixture.gate.check_done())
        start = self.fixture.prepare()
        done = dict(prior, timestamp=start['timestamp'], workflow=start['workflow'], outcome='completed')
        with self.assertRaisesRegex(ValueError, 'iteration|approvals|documentation'):
            final_verification.run(self.root, done, 'arch')

    def test_direct_science_refused_before_reviews(self):
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, 'requires final_verification'):
            verify.run(self.root, 'scientific', 'arch')
        self.assertFalse(list((self.root / project.STATE / 'verification').glob('run-*.log')))

    def test_direct_science_allowed_without_active_issue(self):
        self.assertEqual(verify.run(self.root, 'scientific', 'arch')['status'], 'EXECUTED PASS')

    def test_wrong_owner_and_missing_approval_refused_before_science(self):
        done = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'assigned final'):
            final_verification.run(self.root, done, 'bob')
        done['subagents']['richard'] = []
        with self.assertRaisesRegex(ValueError, 'missing required role'):
            final_verification.run(self.root, done, 'arch')

    def test_snapshot_drift_invalidates_review_and_final_receipt(self):
        done = self.reviewed()
        result = final_verification.run(self.root, done, 'arch')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text() + '\n# Changed candidate\n')
        with self.assertRaisesRegex(ValueError, 'stale|changed|candidate'):
            final_verification.check_receipt(self.root, done)

    def test_input_bytes_and_toolchain_configuration_invalidate_final(self):
        input_path = self.root / 'results/input.txt'
        input_path.parent.mkdir()
        input_path.write_text('1')
        cfg = project.config(self.root)
        cfg['external_inputs'] = ['results/input.txt']
        project.atomic_json(self.root / 'esx/project.json', cfg)
        done = self.reviewed()
        result = final_verification.run(self.root, done, 'arch')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        input_path.write_text('2')
        with self.assertRaisesRegex(ValueError, 'stale'):
            final_verification.check_receipt(self.root, done)
        input_path.write_text('1')
        cfg['toolchain_commands'].append(['{python}', '-c', 'print("tool revision")'])
        project.atomic_json(self.root / 'esx/project.json', cfg)
        with self.assertRaisesRegex(ValueError, 'stale|candidate'):
            final_verification.check_receipt(self.root, done)

    def test_failed_new_attempt_revokes_prior_pass(self):
        cfg = project.config(self.root)
        cfg['verification']['scientific'].append(['{python}', '-c',
            'from pathlib import Path; import sys; sys.exit(int(Path("results/fail").exists()))'])
        project.atomic_json(self.root / 'esx/project.json', cfg)
        done = self.reviewed()
        result = final_verification.run(self.root, done, 'arch')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        (self.root / 'results').mkdir(exist_ok=True)
        (self.root / 'results/fail').touch()
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            final_verification.run(self.root, done, 'arch', fresh=True)
        with self.assertRaises((ValueError, FileNotFoundError)):
            final_verification.check_receipt(self.root, done)
        failures = [json.loads(p.read_text()) for p in (self.root / project.STATE / 'final-verification').glob('*.json')]
        self.assertTrue(any(row.get('status') == 'FAILED' for row in failures))

    def test_later_failed_reviewer_invalidates_previous_approval(self):
        done = self.reviewed()
        events = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        old = events[-1]
        failed = dict(old, event_id='failed-review', status='failed', footer=None,
                      issue_id=done['id'], iteration_timestamp=done['timestamp'], correction_round=1)
        self.append(failed)
        errors = policy.validate_reviews(done, events + [failed], project.source_signature(self.root))
        self.assertTrue(any('latest' in error for error in errors), errors)
        done['subagents']['richard'].append({'dispatch_id': failed['agent_id'], 'dispatch_event_id': failed['event_id'], 'status': 'failed'})
        with self.assertRaisesRegex(ValueError, 'failed or incomplete'):
            final_verification.ready(self.root, done, 'arch')

    def test_true_same_session_continuation_resolves_failed_turn(self):
        done = self.reviewed()
        events = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        old = events[-1]
        failed = dict(old, event_id='failed-review', status='failed', footer=None,
                      issue_id=done['id'], iteration_timestamp=done['timestamp'], correction_round=1)
        recovered = dict(old, event_id='recovered-review', status='completed', correction_round=2)
        self.append(failed)
        self.append(recovered)
        for event in (failed, recovered):
            done['subagents']['richard'].append({'dispatch_id': event['agent_id'], 'dispatch_event_id': event['event_id'], 'status': event['status']})
        self.assertEqual(policy.validate_reviews(done, events + [failed, recovered], project.source_signature(self.root)), [])
        self.assertTrue(final_verification.ready(self.root, done, 'arch'))

    def test_failed_turn_needs_explicit_replacement_evidence(self):
        done = {'id': 'X', 'timestamp': 'T', 'subagents': {'bob': []}, 'agent_continuity': {'replacements': []}}
        failed = {'event_id': 'a', 'agent_type': 'bob', 'agent_id': 'one', 'status': 'failed', 'issue_id': 'X', 'iteration_timestamp': 'T', 'correction_round': 0}
        recovered = dict(failed, event_id='b', agent_id='two', status='completed', correction_round=1)
        done['subagents']['bob'] = [{'dispatch_id': 'two', 'dispatch_event_id': 'b'}]
        self.assertFalse(policy.resolved_dispatch(failed, [failed, recovered], done))
        done['agent_continuity']['replacements'] = [{'role': 'bob', 'old_id': 'one', 'new_id': 'two', 'reason': 'Provider cannot resume its recorded session.', 'evidence_refs': ['runtime failure a']}]
        self.assertTrue(policy.resolved_dispatch(failed, [failed, recovered], done))

    def test_iteration_signatures_and_baseline_preserve_original_issue(self):
        start = self.fixture.prepare(kind='investigation')
        records.save_history(self.root, dict(start, outcome='partial', next_step='Inspect source ownership.'))
        original = self.root / 'src/diffusion.py'
        original.write_text(original.read_text() + '\n# bounded next change\n')
        following = self.fixture.prepare(kind='investigation')
        self.assertEqual(following['maintenance']['baseline'], start['maintenance']['baseline'])
        self.assertEqual(following['workflow']['verify_signature_at_start'], start['workflow']['verify_signature_at_start'])
        self.assertEqual(following['workflow']['numerical_signature_at_start'], start['workflow']['numerical_signature_at_start'])
        self.assertEqual(following['iteration'], 2)

    def test_two_failed_corrections_require_measured_diagnosis(self):
        start = self.fixture.prepare(kind='investigation')
        for round_number in (1, 2):
            row = dict(start, timestamp=f'2026-09-15T00:00:0{round_number}+00:00', outcome='partial',
                       agent_continuity={'correction_round': round_number}, tests_status='failing')
            records.save_history(self.root, row)
        start['timestamp'] = '2026-09-15T00:00:02+00:00'
        project.atomic_json(self.root / project.STATE / 'issue-start.json', start)
        self.fixture.reflect()
        with self.assertRaisesRegex(ValueError, 'diagnosis checkpoint'):
            self.fixture.prepare(kind='investigation')

    def test_execution_policy_cannot_be_removed_by_amendment(self):
        start = policy.default_workflow('investigation', 'a' * 64)
        done = dict(start)
        del done['execution_version']
        self.assertTrue(policy.validate_transition(start, done, {'previous': start, 'reason': 'Avoid preparation.'}))

    def test_timeout_kills_spawned_descendants_and_records_failure(self):
        cfg = project.config(self.root)
        cfg['command_timeout_seconds'] = 0.3
        command = ('import subprocess,sys,time,pathlib; '
                   'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                   'pathlib.Path("results/child.pid").write_text(str(p.pid)); time.sleep(60)')
        cfg['verification']['focused'] = [['{python}', '-c', command]]
        project.atomic_json(self.root / 'esx/project.json', cfg)
        (self.root / 'results').mkdir(exist_ok=True)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            verify.run(self.root, 'focused', 'arch', fresh=True)
        self.assertLess(time.monotonic() - started, 5)
        pid = int((self.root / 'results/child.pid').read_text())
        # A killed process can briefly remain as a zombie awaiting the OS reaper.
        result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
        self.assertTrue(not result.stdout.strip() or result.stdout.strip().startswith('Z'), result.stdout)
        receipts = [json.loads(path.read_text()) for path in (self.root / project.STATE / 'verification').glob('*.json')]
        self.assertTrue(any(item.get('exit') == 124 for item in receipts))

    def test_source_changes_during_verification_fail_the_run(self):
        cfg = project.config(self.root)
        cfg['verification']['scientific'] = [['{python}', '-c', 'from pathlib import Path; p=Path("src/new.py"); p.write_text("VALUE=1\\n")']]
        project.atomic_json(self.root / 'esx/project.json', cfg)
        with self.assertRaisesRegex(ValueError, 'source changed'):
            verify.run(self.root, 'scientific', 'arch')


if __name__ == '__main__':
    unittest.main()
