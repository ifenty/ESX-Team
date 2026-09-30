#!/usr/bin/env python3
"""Regression coverage for the 1.5.1 headless-role failures (no provider calls).

TEAM-RUNTIME-PERMDENIED-CRASH-001 / ESX-001, ESX-002: the runtime hook's rewrite
made every allow rule unmatchable, and the dispatcher then crashed on the CLI's
string-valued permission_denied event, orphaning the turn. Also covered: the
Stop hook's transcript race, iteration burn while a dispatch is in flight, and
the external-input preflight.
"""
from contextlib import redirect_stderr
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'template/tools/esx'))
import permission_match as pm  # noqa: E402
import ralph_stop as hook  # noqa: E402
import project  # noqa: E402
spec = importlib.util.spec_from_file_location('agent_runtime', ROOT / 'template/tools/esx/agent_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

DENIAL = {"type": "system", "subtype": "permission_denied", "tool_name": "Bash",
          "tool_use_id": "toolu_1", "decision_reason_type": "other",
          "decision_reason": "This command requires approval",
          "message": "This command requires approval", "session_id": "s"}
TOOL_USE = {"type": "assistant", "message": {"role": "assistant", "content": [
    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "pwd"}}]}}


class MatcherTests(unittest.TestCase):
    rules = {'allow': ['Bash(sed *)', 'Bash(grep *)', 'Bash(cut *)', 'Bash(python3 *)', 'Bash(head *)',
                       'Bash(git status:*)', 'Bash(kpp*)', 'Bash(pwd)'],
             'ask': ['Bash(git push *)'], 'deny': ['Bash(rm *)']}

    def test_compound_command_that_crashed_bob_is_allowed(self):
        command = ('sed -n 66,70p open_issues.md | cut -c1-6000; grep -n "ghat" docs/a.md docs/b.md | cut -c1-600; '
                   'python3 tools/esx/project.py signature; grep -n "class KPPAdapter" -A80 m.py | head -150')
        self.assertEqual(pm.decide(command, self.rules), 'allow')

    def test_every_subcommand_must_match(self):
        self.assertIsNone(pm.decide('grep x f; curl http://example.invalid', self.rules))
        self.assertEqual(pm.decide('git status --short && pwd', self.rules), 'allow')
        self.assertEqual(pm.decide('kpp_wrapper run', self.rules), 'allow')

    def test_uncertain_shapes_never_get_an_allow(self):
        for command in ('grep "$(curl x)" f', 'grep `id` f', 'sed -n 1p f > out.txt', 'python3 x.py &',
                        'cat <<EOF\nx\nEOF', '(grep x f)', 'grep "x f', 'head <(python3 x.py)'):
            self.assertIsNone(pm.decide(command, self.rules), command)
        self.assertEqual(pm.decide('grep x f 2>&1 | head -3', self.rules), 'allow')
        self.assertEqual(pm.decide('grep x f 2>/dev/null; head f >/dev/null', self.rules), 'allow')
        for command in ('grep x f 2>err.txt', 'sed -n 1p f >>log', 'grep x f >/dev/nullx', 'cat > f <<EOF\nx\nEOF'):
            self.assertIsNone(pm.decide(command, self.rules), command)

    def test_quoted_operators_are_data_not_redirects(self):
        multi = 'python3 -c "import sys\nif len(sys.argv) > 0 and 1 < 2: print(1 & 3)"'
        self.assertEqual(pm.decide(multi, self.rules), 'allow')
        self.assertEqual(pm.decide("grep '<tag>' f | head -1", self.rules), 'allow')
        self.assertIsNone(pm.decide('python3 -c "print(1)" > out.txt', self.rules))
        self.assertEqual(pm.decide("grep 'a;b|c' f", self.rules), 'allow')

    def test_deny_and_ask_rules_win(self):
        self.assertEqual(pm.decide('grep x f; rm -rf build', self.rules), 'deny')
        self.assertIsNone(pm.decide('git push origin main', self.rules))

    def test_unreadable_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / '.claude').mkdir()
            (Path(temp) / '.claude/settings.local.json').write_text('{not json')
            with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': temp + '/none'}):
                rules = pm.load_rules(temp)
            self.assertEqual(pm.decide('grep x f', rules), 'deny')


class RuntimeStreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_string_message_event_does_not_crash_the_watchdog(self):
        stream = self.root / 'stdout.jsonl'
        stream.write_text(json.dumps(TOOL_USE) + '\n' + json.dumps(DENIAL) + '\n')
        open_tools = {}
        runtime._read_tool_events(stream, 0, '', open_tools)
        self.assertIn('toolu_1', open_tools)
        denials = runtime.permission_denials(stream)
        self.assertEqual(denials[0]['reason'], 'This command requires approval')
        self.assertEqual(denials[0]['input'], {'command': 'pwd'})

    def orphan_session(self, later_completed):
        session = 'a7e61b17-0000-4000-8000-000000000000'
        folder = runtime.session_path(self.root, session)
        turns = []
        for name in ('orphan', 'later') if later_completed else ('orphan',):
            turn = folder / 'turns' / name
            turn.mkdir(parents=True)
            (turn / 'invocation.json').write_text('{}')
            (turn / 'stdout.jsonl').write_text(json.dumps(TOOL_USE) + '\n' + json.dumps(DENIAL) + '\n')
            turns.append(name)
        if later_completed:
            (folder / 'turns/later/record.json').write_text('{"status": "completed"}')
        state = {'session_id': session, 'role': 'bob', 'issue_id': 'X-1', 'probe': False,
                 'turns': ['later'] if later_completed else [],
                 'status': 'completed' if later_completed else 'running',
                 'active_event_id': None if later_completed else 'orphan'}
        (folder / 'session.json').write_text(json.dumps(state))
        return session, folder

    def test_recover_closes_last_turn_orphan_as_failed(self):
        session, folder = self.orphan_session(False)
        value = runtime.recover_orphans(self.root, session, 'dispatcher crashed on a permission_denied event')
        self.assertEqual(value['recovered_event_ids'], ['orphan'])
        record = json.loads((folder / 'turns/orphan/record.json').read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['permission_denials'][0]['tool_name'], 'Bash')
        state = json.loads((folder / 'session.json').read_text())
        self.assertEqual(state['status'], 'failed')
        self.assertIsNone(state['active_event_id'])
        log = (self.root / 'devel-loop/loop_state/dispatch_log.jsonl').read_text()
        self.assertIn('recovered_orphan', log)

    def test_recover_closes_orphan_before_later_completed_turns(self):
        session, folder = self.orphan_session(True)
        value = runtime.recover_orphans(self.root, session, 'dispatcher crashed on a permission_denied event')
        self.assertEqual(value['recovered_event_ids'], ['orphan'])
        state = json.loads((folder / 'session.json').read_text())
        self.assertEqual(state['status'], 'completed')  # later successful work is untouched
        self.assertIn('orphan', state['turns'])

    def test_recover_refuses_a_live_turn_and_a_bare_reason(self):
        session, folder = self.orphan_session(False)
        with self.assertRaises(ValueError):
            runtime.recover_orphans(self.root, session, 'short')
        with (folder / '.turn.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            with self.assertRaises(ValueError):
                runtime.recover_orphans(self.root, session, 'dispatcher crashed on a permission_denied event')


class StopHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.claude').mkdir()
        self.state = self.root / '.claude/esx-loop.local.md'
        self.state.write_text('---\nactive: true\niteration: 1\nmax_iterations: 5\n'
                              'completion_promise: "DONE"\n---\nContinue.\n')
        self.transcript = self.root / 'transcript.jsonl'
        # The transcript still lags: only the earlier user turn is on disk.
        self.transcript.write_text(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'go'}}) + '\n')

    def step(self, **extra):
        with redirect_stderr(io.StringIO()):
            return hook.step(self.root, dict(transcript_path=str(self.transcript), **extra))

    def test_last_assistant_message_fulfils_promise_despite_lagging_transcript(self):
        result = self.step(last_assistant_message='All blocked.\n\n<promise>DONE</promise>')
        self.assertNotIn('decision', result)
        self.assertIn('completion promise fulfilled', result['systemMessage'])
        self.assertFalse(self.state.exists())

    def test_waiting_on_live_dispatch_does_not_consume_iterations_but_is_capped(self):
        loop_state = self.root / 'devel-loop/loop_state'
        loop_state.mkdir(parents=True)
        (loop_state / 'issue-start.json').write_text('{"id": "X-1"}')
        session = loop_state / 'agent_runtime/sessions/s1'
        session.mkdir(parents=True)
        (session / 'session.json').write_text('{"issue_id": "X-1", "status": "running"}')
        with (session / '.turn.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            for expected in range(1, hook.MAX_DISPATCH_WAITS + 1):
                result = self.step()
                self.assertEqual(result['decision'], 'block')
                self.assertIn('dispatch_waits: ' + str(expected), self.state.read_text())
                self.assertIn('iteration: 1\n', self.state.read_text())
            self.step()  # cap reached: the iteration advances and the wait count resets
            self.assertIn('iteration: 2\n', self.state.read_text())
            self.assertNotIn('dispatch_waits', self.state.read_text())


class WitnessSelectionTests(unittest.TestCase):
    """MITgcm_new_runoff allows `Bash(mkdir *)`; the witness must not report that as failure."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.claude').mkdir()
        patcher = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.root / 'none')})
        patcher.start()
        self.addCleanup(patcher.stop)

    def witness(self, allow):
        (self.root / '.claude/settings.local.json').write_text(json.dumps({'permissions': {'allow': allow}}))
        seen = {}
        def fake_turn(root, **kwargs):
            seen['prompt'] = kwargs['prompt']
            allowed = kwargs['prompt'].split('1. ')[1].split('\n')[0]
            stream = Path(root) / 'stream.jsonl'
            stream.write_text(json.dumps({'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'id': 'a', 'input': {'command': allowed}}]}}) + '\n' + json.dumps(
                {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a',
                 'content': allowed.split()[-1]}]}}) + '\n')
            return {'stream': {'path': 'stream.jsonl'}, 'effective_permission_mode': 'default'}
        with patch.object(runtime, 'run_turn', fake_turn):
            return runtime.permission_witness(self.root), seen['prompt']

    def test_allowed_mkdir_selects_another_write_command(self):
        value, prompt = self.witness(['Bash(printf *)', 'Bash(mkdir *)'])
        self.assertTrue(value['denied_command'].startswith('touch '), value)
        self.assertIn('2. touch ', prompt)

    def test_all_write_commands_allowed_checks_allow_path_only(self):
        value, prompt = self.witness(['Bash(printf *)', 'Bash(mkdir *)', 'Bash(touch *)', 'Bash(ln *)',
                                      'Bash(cp *)', 'Bash(install *)'])
        self.assertIsNone(value['denied_command'])
        self.assertNotIn('2. ', prompt)
        self.assertEqual(value['status'], 'passed')
        self.assertIn('only the allowed path was checked', value['note'])


class HandbackCaptureTests(unittest.TestCase):
    """A report delivered via SubagentHandback leaves last_assistant_message empty."""

    def test_footer_is_recovered_from_the_handback_in_the_agent_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            footer = {'agent': 'bob', 'issue_id': 'X-1', 'correction_round': 0}
            report = 'Done.\n```json\n' + json.dumps(footer) + '\n```'
            transcript = root / 'agent.jsonl'
            rows = [{'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                        {'type': 'text', 'text': 'earlier text without a footer'}]}},
                    {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                        {'type': 'tool_use', 'name': 'SubagentHandback', 'input': {'message': report}}]}},
                    {'type': 'user', 'message': {'role': 'user', 'content': [
                        {'type': 'tool_result', 'content': 'Report delivered to your caller.'}]}}]
            transcript.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            record = runtime.stop_record(root, {'agent_id': 'a1', 'agent_type': 'bob', 'session_id': 's',
                                                'last_assistant_message': '', 'agent_transcript_path': str(transcript)})
            self.assertEqual(record['status'], 'completed', record['error'])
            self.assertEqual(record['footer'], footer)
            self.assertEqual(record['report_source'], 'agent_transcript')

    def test_no_transcript_and_no_footer_stays_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            record = runtime.stop_record(Path(temp), {'agent_id': 'a1', 'agent_type': 'bob',
                                                     'last_assistant_message': ''})
            self.assertEqual(record['status'], 'incomplete')


class PreflightTests(unittest.TestCase):
    def test_missing_external_inputs_are_named(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'present.nc').write_text('x')
            cfg = {'external_inputs': ['present.nc', 'captures/absent.nc'], 'toolchain_commands': [],
                   'environment_variables': []}
            self.assertEqual(project.missing_inputs(temp, cfg), ['captures/absent.nc'])
            with self.assertRaisesRegex(ValueError, '1 of 2 configured external_inputs are missing'):
                project.environment(Path(temp), cfg)


if __name__ == '__main__':
    unittest.main()
