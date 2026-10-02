#!/usr/bin/env python3
"""1.5.3: native in-flight tracking and friction reported by MITgcm_new_runoff (no provider calls)."""
import argparse
from contextlib import redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'template/tools/esx'))
import doc_contract  # noqa: E402
import project  # noqa: E402
import ralph_stop as hook  # noqa: E402
import runtime_recovery as recovery  # noqa: E402
spec = importlib.util.spec_from_file_location('esx_hooks', ROOT / 'template/tools/esx/hooks.py')
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)
spec = importlib.util.spec_from_file_location('agent_runtime', ROOT / 'template/tools/esx/agent_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class Temp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class NativeInFlightTests(Temp):
    def test_start_marker_holds_the_loop_until_stop_for_the_same_session_only(self):
        hooks.started(self.root, {'agent_id': 'a847', 'agent_type': 'bob', 'session_id': 'arch'})
        self.assertTrue(hook.native_in_flight(self.root, 'arch'))
        self.assertFalse(hook.native_in_flight(self.root, 'other-session'))
        with patch.object(runtime, 'stop_record', return_value={}), \
                patch.dict(sys.modules, {'agent_runtime': runtime}):
            hooks.capture(self.root, {'agent_id': 'a847', 'session_id': 'arch'})
        self.assertFalse(hook.native_in_flight(self.root, 'arch'))

    def test_stale_marker_and_unsafe_ids_are_ignored(self):
        hooks.started(self.root, {'agent_id': 'old', 'session_id': 'arch'})
        marker = self.root / 'devel-loop/loop_state/native_inflight/old.json'
        past = time.time() - hook.NATIVE_STALE_SECONDS - 5
        os.utime(marker, (past, past))
        self.assertFalse(hook.native_in_flight(self.root, 'arch'))
        with self.assertRaises(ValueError):
            hooks.started(self.root, {'agent_id': '../escape', 'session_id': 'arch'})

    def test_stop_is_allowed_quietly_while_a_native_subagent_runs(self):
        """No block (the CLI shows one as "Stop hook error"), no advance, no wait count."""
        (self.root / '.claude').mkdir()
        state = self.root / '.claude/esx-loop.local.md'
        state.write_text('---\nactive: true\niteration: 2\nmax_iterations: 5\n'
                         'completion_promise: "DONE"\n---\nContinue.\n')
        before = state.read_text()
        hooks.started(self.root, {'agent_id': 'bob1', 'agent_type': 'bob', 'session_id': 'arch'})
        for _ in range(hook.MAX_DISPATCH_WAITS + 2):  # holding is not capped: nothing is consumed
            with redirect_stderr(io.StringIO()):
                result = hook.step(self.root, {'session_id': 'arch', 'last_assistant_message': 'waiting'})
            self.assertNotIn('decision', result)
            self.assertIn('bob', result['systemMessage'])
            self.assertIn('nothing is wrong', result['systemMessage'])
        self.assertEqual(state.read_text(), before)
        self.assertIn('HOLD', (self.root / '.claude/esx-loop-exit.log').read_text())
        with patch.object(runtime, 'stop_record', return_value={}), \
                patch.dict(sys.modules, {'agent_runtime': runtime}):
            hooks.capture(self.root, {'agent_id': 'bob1', 'session_id': 'arch'})
        with redirect_stderr(io.StringIO()):
            result = hook.step(self.root, {'session_id': 'arch', 'last_assistant_message': 'bob reported'})
        self.assertEqual(result['decision'], 'block')  # the loop continues once the subagent has reported
        self.assertIn('iteration: 3', state.read_text())


class InterpreterTests(Temp):
    def test_configured_python_resolves_placeholder(self):
        self.assertEqual(project.command(['{python}', '-V'], {'python': '/opt/env/bin/python3'})[0],
                         '/opt/env/bin/python3')
        self.assertEqual(project.command(['{python}', '-V'])[0], sys.executable)

    def test_failed_toolchain_probe_names_interpreter_and_remedy(self):
        cfg = {'toolchain_commands': [['{python}', '-c', 'import numpy_that_does_not_exist']],
               'external_inputs': [], 'environment_variables': []}
        with self.assertRaises(ValueError) as caught:
            project.environment(self.root, cfg)
        message = str(caught.exception)
        self.assertIn(sys.executable, message)
        self.assertIn('ModuleNotFoundError', message)
        self.assertIn('set "python" in esx/project.json', message)


class ReferenceArgumentTests(Temp):
    def test_inline_json_and_ref_file_path_are_both_accepted(self):
        ref = {'path': 'devel-loop/loop_state/maintenance/x.json', 'sha256': 'ab' * 32}
        self.assertEqual(doc_contract.parse_ref(json.dumps(ref)), ref)
        path = self.root / 'ref.json'
        path.write_text(json.dumps(ref) + '\n')
        self.assertEqual(doc_contract.parse_ref(str(path)), ref)
        for bad in (str(self.root / 'missing.json'), '{"path": 1}', '{broken'):
            with self.assertRaises(argparse.ArgumentTypeError):
                doc_contract.parse_ref(bad)


class ReviewOutcomeTests(unittest.TestCase):
    error = ['approval needs a successful executed check and no must_fix findings']

    def test_approve_with_must_fix_is_changes_requested(self):
        footer = {'verdict': 'APPROVE_WITH_FIXES', 'must_fix': ['fix the docstring']}
        self.assertEqual(runtime.changes_requested('richard', footer, self.error), 'changes_requested')

    def test_other_defects_or_roles_are_not_relabelled(self):
        footer = {'verdict': 'APPROVE_WITH_FIXES', 'must_fix': ['x']}
        self.assertIsNone(runtime.changes_requested('richard', footer, self.error + ['stale orientation']))
        self.assertIsNone(runtime.changes_requested('bob', footer, self.error))
        self.assertIsNone(runtime.changes_requested('richard', dict(footer, must_fix=[]), self.error))


class PermissionTransitionTests(Temp):
    def contract(self, settings):
        path = self.root / 'settings.local.json'
        if settings is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(settings))
        return {'sha256': json.dumps(settings), 'effective_manifest': recovery.manifest([path])}

    def classify(self, before, after):
        old, new = self.contract(before), self.contract(after)
        state = {'session_id': 's', 'issue_id': 'I', 'runtime_fingerprint': old['sha256'], 'runtime_contract': old}
        try:
            return recovery.compatibility(self.root, state, new)['classification']
        except ValueError:
            return 'assessment_required'

    def test_only_allow_additions_skip_assessment(self):
        base = {'permissions': {'allow': ['Bash(ls *)'], 'deny': ['Bash(rm *)']}}
        more = {'permissions': {'allow': ['Bash(ls *)', 'Bash(pytest *)'], 'deny': ['Bash(rm *)']}}
        self.assertEqual(self.classify(base, more), 'permission_additions')
        self.assertEqual(self.classify(None, {'permissions': {'allow': ['Bash(ls *)']}}), 'permission_additions')

    def test_removals_deny_mode_and_hook_changes_still_need_assessment(self):
        base = {'permissions': {'allow': ['Bash(ls *)', 'Bash(cat *)'], 'deny': []}}
        for after in ({'permissions': {'allow': ['Bash(ls *)'], 'deny': []}},
                      {'permissions': {'allow': ['Bash(ls *)', 'Bash(cat *)'], 'deny': ['Bash(cat *)']}},
                      {'permissions': {'allow': ['Bash(ls *)', 'Bash(cat *)'], 'deny': [],
                                       'defaultMode': 'bypassPermissions'}},
                      dict(base, hooks={'Stop': []})):
            self.assertEqual(self.classify(base, after), 'assessment_required', after)


