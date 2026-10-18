#!/usr/bin/env python3
"""Exercise bounded continuation and actual Claude transcript block shapes."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "template/tools/esx"))
import ralph_stop as hook


def assistant(text=None, identity=None, blocks=None):
    message = {'role': 'assistant', 'content': blocks if blocks is not None else [
        {'type': 'text', 'text': text}]}
    if identity:
        message['id'] = identity
    return {'type': 'assistant', 'message': message}


def user(text='Continue the issue.'):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def verification_script(root, seconds):
    script = root / 'tools/esx/final_verification.py'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f'import time\ntime.sleep({seconds})\n')
    return script


def launch_detached(root, script):
    """Launch `script` the way a detached final verification is launched.

    A launcher Popens it with start_new_session=True and exits at once, so the
    run is reparented to PID 1 and has no ancestor in this process tree.
    """
    marker = root / 'detached.pid'
    launcher = ('import subprocess, sys\n'
                f'p = subprocess.Popen([sys.executable, {str(script)!r}], cwd={str(root)!r},\n'
                '                     start_new_session=True, stdin=subprocess.DEVNULL,\n'
                '                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n'
                f'open({str(marker)!r}, "w").write(str(p.pid))\n')
    subprocess.run([sys.executable, '-c', launcher], check=True)
    return int(marker.read_text())


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    return predicate()


class StopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.claude').mkdir()
        self.state = self.root / '.claude/esx-loop.local.md'
        self.transcript = self.root / 'transcript.jsonl'
        self.write_state()

    def write_state(self, iteration='1', limit='3', prompt='Run the next bounded step.\n', promise='"DONE"'):
        self.state.write_text(f'---\nactive: true\niteration: {iteration}\n'
                              f'max_iterations: {limit}\ncompletion_promise: {promise}\n---\n{prompt}')

    def rows(self, *rows):
        self.transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def step(self):
        with redirect_stderr(io.StringIO()):
            return hook.step(self.root, {'transcript_path': str(self.transcript)})

    def cli(self, cwd=None, project=None, hook_input=None):
        """Run the hook with explicit scratch-only project selection.

        Claude exports CLAUDE_PROJECT_DIR to its shell tools. Inheriting that
        value here would let the hook update the calling project's live loop.
        """
        env = dict(os.environ)
        env.pop('CLAUDE_PROJECT_DIR', None)
        env.pop('ESX_RALPH_PROJECT_DIR', None)
        env.pop('ESX_AGENT_RUNTIME_CHILD', None)
        if project is not None:
            env['CLAUDE_PROJECT_DIR'] = str(project)
        return subprocess.run([sys.executable, '-B', str(Path(hook.__file__).resolve())],
                              cwd=cwd or self.root,
                              input=json.dumps(hook_input if hook_input is not None else {
                                  'transcript_path': str(self.transcript)}),
                              text=True, capture_output=True, timeout=5, env=env)

    def test_plain_promise_word_is_ordinary_prose(self):
        self.rows(user(), assistant('The earlier example used DONE.'))
        result = self.step()
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 2)

    def test_current_tagged_promise_ends_and_preserves_state_evidence(self):
        original = self.state.read_bytes()
        self.rows(user(), assistant('<promise> DONE </promise>'))
        self.assertNotIn('decision', self.step())
        self.assertFalse(self.state.exists())
        archived = list(self.state.parent.glob('esx-loop.local.md.end.*'))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), original)
        self.assertIn('current completion promise fulfilled',
                      (self.state.parent / 'esx-loop-exit.log').read_text())

    def test_old_promise_before_a_new_user_turn_does_not_end_loop(self):
        self.rows(user('Earlier task'), assistant('<promise>DONE</promise>'),
                  user('A new bounded task'), assistant('Work remains.'))
        self.assertEqual(self.step()['decision'], 'block')

    def test_earlier_assistant_promise_is_replaced_by_newer_answer(self):
        self.rows(user(), assistant('<promise>DONE</promise>', 'old'),
                  assistant('The check found another failure.', 'new'))
        self.assertEqual(self.step()['decision'], 'block')

    def test_trailing_thinking_and_tool_results_do_not_erase_final_text(self):
        self.rows(user(), assistant('<promise>DONE</promise>', 'final'),
                  assistant(identity='final', blocks=[{'type': 'thinking', 'thinking': 'opaque'}]),
                  {'type': 'user', 'message': {'role': 'user', 'content': [
                      {'type': 'tool_result', 'tool_use_id': 't1', 'content': 'result'}]}})
        self.assertNotIn('decision', self.step())
        self.assertFalse(self.state.exists())

    def test_one_final_message_can_have_multiple_text_blocks(self):
        self.rows(user(), assistant(blocks=[{'type': 'text', 'text': '<promise>DONE</promise>'},
                                            {'type': 'text', 'text': 'The evidence is saved.'}]))
        self.assertNotIn('decision', self.step())
        self.assertFalse(self.state.exists())

    def test_serialized_content_blocks_with_same_message_id_are_combined(self):
        self.rows(user(), assistant('<promise>', 'final'), assistant('DONE</promise>', 'final'),
                  assistant('The evidence is saved.', 'final'))
        self.assertNotIn('decision', self.step())

    def test_tag_in_tool_result_cannot_fulfill_the_promise(self):
        self.rows(user(), assistant('Still inspecting.'),
                  {'type': 'user', 'message': {'role': 'user', 'content': [
                      {'type': 'tool_result', 'content': '<promise>DONE</promise>'}]}})
        self.assertEqual(self.step()['decision'], 'block')

    def test_missing_or_malformed_transcript_continues_with_budget(self):
        for content in (None, '{"truncated":', 'null\n', '\ufffd'):
            with self.subTest(content=content):
                self.write_state()
                if content is None:
                    self.transcript.unlink(missing_ok=True)
                else:
                    self.transcript.write_text(content)
                self.assertEqual(self.step()['decision'], 'block')
                self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 2)

    def test_finite_budget_stops_even_when_transcript_is_unavailable(self):
        self.write_state(iteration='3', limit='3')
        self.assertNotIn('decision', self.step())
        self.assertFalse(self.state.exists())
        self.assertIn('budget 3 reached', (self.state.parent / 'esx-loop-exit.log').read_text())

    def test_malformed_budget_or_prompt_suspends_with_original_state(self):
        for limit, prompt in [('oops', 'Continue'), ('-1', 'Continue'), ('', 'Continue'), ('3', '\n')]:
            with self.subTest(limit=limit, prompt=prompt):
                self.write_state(limit=limit, prompt=prompt)
                original = self.state.read_bytes()
                result = self.step()
                self.assertNotIn('decision', result)
                self.assertFalse(self.state.exists())
                self.assertTrue(any(p.read_bytes() == original for p in
                                    self.state.parent.glob('esx-loop.local.md.suspend.*')))

    def test_duplicate_counter_and_invalid_active_are_suspended(self):
        for extra in ('iteration: 1\n', 'active: maybe\n'):
            self.write_state()
            self.state.write_text(self.state.read_text().replace('---\nactive:', '---\n' + extra + 'active:', 1))
            self.assertNotIn('decision', self.step())
            self.assertFalse(self.state.exists())

    def test_cancellation_and_inactive_state_are_respected(self):
        self.state.unlink()
        self.assertEqual(self.step(), {})
        self.write_state()
        self.state.write_text(self.state.read_text().replace('active: true', 'active: false'))
        original = self.state.read_bytes()
        self.assertEqual(self.step(), {})
        self.assertEqual(self.state.read_bytes(), original)

    def test_counter_write_failure_suspends_with_preserved_original(self):
        self.rows(user(), assistant('More work remains.'))
        original = self.state.read_bytes()
        with patch.object(hook.os, 'replace', side_effect=OSError('disk write refused')):
            result = self.step()
        self.assertNotIn('decision', result)
        self.assertFalse(self.state.exists())
        archived = list(self.state.parent.glob('esx-loop.local.md.suspend.*'))
        self.assertEqual(archived[0].read_bytes(), original)
        self.assertIn('cannot persist next iteration', result['systemMessage'])

    def test_replaced_state_is_never_overwritten_by_prior_turn(self):
        self.rows(user(), assistant('More work remains.'))
        real = hook.current_text
        replacement = 'New loop belongs to a separate user request.\n'
        def replace_state(path):
            self.state.write_text(replacement)
            return real(path)
        with patch.object(hook, 'current_text', side_effect=replace_state):
            self.assertEqual(self.step(), {})
        self.assertEqual(self.state.read_text(), replacement)

    def test_whitespace_accepted_in_counter_field_is_also_updated(self):
        self.rows(user(), assistant('More work remains.'))
        self.state.write_text(self.state.read_text().replace('iteration: 1', '  iteration : 1'))
        self.assertEqual(self.step()['decision'], 'block')
        self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 2)

    def test_prompt_bytes_and_quoted_promise_are_preserved(self):
        prompt = '\nContinue the "quoted" experiment.\n\nKeep the intended line breaks.\n'
        self.write_state(prompt=prompt, promise="'ALL DONE'")
        self.rows(user(), assistant('Work remains.'))
        self.assertEqual(self.step()['reason'], prompt)
        self.assertEqual(hook.parse_state(self.state.read_text())['prompt'], prompt)

    def test_transcript_tail_without_current_user_boundary_cannot_stop(self):
        self.transcript.write_text(json.dumps(user()) + '\n' +
            json.dumps(assistant('x' * (2 * 1024 * 1024))) + '\n' +
            json.dumps(assistant('<promise>DONE</promise>')) + '\n')
        self.assertEqual(self.step()['decision'], 'block')

    def test_cli_emits_valid_hook_json(self):
        self.rows(user(), assistant('Work remains.'))
        result = self.cli(project=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['decision'], 'block')

    def test_cli_from_subdirectory_uses_explicit_project_root(self):
        self.rows(user(), assistant('Work remains.'))
        subdirectory = self.root / 'nested/work'
        subdirectory.mkdir(parents=True)
        for signal in ('environment', 'payload'):
            with self.subTest(signal=signal):
                self.write_state()
                payload = {'transcript_path': str(self.transcript)}
                if signal == 'payload':
                    payload['cwd'] = str(self.root)
                result = self.cli(cwd=subdirectory,
                                  project=self.root if signal == 'environment' else None,
                                  hook_input=payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['decision'], 'block')
                self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 2)

    def test_scratch_cli_does_not_inherit_calling_projects_live_loop(self):
        self.rows(user(), assistant('Work remains.'))
        with tempfile.TemporaryDirectory() as other:
            other_root = Path(other)
            (other_root / '.claude').mkdir()
            other_state = other_root / '.claude/esx-loop.local.md'
            original = self.state.read_bytes()
            other_state.write_bytes(original)
            with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': str(other_root)}):
                result = self.cli(project=self.root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'block')
            self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 2)
            self.assertEqual(other_state.read_bytes(), original)

    def test_project_signal_without_state_never_mutates_another_project(self):
        self.rows(user(), assistant('Work remains.'))
        with tempfile.TemporaryDirectory() as other:
            result = self.cli(project=other, hook_input={
                'cwd': other, 'transcript_path': str(self.transcript)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(hook.parse_state(self.state.read_text())['iteration'], 1)
            self.assertFalse((Path(other) / '.claude').exists())

    def test_empty_project_does_not_use_handlers_repository_state(self):
        original = self.state.read_bytes()
        with tempfile.TemporaryDirectory() as other:
            result = self.cli(cwd=other, project=other, hook_input={'cwd': other})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(self.state.read_bytes(), original)
            self.assertFalse((Path(other) / '.claude').exists())

    def test_verification_run_holds_the_iteration(self):
        """A live verification run in this checkout is detected; one elsewhere is not."""
        script = verification_script(self.root, 30)
        other = self.root / 'other'
        other.mkdir()
        foreign_script = verification_script(other, 30)
        proc = subprocess.Popen([sys.executable, str(script)], cwd=self.root)
        foreign = subprocess.Popen([sys.executable, str(foreign_script)], cwd=other)
        try:
            found = wait_for(lambda: hook.verification_running(self.root))
            self.assertEqual([r['script'] for r in found], ['tools/esx/final_verification.py'])
            self.assertEqual(found[0]['pid'], proc.pid)
            # The same script running in another checkout is not this loop's work.
            # Wait for the second process too: under load it can still be starting when the first is visible.
            seen = wait_for(lambda: hook.verification_running(other))
            self.assertEqual([r['pid'] for r in seen], [foreign.pid])
            self.assertEqual(len(hook.verification_running(self.root)), 1)
        finally:
            proc.kill()
            foreign.kill()
            proc.wait()
            foreign.wait()
        self.assertEqual(hook.verification_running(self.root), [])

    def test_verification_hold_releases_and_does_not_stall(self):
        """A detached run must not let the loop stop on a promise nobody keeps.

        Checks the release as well as the hold: once the run is gone the loop
        must advance and clear its wait counter.
        """
        self.write_state(iteration='3', limit='20', promise='null')
        self.rows(user(), assistant('Work remains.'))
        script = verification_script(self.root, 30)
        # This process stands in for the session's `claude` process.
        with patch.object(hook, 'session_process', lambda start=None: os.getpid()):
            # 1. Untracked: block, naming the real process, without spending the iteration.
            pid = launch_detached(self.root, script)
            try:
                self.assertTrue(wait_for(lambda: hook.verification_running(self.root)))
                # Orphans are adopted by PID 1 or, under WSL2 and some containers, by a subreaper; either way
                # the run must not descend from this test process.
                self.assertFalse(hook.descends_from(pid, os.getpid()), 'the launch must reproduce the detached form')
                self.assertEqual([r['pid'] for r in hook.untracked_runs(hook.verification_running(self.root))], [pid])
                result = self.step()
                self.assertEqual(result.get('decision'), 'block', result)
                self.assertIn(f'tail --pid={pid}', result['reason'])
                self.assertIn('run_in_background', result['reason'])
                self.assertNotIn('nothing is wrong', json.dumps(result))
                self.assertIn('verify_waits: 1', self.state.read_text())
                self.assertIn('iteration: 3', self.state.read_text())
            finally:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass

            # 2. Released: the loop advances and the counter is cleared.
            self.assertTrue(wait_for(lambda: not hook.verification_running(self.root)))
            self.step()
            text = self.state.read_text()
            self.assertIn('iteration: 4', text)
            self.assertNotIn('verify_waits', text)

            # 3. Tracked: a child of the session is notified on exit, so a quiet stop is correct.
            child = subprocess.Popen([sys.executable, str(script)], cwd=self.root)
            try:
                self.assertTrue(wait_for(lambda: hook.verification_running(self.root)))
                self.assertEqual(hook.untracked_runs(hook.verification_running(self.root)), [])
                result = self.step()
                self.assertNotEqual(result.get('decision'), 'block', result)
                self.assertIn('re-invoked when it finishes', result['systemMessage'])
                self.assertIn('iteration: 4', self.state.read_text())
            finally:
                child.kill()
                child.wait()

    def test_unidentified_session_counts_as_untracked(self):
        """Fail safe: a wrong 'tracked' costs hours, a needless wait a status line."""
        run = [{'script': 'tools/esx/final_verification.py', 'minutes': 0, 'pid': os.getpid()}]
        self.assertEqual(hook.untracked_runs(run, session=0), run)
        self.assertEqual(hook.untracked_runs(run, session=os.getpid()), [])


class LoopControlTests(unittest.TestCase):
    def setUp(self):
        import check_ralph_hook
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.claude').mkdir()
        (self.root / 'tools/esx').mkdir(parents=True)
        (self.root / 'tools/esx/ralph_stop.py').write_text('# fixture handler\n')
        (self.root / '.claude/settings.json').write_text(json.dumps({'hooks': {'Stop': [
            {'hooks': [{'type': 'command', 'command': check_ralph_hook.COMMAND}]}]}}))
        # Isolate shared user configuration during deterministic checks.
        self.env = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root / 'user-config')})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('ESX_AGENT_RUNTIME_CHILD', None)

    def test_start_advance_cancel_never_recreates_cancelled_state(self):
        import loop_control
        result = loop_control.start(self.root, 'Continue the bounded issue.\n', 3)
        self.assertEqual(result['iteration'], 1)
        self.assertEqual(hook.step(self.root, {})['decision'], 'block')
        self.assertEqual(loop_control.status(self.root)['iteration'], 2)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(loop_control.cancel(self.root)['status'], 'cancelled')
        self.assertEqual(hook.step(self.root, {}), {})
        self.assertEqual(loop_control.status(self.root)['status'], 'inactive')
        self.assertEqual(len(list((self.root / '.claude').glob('esx-loop.local.md.cancelled.*'))), 1)

    def test_positive_finite_budget_is_required(self):
        import loop_control
        for value in (0, -1, True, 2.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'positive integer'):
                loop_control.start(self.root, 'Continue', value)

    def test_child_cannot_start_or_advance_parent_loop(self):
        import loop_control
        loop_control.start(self.root, 'Continue', 3)
        original = (self.root / loop_control.STATE).read_bytes()
        with patch.dict(os.environ, {'ESX_AGENT_RUNTIME_CHILD': '1'}):
            self.assertEqual(hook.step(self.root, {}), {})
            with self.assertRaisesRegex(ValueError, 'cannot own'):
                loop_control.start(self.root, 'Continue', 3)
        self.assertEqual((self.root / loop_control.STATE).read_bytes(), original)

    def test_existing_state_or_external_owner_blocks_start(self):
        import loop_control
        external = self.root / '.claude/ralph-loop.local.md'
        external.write_text('external plugin owns this state')
        with self.assertRaisesRegex(ValueError, 'external Ralph'):
            loop_control.start(self.root, 'Continue')
        external.unlink()
        loop_control.start(self.root, 'Continue')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            loop_control.start(self.root, 'Continue')

    def test_missing_duplicate_disabled_hooks_are_refused(self):
        import check_ralph_hook
        settings = self.root / '.claude/settings.json'
        valid = json.loads(settings.read_text())
        for invalid in ({}, {'disableAllHooks': True, **valid}, {'allowManagedHooksOnly':True, **valid},
                        {'hooks': {'Stop': valid['hooks']['Stop'] * 2}}):
            settings.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                check_ralph_hook.check(self.root)

    def test_stop_waiting_on_lifecycle_lock_observes_cancellation(self):
        import loop_control
        import time
        loop_control.start(self.root, 'Continue', 3)
        env = dict(os.environ, ESX_RALPH_PROJECT_DIR=str(self.root))
        with hook.loop_lock(self.root):
            process = subprocess.Popen([sys.executable, str(Path(hook.__file__))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            try:
                # The subprocess must wait for our lock; emulate cancellation
                # within that same critical section before releasing it.
                time.sleep(0.1)
                self.assertIsNone(process.poll())
                state = self.root / loop_control.STATE
                state.rename(state.with_name(state.name + '.cancelled.test'))
            except BaseException:
                process.kill()
                process.communicate()
                raise
        output, error = process.communicate('{}', timeout=3)
        self.assertEqual(process.returncode, 0, error)
        self.assertEqual(output, '')
        self.assertFalse((self.root / loop_control.STATE).exists())

    def test_scratch_override_is_authoritative_without_state(self):
        import loop_control
        loop_control.start(self.root, 'Continue', 3)
        with tempfile.TemporaryDirectory() as scratch, patch.dict(os.environ, {
                'ESX_RALPH_PROJECT_DIR': scratch, 'CLAUDE_PROJECT_DIR': str(self.root)}):
            self.assertEqual(hook.project_root({'cwd': str(self.root)}), Path(scratch))
        self.assertEqual(loop_control.status(self.root)['iteration'], 1)


if __name__ == '__main__':
    unittest.main()
