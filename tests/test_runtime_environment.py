"""1.6.0 runtime: CLI patch updates, shell-independent evidence, lessons at prepare.

Offline: no provider calls and no real Claude CLI.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'template/tools/esx'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402
import runtime_recovery as recovery  # noqa: E402


class Temp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class CliPatchUpdateTests(Temp):
    def contract(self, version, **extra):
        settings = self.root / 'settings.local.json'
        settings.write_text(json.dumps({'permissions': {'allow': ['Bash(ls *)']}}))
        body = {'binary': f'/opt/claude/versions/{version}', 'binary_sha256': 'sha-' + version,
                'version': f'{version} (Claude Code)', 'environment': {}, 'transport': 'claude_cli_session',
                'permission_mode': 'inherited_settings', 'effective_manifest': recovery.manifest([settings])}
        body.update(extra)
        return dict(body, sha256=json.dumps(body, sort_keys=True))

    def state(self, contract):
        return {'session_id': 's', 'issue_id': 'I', 'runtime_fingerprint': contract['sha256'], 'runtime_contract': contract}

    PASSED = {'status': 'passed', 'reused_evidence': True, 'evidence': {'path': 'probes/x.json', 'sha256': 'ab'}}

    def test_patch_update_with_a_passing_probe_needs_no_assessment(self):
        old, new = self.contract('2.1.285'), self.contract('2.1.286')
        result = recovery.compatibility(self.root, self.state(old), new, probe=lambda: self.PASSED)
        self.assertEqual(result['classification'], 'cli_patch_update')
        self.assertEqual(result['probe'], self.PASSED['evidence'])
        self.assertEqual(result['versions'], ['2.1.285 (Claude Code)', '2.1.286 (Claude Code)'])

    def test_patch_update_without_a_passing_probe_says_to_run_one(self):
        old, new = self.contract('2.1.285'), self.contract('2.1.286')
        for probe in (None, lambda: {'status': 'missing'}, lambda: {'status': 'failed', 'evidence': {'path': 'p'}}):
            with self.assertRaisesRegex(ValueError, r'2\.1\.285.*2\.1\.286.*agent_runtime\.py probe'):
                recovery.compatibility(self.root, self.state(old), new, probe=probe)

    def test_minor_bumps_downgrades_and_any_other_change_still_need_assessment(self):
        old = self.contract('2.1.285')
        for new in (self.contract('2.2.0'), self.contract('3.0.0'), self.contract('2.1.284'),
                    self.contract('2.1.286', environment={'ANTHROPIC_MODEL': 'x'}),
                    self.contract('2.1.286', permission_mode='bypassPermissions')):
            with self.assertRaisesRegex(ValueError, 'assess-transition with exact session'):
                recovery.compatibility(self.root, self.state(old), new, probe=lambda: self.PASSED)

    def test_the_probe_is_not_consulted_for_other_classifications(self):
        old = self.contract('2.1.285')

        def never():
            raise AssertionError('probe consulted')
        self.assertEqual(recovery.compatibility(self.root, self.state(old), old, probe=never)['classification'], 'unchanged')


class PinnedEnvironmentTests(Temp):
    def conda(self, name=None):
        root = self.root / 'miniforge3'
        prefix = root / 'envs' / name if name else root
        (prefix / 'conda-meta').mkdir(parents=True)
        return root, prefix

    def facts(self, prefix, base=None):
        return {'version': '3.12.1 (pinned)', 'optimize': 0, 'prefix': str(prefix), 'base_prefix': str(base or prefix)}

    CFG = {'python': '/pinned/python3', 'environment_variables': ['CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'VIRTUAL_ENV', 'PATH', 'LANG']}

    def test_evidence_is_the_same_from_the_base_shell_and_the_activated_environment(self):
        root, prefix = self.conda('ecco')
        base_shell = {'CONDA_PREFIX': str(root), 'CONDA_DEFAULT_ENV': 'base', 'LANG': 'C.UTF-8',
                      'PATH': os.pathsep.join([str(root / 'bin'), str(root / 'condabin'), '/usr/bin', '/bin'])}
        activated = {'CONDA_PREFIX': str(prefix), 'CONDA_DEFAULT_ENV': 'ecco', 'LANG': 'C.UTF-8',
                     'PATH': os.pathsep.join([str(prefix / 'bin'), str(root / 'condabin'), '/usr/bin', '/bin'])}
        measured = []
        for shell in (base_shell, activated):
            with patch.object(project, 'pinned_facts', return_value=self.facts(prefix)), \
                    patch.dict(os.environ, shell, clear=True):
                measured.append(project.measured_variables(self.CFG))
        self.assertEqual(measured[0], measured[1])
        self.assertEqual(measured[0]['CONDA_PREFIX'], str(prefix))
        self.assertEqual(measured[0]['CONDA_DEFAULT_ENV'], 'ecco')
        self.assertIsNone(measured[0]['VIRTUAL_ENV'])
        self.assertEqual(measured[0]['PATH'], os.pathsep.join([str(prefix / 'bin'), '/usr/bin', '/bin']))

    def test_a_real_difference_outside_the_activation_still_changes_the_evidence(self):
        root, prefix = self.conda('ecco')
        values = []
        for extra in ('/usr/bin', '/opt/other-compiler/bin:/usr/bin'):
            with patch.object(project, 'pinned_facts', return_value=self.facts(prefix)), \
                    patch.dict(os.environ, {'PATH': extra, 'LANG': 'C'}, clear=True):
                values.append(project.measured_variables(self.CFG)['PATH'])
        self.assertNotEqual(values[0], values[1])

    def test_without_a_pin_the_calling_shell_is_recorded_as_before(self):
        cfg = {'environment_variables': ['CONDA_PREFIX', 'PATH']}
        with patch.dict(os.environ, {'CONDA_PREFIX': '/somewhere', 'PATH': '/a:/b'}, clear=True):
            self.assertEqual(project.measured_variables(cfg), {'CONDA_PREFIX': '/somewhere', 'PATH': '/a:/b'})
        self.assertIsNone(project.pinned_facts(cfg))

    def test_the_pinned_interpreter_is_measured_not_the_one_running_the_tool(self):
        facts = project.pinned_facts({'python': sys.executable})
        self.assertEqual(facts['version'], sys.version)
        self.assertEqual(facts['prefix'], sys.prefix)
        with self.assertRaisesRegex(ValueError, 'cannot run'):
            project.pinned_facts({'python': str(self.root / 'missing-python')})

    def test_a_virtual_environment_pin_sets_virtual_env_only(self):
        venv = self.root / 'venv'
        venv.mkdir()
        with patch.object(project, 'pinned_facts', return_value=self.facts(venv, base='/usr')), \
                patch.dict(os.environ, {'PATH': '/usr/bin', 'CONDA_PREFIX': '/stale'}, clear=True):
            values = project.measured_variables(self.CFG)
        self.assertEqual(values['VIRTUAL_ENV'], str(venv))
        self.assertIsNone(values['CONDA_PREFIX'])
        self.assertEqual(values['PATH'], '/usr/bin')


class KitHygieneTests(unittest.TestCase):
    def test_template_tools_import_no_project_specific_module(self):
        for path in (ROOT / 'template/tools/esx').glob('*.py'):
            self.assertNotIn('adx_workflow', path.read_text(), path.name)


class LessonNoticeTests(unittest.TestCase):
    def test_prepare_lists_active_lessons_with_their_triggers(self):
        import test_framework
        import loop_gate
        fixture = test_framework.FrameworkTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        gate = loop_gate.Gate(fixture.root)
        self.assertEqual(gate.lesson_notices(), [])  # the template's placeholder entry is not a lesson
        (fixture.root / 'lessons_learned.md').write_text(
            '# Active lessons\n\n- [LL-001] Run a live probe after every kit upgrade; high confidence.\n'
            '  Trigger: any ESX upgrade or CLI update\n- [LL-002] A lesson without a trigger line.\n')
        notices = gate.lesson_notices()
        self.assertEqual(notices[0], 'LESSON [LL-001] Run a live probe after every kit upgrade; high confidence. '
                                     'Trigger: any ESX upgrade or CLI update')
        self.assertEqual(notices[1], 'LESSON [LL-002] A lesson without a trigger line.')
        self.assertIn('which of these triggers apply', notices[2])


if __name__ == '__main__':
    unittest.main()
