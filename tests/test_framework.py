"""Deployment and end-to-end ESX contracts in disposable, synthetic projects.

Hook events below simulate the documented runtime adapter and test correlation.
Actual provider availability requires a deployment smoke check. All scientific example checks execute real code.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('esx_deploy', KIT / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
sys.path.insert(0, str(KIT / 'template/tools/esx'))
import audit
import doc_contract as maintenance
import doc_inventory
import hooks
import loop_gate
import project
import records
import verify
import final_verification
import issue_candidates
import team_retrospective
import notifications


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='esx deployment ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'project with spaces'
        deploy.deploy(self.root, apply=True)
        example = KIT / 'examples/periodic_diffusion'
        for directory in ('src', 'tests'):
            shutil.copytree(example / directory, self.root / directory)
        for source, target in [('project.json', 'esx/project.json'), ('project_profile.md', 'esx/project_profile.md'), ('code_map.md', 'docs/code_map.md')]:
            shutil.copyfile(example / source, self.root / target)

    def write_issue(self):
        self.issue = 'SAMPLE-001'
        self.root.joinpath('open_issues.md').write_text('''# Open issues

## UNRESOLVED: Diffusion qualification
**Status**: Unresolved
**UUID**: SAMPLE-001
**Anchors**: src/diffusion.py::step; tests/check_diffusion.py::<module>
''')

    def reflect(self):
        if team_retrospective.pending(self.root):
            draft = team_retrospective.draft(self.root)
            draft['no_problem_reason'] = 'This disposable test records its measured process evidence; provider costs are unknown for simulated native dispatches and no live efficiency claim is made.'
            team_retrospective.accept(self.root, draft)

    def prepare(self, kind='scientific_change', risks=()):
        self.reflect()
        self.write_issue()
        self.gate = loop_gate.Gate(self.root)
        with contextlib.redirect_stderr(io.StringIO()):
            self.start = self.gate.prepare(self.issue, kind, risks, 'arch', 'Qualify the periodic boundary update.',
                                           'docs/code_map.md#pipeline', ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'],
                                           ['docs/model_contract.md'], 'Trace the periodic update into its Fourier and conservation oracle before evaluating acceptance.')
        if not notifications.pending(self.root):
            self.gate.check_start()
        return self.start

    def complete(self, risks=(), qualify=True):
        self.prepare(risks=risks)
        base = self.start['maintenance']['baseline']
        plan = maintenance.draft(self.root, self.issue, base)
        self.assertEqual(plan['changes'], [])
        plan['map_delta'] = {'status': 'MAP-OK', 'reason': 'This qualification leaves the mapped periodic update and its independent oracle routes unchanged.',
                             'references': ['docs/code_map.md#pipeline']}
        report = maintenance.seal(self.root, plan)
        done = {'state_version': self.start['state_version'], 'iteration': self.start['iteration'], 'id': self.issue, 'timestamp': self.start['timestamp'], 'outcome': 'completed', 'summary': 'Qualified the synthetic stencil.',
                'workflow': self.start['workflow'], 'scope_decisions': [], 'lessons': [],
                'git': {'committed': False, 'reason': 'This disposable qualification task does not create commits.'},
                'communication': {'status': 'disabled', 'detail': 'Synthetic tests do not send external messages.'},
                'maintenance': {**self.start['maintenance'], 'documentation': report}, 'map_delta': plan['map_delta'],
                'verification': {'final_owner': 'arch'}, 'subagents': {}, 'agent_continuity': {}}
        for role in ('bob', 'richard'):
            with contextlib.redirect_stderr(io.StringIO()):
                nav = maintenance.navigate(self.root, self.issue, base, role, 'docs/code_map.md#pipeline',
                                           ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'], ['docs/model_contract.md'],
                                           'Read the periodic owner and exact Fourier oracle to assess conservation, stability and the qualified model scope.')
            agent = role + '-runtime-1'
            footer = {'agent': role, 'issue_id': self.issue, 'iteration_timestamp': self.start['timestamp'], 'orientation': nav}
            if role == 'richard':
                evidence = verify.run(self.root, 'focused', agent, fresh=True)['evidence']
                footer.update(candidate_signature=project.source_signature(self.root), verdict='APPROVE', must_fix=[],
                              independent_check={'cmd': 'python3 tests/check_diffusion.py', 'exit': 0, 'executed': True, 'evidence': evidence},
                              documentation_review={'report': report, 'status': 'confirmed', 'notes': 'Checked the mapped owner and Fourier oracle contracts against the unchanged qualification candidate.'})
            event = hooks.capture(self.root, {'agent_type': role, 'agent_id': agent, 'session_id': 'synthetic-session',
                                              'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})
            done['subagents'][role] = [{'dispatch_id': agent, 'dispatch_event_id': event['event_id']}]
            done['agent_continuity'][role] = [agent]
        self.root.joinpath('open_issues.md').write_text('# Open issues\n')
        self.root.joinpath('closed_issues.md').write_text('# Closed issues\n\n## RESOLVED: Diffusion qualification\n**Status**: Resolved\n**UUID**: SAMPLE-001\n')
        done['candidate'] = issue_candidates.capture(self.root, self.issue, base)
        done['verification']['structural'] = verify.run(self.root, 'structural', 'arch')['evidence']
        if qualify and not risks:
            self.finalize(done)
        self.save_done(done)
        return done

    def finalize(self, done):
        done['candidate'] = issue_candidates.capture(self.root, self.issue, self.start['maintenance']['baseline'])
        structural = done['verification'].get('structural') or verify.run(self.root, 'structural', 'arch')['evidence']
        final = final_verification.run(self.root, done, 'arch')
        done['verification'] = {'final_owner': 'arch', 'structural': structural,
                                'scientific': final['scientific'], 'receipt': final['receipt']}
        self.save_done(done)
        return done

    def save_done(self, done):
        project.atomic_json(self.root / project.STATE / 'issue-done.json', done)

    def test_completed_deployment_audits_and_has_no_source_project_dependencies(self):
        self.assertEqual(audit.check(self.root)['status'], 'PASS')
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'/Users/ifenty/', path.read_bytes())
                self.assertNotIn(b'ADX', path.read_bytes())

    def test_configured_archive_paths_are_excluded_from_link_checking(self):
        """Superseded documentation keeps its stale links without a code edit.

        A project that retains historical Markdown would otherwise have to patch
        audit.py to keep a passing structural gate, so the exclusion belongs in
        reviewed configuration instead.
        """
        archive = self.root / 'docs/superseded'
        archive.mkdir(parents=True)
        (archive / 'old_design.md').write_text('# Superseded\n\nSee [the old layout](../../gone/removed.md).\n')
        with self.assertRaisesRegex(ValueError, 'missing/locality-invalid link'):
            audit.check(self.root)
        configuration = self.root / 'esx/project.json'
        settings = json.loads(configuration.read_text())
        settings['archive_paths'] = ['docs/superseded']
        configuration.write_text(json.dumps(settings, indent=2) + '\n')
        self.assertEqual(audit.check(self.root)['status'], 'PASS')
        # A configured scientific root outranks the archive convention, so real
        # source can never be quietly exempted by listing it here.
        settings['archive_paths'] = ['src']
        configuration.write_text(json.dumps(settings, indent=2) + '\n')
        self.assertFalse(project.archived('src/diffusion.py', json.loads(configuration.read_text())))

    def test_archive_paths_must_be_local_project_paths(self):
        configuration = self.root / 'esx/project.json'
        settings = json.loads(configuration.read_text())
        settings['archive_paths'] = ['../outside']
        configuration.write_text(json.dumps(settings, indent=2) + '\n')
        with self.assertRaisesRegex(ValueError, 'invalid project path'):
            audit.check(self.root)
        settings['archive_paths'] = [123]
        configuration.write_text(json.dumps(settings, indent=2) + '\n')
        with self.assertRaisesRegex(ValueError, 'archive_paths must be a list of project paths'):
            audit.check(self.root)

    def test_blank_deployment_requires_customization(self):
        other = self.root.parent / 'blank'
        deploy.deploy(other, apply=True)
        with self.assertRaisesRegex(ValueError, 'project_id'):
            audit.check(other)

    def test_missing_hook_or_required_skill_is_detected(self):
        skill = self.root / '.claude/skills/esx-common/SKILL.md'
        saved = skill.read_bytes()
        skill.unlink()
        with self.assertRaisesRegex(ValueError, 'missing ESX skill'):
            audit.check(self.root)
        skill.write_bytes(saved)
        (self.root / 'tools/esx/hooks.py').unlink()
        with self.assertRaisesRegex(ValueError, 'missing framework utility'):
            audit.check(self.root)

    def test_deployment_merges_shared_files_preserves_settings_and_is_idempotent(self):
        other = self.root.parent / 'existing'
        (other / '.claude').mkdir(parents=True)
        (other / 'CLAUDE.md').write_text('Owner instructions\n')
        (other / '.gitignore').write_text('data/\n')
        (other / '.claude/settings.json').write_text(json.dumps({'permissions': {'allow': ['Read']}, 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'my-plugin-stop'}]}]}}))
        deploy.deploy(other, apply=True)
        self.assertIn('Owner instructions', (other / 'CLAUDE.md').read_text())
        settings = json.loads((other / '.claude/settings.json').read_text())
        self.assertEqual(settings['permissions'], {'allow': ['Read']})
        self.assertEqual(settings['hooks']['Stop'][0]['hooks'][0]['command'], 'my-plugin-stop')
        before = {p.relative_to(other): p.read_bytes() for p in other.rglob('*') if p.is_file()}
        self.assertEqual(deploy.deploy(other, apply=True), [])
        self.assertEqual(before, {p.relative_to(other): p.read_bytes() for p in other.rglob('*') if p.is_file()})

    def test_collision_preflight_writes_nothing(self):
        other = self.root.parent / 'conflicting'
        (other / 'docs').mkdir(parents=True)
        (other / 'docs/code_map.md').write_text('Existing scientific map\n')
        with self.assertRaisesRegex(ValueError, 'collision'):
            deploy.deploy(other, apply=True)
        self.assertEqual([p.relative_to(other).as_posix() for p in other.rglob('*') if p.is_file()], ['docs/code_map.md'])

    def test_symlink_destination_is_refused(self):
        other = self.root.parent / 'symlinked'
        other.mkdir()
        (other / 'docs').symlink_to(self.root / 'docs', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            deploy.deploy(other, apply=True)

    def test_prepare_refuses_to_overwrite_an_active_iteration(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'active iteration'):
            self.prepare()

    def test_executable_cli_works_outside_the_deployed_project(self):
        run = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_gate.py'), '--doctor'],
                             cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_complete_closeout_and_notification_refresh(self):
        done = self.complete()
        run = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_gate.py'), '--check-done'],
                             cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        done = json.loads(run.stdout)
        self.assertEqual(done['outcome'], 'completed')
        self.assertEqual(self.gate.check_done()['outcome'], 'completed')
        self.assertFalse(records.save_history(self.root, done))
        done['slack_ts'] = '1789344000.123456'
        self.save_done(done)
        self.gate.check_done()
        self.assertTrue(records.save_history(self.root, done))
        history = records.json_lines(self.root / project.STATE / 'loop_history.jsonl')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['slack_ts'], done['slack_ts'])
        self.assertEqual(history[0]['git'], done['git'])
        self.assertFalse(records.save_history(self.root, done))

    def test_high_risk_needs_two_distinct_current_reviewers(self):
        self.complete(risks=['fundamental_algorithm'])
        with self.assertRaisesRegex(ValueError, '2 required'):
            self.gate.check_done()

    def test_high_risk_accepts_two_current_independent_receipts(self):
        done = self.complete(risks=['fundamental_algorithm'])
        base = self.start['maintenance']['baseline']
        with contextlib.redirect_stderr(io.StringIO()):
            nav = maintenance.navigate(self.root, self.issue, base, 'richard', 'docs/code_map.md#pipeline',
                                       ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'], ['docs/model_contract.md'],
                                       'A second reviewer checks periodic mass conservation and invalid coefficients against the same bounded source contract.')
        first = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')[-1]['footer']
        footer = copy.deepcopy(first)
        footer['orientation'] = nav
        agent = 'richard-runtime-2'
        footer['independent_check']['evidence'] = verify.run(self.root, 'focused', agent, fresh=True)['evidence']
        event = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': agent, 'session_id': 'synthetic-session',
                                          'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})
        done['subagents']['richard'].append({'dispatch_id': agent, 'dispatch_event_id': event['event_id']})
        done['agent_continuity']['richard'].append(agent)
        self.finalize(done)
        self.assertEqual(self.gate.check_done()['outcome'], 'completed')

    def test_missing_sealed_documentation_blocks_completion(self):
        done = self.complete()
        del done['maintenance']['documentation']
        self.save_done(done)
        with self.assertRaisesRegex(ValueError, 'documentation evidence reference'):
            self.gate.check_done()

    def test_documentation_review_status_synonym_is_rejected_with_a_precise_message(self):
        # Fix 3c (2026-09-23 self-improvement): 'sealed' describes the report's
        # own state; the gate requires the literal 'confirmed' -- Richard's own
        # act of confirming it. This recurred independently more than once in
        # the source project; the error must name the exact expected value.
        done = self.complete(qualify=False)
        richard_event_id = done['subagents']['richard'][0]['dispatch_event_id']
        original = next(r for r in records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
                        if r['event_id'] == richard_event_id)
        footer = copy.deepcopy(original['footer'])
        footer['documentation_review']['status'] = 'sealed'
        event = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': original['agent_id'], 'session_id': 'synthetic-session-2',
                                          'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})
        done['subagents']['richard'][0]['dispatch_event_id'] = event['event_id']
        with self.assertRaisesRegex(ValueError, "literal string 'confirmed'.*got 'sealed'"):
            final_verification.run(self.root, done, 'arch')

    def test_stale_candidate_signature_names_the_expected_value_and_recovery_command(self):
        # Fix 3c (2026-09-23 self-improvement): the previous message ("0
        # independent approvals") gave no hint that the actual cause was a
        # wrong signature *scheme* (issue_candidates.py's own content-addressed
        # signature, not project.py::source_signature) -- this recurred
        # independently for both Bob and Richard in the source project.
        done = self.complete(qualify=False)
        richard_event_id = done['subagents']['richard'][0]['dispatch_event_id']
        original = next(r for r in records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
                        if r['event_id'] == richard_event_id)
        footer = copy.deepcopy(original['footer'])
        wrong_signature_scheme = issue_candidates.capture(self.root, self.issue, self.start['maintenance']['baseline'])['sha256']
        footer['candidate_signature'] = wrong_signature_scheme
        event = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': original['agent_id'], 'session_id': 'synthetic-session-3',
                                          'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})
        done['subagents']['richard'][0]['dispatch_event_id'] = event['event_id']
        with self.assertRaisesRegex(ValueError, re.escape(wrong_signature_scheme) + '.*project.py signature'):
            final_verification.run(self.root, done, 'arch')

    def test_missing_or_fabricated_completion_is_rejected(self):
        done = self.complete()
        done['subagents']['richard'][0]['dispatch_event_id'] = 'invented'
        self.save_done(done)
        with self.assertRaisesRegex(ValueError, 'exact completion'):
            self.gate.check_done()

    def test_stale_candidate_or_modified_log_cannot_pass(self):
        done = self.complete()
        receipt = verify.load_evidence(self.root, done['verification']['scientific'])
        (self.root / receipt['log']).write_text('fabricated PASS')
        with self.assertRaisesRegex(ValueError, 'log is missing or modified'):
            self.gate.check_done()

    def test_configured_source_additions_and_removals_invalidate_evidence(self):
        ref = verify.run(self.root, 'scientific', 'arch')['evidence']
        file = self.root / 'src/new_kernel.py'
        file.write_text('def unused():\n    return 1\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            verify.load_evidence(self.root, ref)
        file.unlink()
        self.assertEqual(verify.load_evidence(self.root, ref)['exit'], 0)
        (self.root / 'src/diffusion.py').unlink()
        with self.assertRaisesRegex(ValueError, 'stale'):
            verify.load_evidence(self.root, ref)

    def test_configurable_science_directories(self):
        cfg = project.config(self.root)
        (self.root / 'src').rename(self.root / 'analysis')
        cfg['source_paths'] = ['analysis']
        project.atomic_json(self.root / 'esx/project.json', cfg)
        inventory = doc_inventory.snapshot(self.root)
        self.assertIn('analysis/diffusion.py', inventory)
        self.assertNotIn('src/diffusion.py', inventory)

    def test_mirrored_paths_detects_drift_missing_and_stale_canonical(self):
        # Generalizes a real bug (self-improvement/improvements_2026-09-23_...):
        # a build step needing its own local copy of shared source, with no
        # import mechanism to keep copies in sync, silently drifting stale.
        canonical = self.root / 'src/diffusion.py'
        mirror = self.root / 'src/diffusion_mirror.py'
        mirror.write_bytes(canonical.read_bytes())
        cfg = project.config(self.root)
        cfg['mirrored_paths'] = [{'canonical': 'src/diffusion.py', 'mirrors': ['src/diffusion_mirror.py']}]
        project.atomic_json(self.root / 'esx/project.json', cfg)
        self.assertEqual(audit.check(self.root)['status'], 'PASS')
        mirror.write_text(mirror.read_text() + '\n# drifted\n')
        with self.assertRaisesRegex(ValueError, 'drifted from canonical source src/diffusion.py'):
            audit.check(self.root)
        mirror.unlink()
        with self.assertRaisesRegex(ValueError, 'missing entirely'):
            audit.check(self.root)

    def test_failing_and_empty_suites_cannot_supply_success(self):
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            verify.run(self.root, 'focused', 'prober', override=['{python}', '-c', 'raise SystemExit(7)'])
        cfg = project.config(self.root)
        cfg['verification']['focused'] = []
        project.atomic_json(self.root / 'esx/project.json', cfg)
        with self.assertRaisesRegex(ValueError, 'empty'):
            verify.run(self.root, 'focused', 'prober')

    def test_source_drift_during_successful_command_invalidates_run(self):
        argv = ['{python}', '-c', "from pathlib import Path; p=Path('src/diffusion.py'); p.write_text(p.read_text()+'\\n# drift\\n')"]
        with self.assertRaisesRegex(ValueError, 'source changed'):
            verify.run(self.root, 'focused', 'prober', override=argv)

    def test_external_input_bytes_invalidate_reuse(self):
        data = self.root.parent / 'observations.bin'
        data.write_bytes(b'first')
        cfg = project.config(self.root)
        cfg['external_inputs'] = [str(data)]
        project.atomic_json(self.root / 'esx/project.json', cfg)
        ref = verify.run(self.root, 'scientific', 'arch')['evidence']
        data.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'stale'):
            verify.load_evidence(self.root, ref)

    def test_navigation_and_documentation_drift_are_detected(self):
        self.prepare()
        base = self.start['maintenance']['baseline']
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text().replace('Return a new periodic', 'Return a fresh periodic'))
        with self.assertRaisesRegex(ValueError, 'stale'):
            maintenance.validate_orientation(self.root, self.start['maintenance']['orientation'], self.issue, base, 'arch')
        plan = maintenance.draft(self.root, self.issue, base)
        self.assertTrue(any(row['target'] == 'src/diffusion.py::step' for row in plan['changes']))
        with self.assertRaisesRegex(ValueError, 'documentation action'):
            maintenance.seal(self.root, plan)

    def test_fenced_records_and_missing_lesson_evidence(self):
        self.assertEqual(records.issues(self.root), {})
        (self.root / 'lessons_learned.md').write_text('# Lessons\n- [LL-001] Preserve mass.\n')
        with self.assertRaisesRegex(ValueError, 'lacks an evidence'):
            records.validate_records(self.root)

    def test_resume_events_preserve_distinct_completion_ids(self):
        event = {'agent_type': 'richard', 'agent_id': 'same-runtime', 'last_assistant_message': '```json\n{"agent":"richard"}\n```'}
        first, second = hooks.capture(self.root, event), hooks.capture(self.root, event)
        self.assertEqual(first['agent_id'], second['agent_id'])
        self.assertNotEqual(first['event_id'], second['event_id'])

    def test_untested_configuration_and_output_overlap_are_rejected(self):
        cfg = project.config(self.root)
        cfg['output_paths'] = ['src']
        project.atomic_json(self.root / 'esx/project.json', cfg)
        with self.assertRaisesRegex(ValueError, 'hide configured'):
            project.config(self.root)

    def test_conservation_fault_is_detected_by_the_actual_scientific_oracle(self):
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text().replace('- 2*x +', '- 2.01*x +'))
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            verify.run(self.root, 'scientific', 'arch')

    def test_full_suite_can_be_reused_but_missing_logs_require_execution(self):
        first = verify.run(self.root, 'scientific', 'arch')
        second = verify.run(self.root, 'scientific', 'arch')
        self.assertEqual(second['status'], 'REUSED EVIDENCE')
        self.assertEqual(first['evidence'], second['evidence'])
        evidence = verify.load_evidence(self.root, first['evidence'])
        (self.root / evidence['log']).unlink()
        self.assertEqual(verify.run(self.root, 'scientific', 'arch')['status'], 'EXECUTED PASS')

    def test_partial_and_blocked_iterations_preserve_unfinished_work(self):
        self.prepare(kind='investigation')
        done = {'state_version': self.start['state_version'], 'iteration': self.start['iteration'], 'id': self.issue, 'timestamp': self.start['timestamp'], 'outcome': 'partial', 'summary': 'Measured a bounded witness.',
                'workflow': self.start['workflow'], 'scope_decisions': [], 'subagents': {},
                'maintenance': self.start['maintenance'],
                'git': {'committed': False, 'reason': 'The investigation retains its working evidence without a commit.'},
                'communication': {'status': 'disabled', 'detail': 'No external announcements during this test.'},
                'next_step': 'Obtain the approved external reference dataset.'}
        self.save_done(done)
        self.assertEqual(self.gate.check_done()['outcome'], 'partial')
        path = self.root / 'open_issues.md'
        path.write_text(path.read_text().replace('UNRESOLVED:', 'BLOCKED:').replace('**Status**: Unresolved', '**Status**: Blocked')
                        + '**Blocked-By**: EXTERNAL — reference dataset is unavailable\n')
        done.update(outcome='blocked', blocked_by='EXTERNAL — reference dataset is unavailable')
        self.save_done(done)
        self.assertEqual(self.gate.check_done()['outcome'], 'blocked')

    def test_promise_requires_active_loop_and_no_actionable_issues(self):
        gate = loop_gate.Gate(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.next(), 4)
        self.assertNotIn(loop_gate.PROMISE, output.getvalue())
        (self.root / '.claude/esx-loop.local.md').write_text('---\nactive: true\niteration: 1\nmax_iterations: 10\ncompletion_promise: ESX-LOOP-NO-ACTIONABLE-WORK\n---\nContinue.\n')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.next(), 3)
        self.assertIn(loop_gate.PROMISE, output.getvalue())
        self.write_issue()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.next(), 0)
        self.assertNotIn(loop_gate.PROMISE, output.getvalue())

    def test_failed_fresh_run_invalidates_a_previous_matching_pass(self):
        argv = ['{python}', '-c', "from pathlib import Path; raise SystemExit(int(Path('results/fail').exists()))"]
        verify.run(self.root, 'focused', 'prober', override=argv)
        (self.root / 'results').mkdir()
        (self.root / 'results/fail').touch()
        for fresh in (True, False):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                verify.run(self.root, 'focused', 'prober', fresh=fresh, override=argv)

    def test_isolated_worktrees_do_not_enter_primary_source_inventory(self):
        nested = self.root / '.claude/worktrees/other/src'
        nested.mkdir(parents=True)
        (nested / 'unrelated.py').write_text('print("isolated")\n')
        self.assertFalse(any('worktrees' in p for p in doc_inventory.snapshot(self.root)))

    def test_source_symlink_outside_project_is_refused(self):
        external = self.root.parent / 'outside.py'
        external.write_text('value = 1\n')
        (self.root / 'src/outside.py').symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'leaves project'):
            project.source_signature(self.root)



    def test_loop_artifacts_leave_source_signature_unchanged(self):
        before = project.source_signature(self.root)
        for name in ('esx-loop.local.md', 'esx-loop.lock', 'esx-loop-exit.log',
                     'esx-loop.cancelled.md', 'ralph-loop-exit.log'):
            (self.root / '.claude' / name).write_text('mutable runtime bytes')
        self.assertEqual(project.source_signature(self.root), before)

    def test_nonfinite_timeouts_are_refused(self):
        for timeout in (float('inf'), float('nan'), 0, True):
            cfg = json.loads((self.root / 'esx/project.json').read_text())
            cfg['command_timeout_seconds'] = timeout
            project.atomic_json(self.root / 'esx/project.json', cfg)
            with self.assertRaisesRegex(ValueError, 'finite and positive'):
                project.config(self.root)

    def test_duplicate_stop_handler_blocks_deployment_before_writes(self):
        target = self.root.parent / 'bad-hook'
        (target / '.claude').mkdir(parents=True)
        original = json.dumps({'hooks': {'Stop': [{'hooks': [{'type': 'command',
            'command': 'python3 tools/esx/ralph_stop.py'}]}]}})
        (target / '.claude/settings.json').write_text(original)
        with self.assertRaisesRegex(ValueError, 'existing ESX Stop hook differs'):
            deploy.deploy(target, apply=True)
        self.assertEqual((target / '.claude/settings.json').read_text(), original)
        self.assertFalse((target / 'tools').exists())

    def test_missing_canonical_stop_is_detected(self):
        path = self.root / '.claude/settings.json'
        cfg = json.loads(path.read_text())
        del cfg['hooks']['Stop']
        project.atomic_json(path, cfg)
        with self.assertRaisesRegex(ValueError, 'exactly one canonical ESX Stop'):
            audit.check(self.root)


if __name__ == '__main__':
    unittest.main()
