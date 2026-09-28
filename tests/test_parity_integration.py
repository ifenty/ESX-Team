"""Portable end-to-end and failure tests for measured, bounded ESX operation.

Provider responses are deterministic fixtures. Diffusion verification and all
receipts/gates execute real project code. No paid API or external messages.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import test_framework
import test_runtime
import test_self_improvement
import agent_runtime
import brief
import doc_contract
import final_verification
import footer_contract
import ledger_transaction as transaction
import loop_gate
import loop_iteration
import loop_lifecycle
import process_evidence
import project
import records
import self_improvement as si
import team_accounting as accounting
import team_budget as budget
import team_retrospective as retro
import verify


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_start_receipt_binds_exact_iteration_and_content(self):
        start = self.fixture.prepare()
        self.assertTrue(loop_iteration.start_status(self.root, start)['validated'])
        edited = dict(start, priority_reason='Changed scope without validating its new start.')
        self.assertFalse(loop_iteration.start_status(self.root, edited)['validated'])
        self.assertFalse(loop_iteration.matches(start, dict(start, iteration=2)))
        self.assertFalse(loop_iteration.matches(start, dict(start, timestamp=project.now())))
        self.assertFalse(loop_iteration.start_status(self.root, {})['validated'])

    def test_closeout_without_start_receipt_fails(self):
        self.fixture.complete()
        for path in (self.root / project.STATE / 'start-receipts').glob('*.json'):
            path.unlink()
        with self.assertRaisesRegex(ValueError, 'successful --check-start'):
            self.fixture.gate.check_done()

    def test_measured_retro_is_mandatory_before_even_empty_queue(self):
        self.fixture.complete()
        done = self.fixture.gate.check_done()
        records.save_history(self.root, done)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.fixture.gate.next()
        self.assertIn('NEXT: RETROSPECTIVE', output.getvalue())
        with self.assertRaisesRegex(ValueError, 'RETROSPECTIVE_REQUIRED'):
            self.fixture.gate.prepare('OTHER', 'investigation', [], 'arch', '', '', [], [], '')
        draft = retro.draft(self.root)
        self.assertEqual(len(draft['measured']['unknown_cost_event_ids']), 2)
        draft['no_problem_reason'] = 'The synthetic workflow completed successfully; two simulated native reports have unknown provider costs and therefore cannot establish a zero cost live run.'
        bad = json.loads(json.dumps(draft)); bad['measured']['elapsed_seconds'] = -1
        with self.assertRaisesRegex(ValueError, 'measured block differs'):
            retro.accept(self.root, bad)
        self.assertEqual(retro.accept(self.root, draft)['status'], 'accepted')
        self.assertIsNone(retro.pending(self.root))
        self.assertEqual(len(list((self.root/si.BASE/'assessments/retrospectives').glob('*.json'))), 1)
        self.assertTrue(retro.accept(self.root, draft)['already_accepted'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.fixture.gate.next()
        self.assertNotIn('NEXT: RETROSPECTIVE', output.getvalue())

    def test_real_scientific_closeout_transaction_and_reuse(self):
        done = self.fixture.complete()
        self.fixture.write_issue()
        (self.root/'closed_issues.md').write_text('# Closed issues\n')
        row = si.parse(self.root/'open_issues.md')[0]
        closure = {'fields': {'Status': 'Resolved', 'Date Resolved': '2026-09-25'},
                   'sections': {'Resolution': 'Qualified the periodic diffusion solution against the actual Fourier and conservation checks.'}}
        metadata = {'summary': 'Qualified the unchanged periodic diffusion stencil using measured independent checks.',
                    'tests_status': 'passing', 'git': done['git'], 'communication': done['communication']}
        self.assertFalse(loop_lifecycle.prepare_done(self.root, done, done['verification'], metadata)['accepted'])
        self.assertEqual(transaction.promote(self.root, 'esx', self.fixture.issue, closure, transaction.digest(row.text))['status'], 'preview')
        self.assertIn(self.fixture.issue, records.issues(self.root))
        result = transaction.promote(self.root, 'esx', self.fixture.issue, closure, transaction.digest(row.text), True)
        self.assertEqual(result['status'], 'applied')
        accepted = self.fixture.gate.check_done()
        self.assertEqual(accepted['outcome'], 'completed')
        self.assertEqual(transaction.promote(self.root, 'esx', self.fixture.issue, closure, transaction.digest(row.text), True)['status'], 'already_promoted')
        with patch.object(verify, 'execute', side_effect=AssertionError('must reuse intact scientific evidence')):
            self.assertEqual(final_verification.run(self.root, accepted, 'arch')['status'], 'REUSED EVIDENCE')

    def test_generated_brief_drives_retained_bob_and_footer_validation(self):
        start = self.fixture.prepare()
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Qualify the unchanged diffusion update and run the Fourier and mass checks.')
        self.assertIn('--role bob', text)
        self.assertIn('correction_round', text)
        # The reseal instruction is emitted automatically, naming the oriented
        # targets, rather than depending on the coordinator remembering it.
        self.assertIn('Reseal before reporting', text)
        self.assertIn('FINAL steps after your last edit', text)
        self.assertIn('src/diffusion.py::step', text.split('Reseal before reporting')[1])
        # Allocations are stated as expectations, not caps.
        self.assertIn('recorded expectations, not caps', text)
        self.assertNotIn('At 80% of calls/time', text)
        with contextlib.redirect_stderr(io.StringIO()):
            nav = doc_contract.navigate(self.root, self.fixture.issue, start['maintenance']['baseline'], 'bob',
                'docs/code_map.md#pipeline', ['src/diffusion.py::step','tests/check_diffusion.py::<module>'],
                ['docs/model_contract.md'], 'Check the periodic update against its independent Fourier and conservation oracle.')
        footer = dict(skills_used=[], files_touched=[], agent='bob', issue_id=self.fixture.issue, correction_round=0,
                      iteration_timestamp=start['timestamp'], orientation=nav, summary='Focused qualification completed.', evidence=['Fourier and mass checks'], limits=[])
        binary = self.root/'fake-claude'; binary.write_text(test_runtime.FAKE); binary.chmod(0o755)
        event = agent_runtime.run_turn(self.root, role='bob', issue=self.fixture.issue,
            prompt=json.dumps({'footer':footer}), executable=str(binary), timeout=10)
        self.assertEqual(event['status'], 'completed', event)
        turn = self.root/project.STATE/'agent_runtime/sessions'/event['session_id']/'turns'/event['event_id']
        self.assertEqual(json.loads((turn/'handoff.json').read_text())['constraints'], [])
        invocation = json.loads((turn/'invocation.json').read_text())['argv']
        # No provider spend cap is imposed; the reservation only records expected cost.
        self.assertNotIn('--max-budget-usd', invocation)
        settings = json.loads(invocation[invocation.index('--settings')+1])
        self.assertIn('PreToolUse', settings['hooks'])
        # Recovery reads whether the turn left durable work behind, rather than
        # inferring it from a bare status.
        self.assertIn('source_changed_during_turn', event)
        self.assertFalse(event['source_changed_during_turn'])
        self.assertEqual(event['source_signature_at_finish'], event['source_signature_at_dispatch'])
        self.assertEqual(accounting.summary(self.root)['reported_usd'], 0)
        bad = dict(footer, summary=[])
        self.assertTrue(footer_contract.validate(self.root, 'bob', bad, self.fixture.issue, 0, start))
        bad = dict(footer, orientation=None)
        self.assertTrue(footer_contract.validate(self.root, 'bob', bad, self.fixture.issue, 0, start))

    def test_direct_review_refuses_stale_structural_before_provider(self):
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, 'STRUCTURAL_STALE_OR_FAILING'):
            agent_runtime.review_context(self.root, {}, self.fixture.issue, self.fixture.start['maintenance']['baseline'])

    def test_generated_review_brief_runs_actual_independent_checks(self):
        done = self.fixture.complete(qualify=False)
        generated = brief.build(self.root, 'richard', self.fixture.issue,
            'Qualify the unchanged periodic diffusion update.',
            'Does the Fourier and conservation oracle support this exact candidate?', done)
        self.assertIn('documentation_review', generated)
        self.assertIn('confirmed', generated)
        project.atomic_json(self.root/project.STATE/'review-fixture.json', done)
        binary = self.root/'fake-reviewer'
        binary.write_text('#!' + sys.executable + '\n' + '''
import contextlib, io, json, pathlib, sys
args = sys.argv[1:]
if '--version' in args:
    print('offline-reviewer-1'); raise SystemExit(0)
sys.stdin.read()
root = pathlib.Path.cwd()
sys.path.insert(0, str(root/'tools/esx'))
import doc_contract, footer_contract, project, verify
assignment = json.loads(args[args.index('--append-system-prompt')+1].split('ESX dispatcher assignment: ',1)[1].split('\\n',1)[0])
sid = assignment['agent_id']
packet = json.loads((root/project.STATE/'review-fixture.json').read_text())
with contextlib.redirect_stderr(io.StringIO()):
    orientation = doc_contract.navigate(root, packet['id'], packet['maintenance']['baseline'], 'richard',
        'docs/code_map.md#pipeline', ['src/diffusion.py::step','tests/check_diffusion.py::<module>'],
        ['docs/model_contract.md'], 'Independently inspect the exact periodic stencil and Fourier conservation oracle.')
evidence = verify.run(root, 'focused', sid, fresh=True)['evidence']
footer = footer_contract.example(root, 'richard')
footer.update(issue_id=packet['id'], iteration_timestamp=packet['timestamp'], correction_round=0,
    orientation=orientation, summary='Executed independent Fourier and conservation checks.',
    evidence=[evidence], candidate_signature=project.source_signature(root), verdict='APPROVE',
    independent_check={'cmd':'python tests/check_diffusion.py','exit':0,'executed':True,'evidence':evidence,'coverage':'Fourier decay and conservation'},
    documentation_review={'report':packet['maintenance']['documentation'],'status':'confirmed','notes':'Confirmed the sealed map and scientific contract against the unchanged candidate and executed oracle.'})
print(json.dumps({'type':'system','subtype':'init','session_id':sid}))
print(json.dumps({'type':'result','subtype':'success','is_error':False,'session_id':sid,'stop_reason':'end_turn',
    'result':'```json\\n'+json.dumps(footer)+'\\n```','total_cost_usd':0,'usage':{'input_tokens':0,'output_tokens':0}}))
''')
        binary.chmod(0o755)
        event = agent_runtime.run_turn(self.root, role='richard', issue=self.fixture.issue,
            prompt=generated, review_packet=done, executable=str(binary), timeout=20)
        self.assertEqual(event['status'], 'completed', event)
        self.assertEqual(verify.load_evidence(self.root, event['footer']['independent_check']['evidence'])['owner'], event['agent_id'])
        self.assertEqual(event['correction_round'], 0)

    def test_administrative_findings_do_not_stale_science_but_are_validated(self):
        self.fixture.prepare()
        receipt = verify.run(self.root, 'structural', 'arch')['evidence']
        signature = project.source_signature(self.root)
        assessment = self.root/si.BASE/'assessments/trial/assessment.md'
        assessment.parent.mkdir(parents=True); assessment.write_text('Measured process observation with retained evidence.\n')
        self.assertEqual(project.source_signature(self.root), signature)
        self.assertEqual(verify.structural_evidence(self.root), receipt)
        (self.root/si.OPEN).write_text('# Open\n\n## PROPOSED: Broken entry\n**UUID**: TEAM-BROKEN-001\n')
        with self.assertRaises(ValueError): verify.load_evidence(self.root, receipt)

    def test_witnesses_and_declared_scientific_configuration_are_not_excluded(self):
        before = project.source_signature(self.root)
        witness = self.root/si.BASE/'assessments/trial/witness.py'
        witness.parent.mkdir(parents=True); witness.write_text('EXPECTED = 1\n')
        self.assertNotEqual(project.source_signature(self.root), before)
        cfg = project.config(self.root)
        cfg['configuration_paths'].append(str(si.BASE))
        project.atomic_json(self.root/'esx/project.json', cfg)
        before = project.source_signature(self.root, scientific=True)
        (witness.parent/'measurement.json').write_text('{"changed":true}\n')
        self.assertNotEqual(project.source_signature(self.root, scientific=True), before)

    def test_standing_rule_lifecycle_and_repeat_detection(self):
        path=self.root/'devel-loop/loop_rules.md'
        path.write_text('# Rules\n\n## Rules\n\n- Preserve the independent oracle.\n\n## Retired\n')
        self.assertEqual(retro.standing_rules(self.root), ['Preserve the independent oracle.'])
        for i in range(2):
            accounting.append(self.root/project.STATE/'retrospective_history.jsonl', {'carry_forward':['Bound each scientific witness before starting review.']})
        self.assertTrue(any('PROMOTE OR RETIRE' in n for n in retro.rule_notices(self.root)))

    def test_upgrade_preserves_project_owned_process_history(self):
        import esx_manager
        for name in (str(si.OPEN), str(si.CLOSED), str(si.INDEX), 'devel-loop/loop_rules.md',
                     str(si.BASE/'records/original.md'), str(si.BASE/'assessments/trial/assessment.md')):
            self.assertEqual(esx_manager.ownership(name), 'project')

    def test_ignored_sigint_is_overridden_during_owned_execution_and_restored(self):
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            with tempfile.TemporaryFile(mode='w+') as log:
                with patch.object(verify.subprocess, 'Popen') as launch:
                    child = launch.return_value; child.pid = 99999999
                    def wait(timeout=None):
                        if timeout == 1:
                            self.assertNotEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)
                            raise InterruptedError('simulated interrupt after handler installation')
                        return 0
                    child.wait.side_effect = wait
                    with patch.object(verify.os, 'killpg', side_effect=ProcessLookupError):
                        with self.assertRaises(InterruptedError): verify.execute(['fixture'], self.root, log, 1)
            self.assertEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)
        finally:
            signal.signal(signal.SIGINT, previous)


class ContinuationTests(unittest.TestCase):
    def test_owner_extension_does_not_reset_unknown_spend(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cap=budget.limits('scientific_small')
            with patch.object(budget.time, 'time', return_value=1000):
                budget.reserve(root,'unknown','TEAM-TEST-001',cap);budget.settle(root,'unknown',None)
            with patch.object(budget.time, 'time', return_value=3000):
                # Allocations are expectations: the launch proceeds and the overrun is recorded.
                budget.reserve(root,'past-expectation','TEAM-TEST-001',cap)
                budget.settle(root,'past-expectation',0)
                scope=json.loads(budget.file_for(root).read_text())['scopes']['issue:TEAM-TEST-001']
                self.assertIn('minutes', scope['overruns'])
                request={'issue':'TEAM-TEST-001','authorization_id':'fixture-owner-1','authorized_by':'Owner',
                         'evidence':'fixture owner directive','reason':'Continue measured partial work',
                         'expected_scope_sha256':budget.scope_digest(scope),'add_minutes':20}
                path=root/'authorization.json';path.write_text(json.dumps(request));ref=process_evidence.ref(root,path)
                self.assertEqual(budget.extend(root,ref)['status'],'preview')
                self.assertEqual(budget.extend(root,ref,True)['retained_charged_usd'],5)
                self.assertEqual(budget.extend(root,ref,True)['status'],'already_applied')
                cap,_=budget.assignment(root,'TEAM-TEST-001')
                self.assertEqual(budget.reserve(root,'resumed','TEAM-TEST-001',cap)['deadline'],4200)


    def test_recurring_owner_blocks_selection_and_deferral_expires(self):
        import team_retrospective as retro
        import team_accounting as accounting
        fixture = test_self_improvement.SelfImprovementTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        state = root / accounting.STATE
        for n in range(2):
            accounting.append(state / 'retrospective_history.jsonl', {'id': str(n), 'problems': [{'category': 'footer_shape'}], 'solutions': [{'problem': 0, 'action': 'filed', 'reference': 'TEAM-FOOTER-CONTRACT-001'}]})
        accounting.append(state / 'loop_history.jsonl', {'id': 'LAST', 'timestamp': 'first'})
        with self.assertRaisesRegex(ValueError, 'FOLLOWUP_REQUIRED'):
            retro.require_followup(root)
        retro.require_followup(root, 'TEAM-FOOTER-CONTRACT-001')
        retro.decide_followup(root, 'TEAM-FOOTER-CONTRACT-001', 'deferred', 'Defer exactly one iteration while the concrete fix is reviewed and its regression runs.')
        self.assertEqual(retro.followup_due(root), [])
        accounting.append(state / 'loop_history.jsonl', {'id': 'NEXT', 'timestamp': 'second'})
        self.assertEqual(retro.followup_due(root), ['TEAM-FOOTER-CONTRACT-001'])

if __name__ == '__main__':
    unittest.main()