class ForeignStopTests(Temp):
    """A bare `claude --print` in the project dir must not drive the owner's loop."""

    def state(self, owner=True):
        (self.root / '.claude').mkdir(exist_ok=True)
        path = self.root / '.claude/esx-loop.local.md'
        path.write_text('---\nactive: true\niteration: 2\nmax_iterations: 6\ncompletion_promise: "DONE"\n'
                        + ('owner_session: owner-session-1\n' if owner else '') + '---\nContinue.\n')
        return path

    def step(self, **event):
        with redirect_stderr(io.StringIO()):
            return hook.step(self.root, event)

    def test_foreign_session_cannot_advance_or_end_the_loop(self):
        path = self.state()
        before = path.read_text()
        self.assertEqual(self.step(session_id='someone-else-99', last_assistant_message='x'), {})
        self.assertEqual(self.step(session_id='someone-else-99', last_assistant_message='<promise>DONE</promise>'), {})
        self.assertEqual(path.read_text(), before)

    def test_owner_session_still_drives_the_loop(self):
        path = self.state()
        result = self.step(session_id='owner-session-1', last_assistant_message='working')
        self.assertEqual(result['decision'], 'block')
        self.assertIn('iteration: 3', path.read_text())

    def test_unowned_legacy_state_keeps_previous_behaviour(self):
        path = self.state(owner=False)
        result = self.step(session_id='anyone-1234', last_assistant_message='working')
        self.assertEqual(result['decision'], 'block')
        self.assertIn('iteration: 3', path.read_text())

    def test_start_records_and_run_rebinds_owner(self):
        import loop_control
        (self.root / 'devel-loop').mkdir()
        (self.root / 'devel-loop/autonomous_prompt.md').write_text('Continue.\n')
        with patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': 'owner-session-1'}), \
                patch('check_ralph_hook.check', return_value=None):
            loop_control.start(self.root, 'Continue.\n', 5)
        text = (self.root / '.claude/esx-loop.local.md').read_text()
        self.assertIn('owner_session: owner-session-1', text)
        with patch.dict(os.environ, {'CLAUDE_CODE_SESSION_ID': 'new-owner-2222'}):
            self.assertEqual(loop_control.bind_owner(self.root), 'new-owner-2222')
        text = (self.root / '.claude/esx-loop.local.md').read_text()
        self.assertIn('owner_session: new-owner-2222', text)
        self.assertEqual(text.count('owner_session'), 1)


if __name__ == '__main__':
    unittest.main()
