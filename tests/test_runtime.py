"""Exercise retained transport, corrupt evidence, identity and failure handling.

The deterministic executable below simulates the CLI transport protocol. These
tests cannot establish availability of the real model provider; ``probe`` and
the recorded live role experiment do that separately.
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "template/tools/esx"))
spec = importlib.util.spec_from_file_location("agent_runtime", ROOT / "template/tools/esx/agent_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

FAKE = '''#!/usr/bin/env python3
import json, pathlib, sys, time
args=sys.argv[1:]
if '--version' in args:
    print('fake-claude-1');sys.exit(0)
prompt=json.loads(sys.stdin.read())
if 'CLAUDECODE' in __import__('os').environ:
    print('nested sessions forbidden',file=sys.stderr);sys.exit(9)
resumed='--resume' in args
sid=args[args.index('--resume' if resumed else '--session-id')+1]
history=pathlib.Path('.history-'+sid+'.json')
if resumed and not history.exists():sys.exit(3)
values=json.loads(history.read_text()) if history.exists() else []
values.append(prompt)
history.write_text(json.dumps(values))
mode=prompt.get('mode','ok')
if mode=='timeout':time.sleep(30)
if mode=='crash':sys.exit(7)
actual='different-id' if mode=='identity' else sid
print(json.dumps({'type':'system','subtype':'init','session_id':actual,'tools':['Read']}))
footer={'agent':prompt.get('role','bob'),'issue_id':'TEST-001',
        'correction_round':prompt.get('round',0),'remembered':values[0].get('token'),
        'received_rounds':len(values)}
if 'footer' in prompt:footer=prompt['footer']
if mode=='wrong-role':footer['agent']='richard'
if mode=='wrong-issue':footer['issue_id']='ANOTHER'
message='report' if mode=='no-footer' else '```json\\n'+json.dumps(footer)+'\\n```'
if mode=='bad-final':message+='\\n```json\\n{invalid}\\n```'
print(json.dumps({'type':'result','subtype':'success','session_id':actual,
    'is_error':mode=='provider','result':message,
    'stop_reason':'max_tokens' if mode=='truncated' else 'end_turn',
    'usage':{'input_tokens':3,'output_tokens':2},'total_cost_usd':0}))
'''


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.binary = self.root / "claude-fake"
        self.binary.write_text(FAKE)
        self.binary.chmod(0o755)
        roles = self.root / ".claude/agents"
        roles.mkdir(parents=True)
        for role in ("bob", "richard"):
            (roles / (role + ".md")).write_text(
                f"---\nname: {role}\ntools: Read, Bash\nskills: esx-common\n---\nRole contract.\n")

    def run_turn(self, **kwargs):
        payload = kwargs.pop("payload", {})
        return runtime.run_turn(self.root, executable=str(self.binary),
                                prompt=json.dumps(payload), **kwargs)

    def start(self, **payload):
        return self.run_turn(role="bob", issue="TEST-001", payload=payload)

    def test_dispatcher_supplies_measured_identity_without_prompt_guessing(self):
        event = self.start()
        invocation = json.loads((self.root / event['invocation']['path']).read_text())
        argv = invocation['argv']
        context = argv[argv.index('--append-system-prompt') + 1]
        assignment = json.loads(context.split('ESX dispatcher assignment: ', 1)[1].split('\n', 1)[0])
        self.assertEqual(assignment['agent_id'], event['agent_id'])
        self.assertEqual(assignment['issue_id'], 'TEST-001')
        self.assertEqual(assignment['correction_round'], 0)
        self.assertNotIn('--dangerously-skip-permissions', argv)

    def test_two_turns_preserve_real_transport_history_and_identity(self):
        first = self.start(token="no-token-in-second-prompt")
        second = self.run_turn(session=first["session_id"], correction_round=1, payload={"round": 1})
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["agent_id"], first["agent_id"])
        self.assertEqual(second["footer"]["remembered"], "no-token-in-second-prompt")
        self.assertEqual(second["footer"]["received_rounds"], 2)
        self.assertEqual(second["resumed_from_event_id"], first["event_id"])
        self.assertNotEqual(second["event_id"], first["event_id"])
        command = json.loads((self.root / second["invocation"]["path"]).read_text())["argv"]
        self.assertIn("--resume", command)
        self.assertNotIn("--fork-session", command)
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertNotIn("--allowedTools", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertEqual(json.loads(command[command.index("--mcp-config") + 1]), {"mcpServers": {}})

    def test_failed_and_incomplete_turns_never_become_completed(self):
        modes = {"no-footer": "incomplete", "truncated": "incomplete",
                 "provider": "failed", "crash": "failed", "identity": "failed",
                 "wrong-role": "incomplete", "wrong-issue": "incomplete",
                 "bad-final": "incomplete"}
        for mode, expected in modes.items():
            with self.subTest(mode=mode):
                record = self.start(mode=mode)
                self.assertEqual(record["status"], expected, record)
                self.assertTrue(record["error"])
                state = json.loads((runtime.session_path(self.root, record["session_id"]) / "session.json").read_text())
                self.assertEqual(state["status"], expected)
                self.assertIsNone(state["active_event_id"])

    def test_wrong_correction_round_is_incomplete(self):
        self.assertEqual(self.start(round=3)["status"], "incomplete")

    def test_stalled_prompt_reader_cannot_bypass_turn_timeout(self):
        self.binary.write_text('#!' + sys.executable + '\nimport sys,time\n'
            'if "--version" in sys.argv: print("stalled-fixture");sys.exit(0)\n'
            'time.sleep(30)\n')
        begun = time.monotonic()
        event = runtime.run_turn(self.root, role='bob', issue='TEST-001',
            prompt='large bounded fixture ' * 60000, executable=str(self.binary), timeout=.2)
        self.assertLess(time.monotonic() - begun, 5)
        self.assertEqual(event['status'], 'failed')
        self.assertEqual(event['error'], 'timeout')
        self.assertIsNone(event['cost_usd'])

    def test_all_role_instructions_route_to_complete_common_footer(self):
        template = json.loads((ROOT / 'template/esx/templates/agent_report.json').read_text())
        for key in ('agent', 'issue_id', 'iteration_timestamp', 'correction_round', 'orientation'):
            self.assertIn(key, template)
        self.assertIs(type(template['correction_round']), int)
        self.assertEqual(template['correction_round'], 0)
        for role in sorted(runtime.ROLES):
            with self.subTest(role=role):
                instructions = (ROOT / 'template/.claude/agents' / (role + '.md')).read_text()
                self.assertIn('esx/templates/agent_report.json', instructions)
                self.assertIn('correction_round', instructions)
                if role in ('scout', 'prober', 'bisector', 'auditor'):
                    self.assertIn('`"correction_round": 0`', instructions)
                    self.assertIn('supplied nonzero integer', instructions)
                    self.assertIn('`incomplete`', instructions)

    def test_specialist_template_rounds_match_retained_runtime(self):
        template = json.loads((ROOT / 'template/esx/templates/agent_report.json').read_text())
        active = self.root / 'devel-loop/loop_state/issue-start.json'
        active.parent.mkdir(parents=True, exist_ok=True)
        stamp = '2026-09-17T13:45:00+00:00'
        active.write_text(json.dumps({'id': 'TEST-001', 'timestamp': stamp}))
        for role in ('scout', 'prober', 'bisector', 'auditor'):
            with self.subTest(role=role):
                (self.root / '.claude/agents' / (role + '.md')).write_bytes(
                    (ROOT / 'template/.claude/agents' / (role + '.md')).read_bytes())
                footer = dict(template, agent=role, issue_id='TEST-001', iteration_timestamp=stamp)
                first = self.run_turn(role=role, issue='TEST-001', payload={'footer':footer})
                self.assertEqual(first['status'], 'completed', first)
                for label, bad in [('missing', {k:v for k,v in footer.items() if k!='correction_round'}),
                                   ('wrong', dict(footer, correction_round=1)),
                                   ('string', dict(footer, correction_round='0'))]:
                    with self.subTest(case=label):
                        event = self.run_turn(role=role, issue='TEST-001', payload={'footer':bad})
                        self.assertEqual(event['status'], 'incomplete', event)
                        persisted = json.loads((runtime.session_path(self.root, event['session_id']) / 'session.json').read_text())
                        self.assertEqual(persisted['status'], 'incomplete')
                # Keeping the initial example's zero on a real correction is refused.
                wrong = self.run_turn(session=first['session_id'], correction_round=2, payload={'footer':footer})
                self.assertEqual(wrong['status'], 'incomplete', wrong)
                corrected = dict(footer, correction_round=2)
                good = self.run_turn(session=first['session_id'], correction_round=2, payload={'footer':corrected})
                self.assertEqual(good['status'], 'completed', good)
                self.assertEqual(good['agent_id'], first['agent_id'])
                self.assertEqual(good['footer']['correction_round'], 2)

    def test_timeout_kills_process_and_records_failure(self):
        record = self.run_turn(role="bob", issue="TEST-001", timeout=0.05, payload={"mode": "timeout"})
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "timeout")
        self.assertLess(record["duration_seconds"], 5)

    def test_parent_sigterm_records_interruption_and_stops_cli_child(self):
        prompt = self.root / "prompt.json"
        prompt.write_text(json.dumps({"mode": "timeout"}))
        process = subprocess.Popen([sys.executable, str(ROOT / "template/tools/esx/agent_runtime.py"),
            "--root", str(self.root), "--claude", str(self.binary), "start", "--role", "bob",
            "--issue", "TEST-001", "--prompt-file", str(prompt)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not list(self.root.glob('.history-*.json')) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(list(self.root.glob('.history-*.json')), "CLI child never started")
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 1, stderr)
            record = json.loads(stdout)
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error"], "interrupted")
            self.assertLess(record["returncode"], 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_launch_failure_is_recorded(self):
        with patch.object(runtime.subprocess, "Popen", side_effect=OSError("cannot launch")), \
             patch.object(runtime, "runtime_contract", return_value={"binary":str(self.binary),"sha256":"fake"}):
            record = self.start()
        self.assertEqual(record["status"], "failed")
        self.assertIn("cannot launch", record["error"])

    def test_concurrent_turn_on_same_session_is_rejected(self):
        first = self.start()
        folder = runtime.session_path(self.root, first["session_id"])
        with runtime.locked(folder / ".turn.lock"):
            with self.assertRaisesRegex(ValueError, "already has a running"):
                self.run_turn(session=first["session_id"], correction_round=1, payload={"round": 1})

    def test_unknown_native_id_cannot_fake_cli_resume(self):
        with self.assertRaisesRegex(ValueError, "session UUID"):
            self.run_turn(session="a-native-agent-id")

    def test_peer_message_resumes_target_and_records_sender(self):
        bob = self.start(token="retained-bob")
        richard = self.run_turn(role="richard", issue="TEST-001", payload={"role": "richard"})
        reply = self.run_turn(session=bob["session_id"], from_session=richard["session_id"],
                              correction_round=1, payload={"round": 1})
        self.assertEqual(reply["sender_session_id"], richard["session_id"])
        self.assertEqual(reply["footer"]["remembered"], "retained-bob")

    def test_peer_message_cannot_cross_issues(self):
        bob = self.start()
        richard = self.run_turn(role="richard", issue="ANOTHER", payload={"role": "richard"})
        with self.assertRaisesRegex(ValueError, "assigned issue"):
            self.run_turn(session=bob["session_id"], from_session=richard["session_id"],
                          correction_round=1, payload={"round": 1})

    def test_fresh_correction_requires_observed_replacement(self):
        with self.assertRaisesRegex(ValueError, "correction needs followup"):
            self.run_turn(role="bob", issue="TEST-001", correction_round=1, payload={"round": 1})

    def test_explicit_replacement_has_provenance(self):
        previous = self.start()
        replacement = self.run_turn(role="bob", issue="TEST-001", correction_round=1,
                                    payload={"round": 1}, replaces_agent=previous["agent_id"],
                                    replacement_reason="The runtime history was removed and resume failed.")
        self.assertEqual(replacement["status"], "completed")
        self.assertNotEqual(previous["agent_id"], replacement["agent_id"])
        self.assertEqual(replacement["replacement"]["event_id"], previous["event_id"])

    def test_replacement_cannot_change_role_or_issue(self):
        previous = self.start()
        with self.assertRaisesRegex(ValueError, "preserve the recorded role"):
            self.run_turn(role="richard", issue="TEST-001", correction_round=1,
                          payload={"role": "richard", "round": 1}, replaces_agent=previous["agent_id"],
                          replacement_reason="This explanation does not authorize changing roles.")

    def test_intentional_session_bridge_removes_nesting_sentinel(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            record = self.start()
        self.assertEqual(record["status"], "completed")

    def test_peer_environment_preserves_same_effective_configuration(self):
        path = self.root / ".claude/settings.json"
        path.write_text(json.dumps({"env":{"ANTHROPIC_BASE_URL":"https://example.invalid"}}))
        # `first` is the direct-CLI caller, whose value must come from settings.json.
        # A real session often exports ANTHROPIC_BASE_URL, which would otherwise
        # override the fixture and make this comparison depend on the machine.
        with patch.dict(os.environ):
            os.environ.pop("ANTHROPIC_BASE_URL", None)
            first = runtime.runtime_contract(self.root, str(self.binary), "bob")
        with patch.dict(os.environ, {"CLAUDECODE":"1", "CLAUDE_AGENT_ID":"peer-session",
                                     "ANTHROPIC_BASE_URL":"https://example.invalid"}):
            peer = runtime.runtime_contract(self.root, str(self.binary), "bob")
        self.assertEqual(first["sha256"], peer["sha256"])
        with patch.dict(os.environ, {"ANTHROPIC_BASE_URL":"https://changed.invalid"}):
            changed = runtime.runtime_contract(self.root, str(self.binary), "bob")
        self.assertNotEqual(first["sha256"], changed["sha256"])

    def test_role_turn_preserves_hooks_and_permissions_and_disables_ralph_only(self):
        path = self.root / ".claude/settings.json"
        path.write_text(json.dumps({"enabledPlugins":{"ralph-loop@test":True,"other@test":True},
                                    "hooks":{"PostToolUse":[]}, "permissions":{"defaultMode":"acceptEdits"}}))
        settings = runtime.role_runtime_settings(self.root)
        self.assertEqual(settings["enabledPlugins"]["ralph-loop@test"], False)
        self.assertNotIn("other@test", settings["enabledPlugins"])
        self.assertNotIn("permissions", settings)
        self.assertNotIn("hooks", settings)
        self.assertNotIn("disableAllHooks", settings)

    def test_missing_probe_is_not_live_availability(self):
        status = runtime.probe_status(self.root, str(self.binary))
        self.assertEqual(status["status"], "missing")
        self.assertFalse(status["reused_evidence"])

    def test_changed_contract_requires_explicit_replacement(self):
        first = self.start()
        path = self.root / ".claude/agents/bob.md"
        path.write_text(path.read_text() + "Changed policy.\n")
        with self.assertRaisesRegex(ValueError, "contract changed"):
            self.run_turn(session=first["session_id"], correction_round=1, payload={"round": 1})

    def test_formatting_resume_and_preflight_rejection_are_distinct_events(self):
        settings = self.root / '.claude/settings.json'
        settings.write_text('{"hooks": {}}')
        first = self.start(token='retained')
        settings.write_text('{\n "hooks": {}\n}')
        second = self.run_turn(session=first['session_id'], correction_round=1, payload={'round': 1})
        self.assertEqual(second['session_id'], first['session_id'])
        self.assertEqual(second['footer']['remembered'], 'retained')
        log = self.root / 'devel-loop/loop_state/dispatch_log.jsonl'
        before = log.read_bytes()
        settings.write_text('{"permissions":{"deny":["Bash"]}}')
        with self.assertRaisesRegex(ValueError, 'contract changed'):
            self.run_turn(session=first['session_id'], correction_round=2, payload={'round': 2})
        self.assertEqual(log.read_bytes(), before)
        events = [json.loads(line) for line in (self.root / 'devel-loop/loop_state/runtime-preflight.jsonl').read_text().splitlines()]
        self.assertEqual(events[-1]['status'], 'preflight_rejected')
        self.assertFalse(events[-1]['counts_as_correction'])
        self.assertEqual(events[-1]['session_id'], first['session_id'])

    def test_sealed_review_context_and_missing_packet_preflight(self):
        import test_framework
        fixture = test_framework.FrameworkTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        done = fixture.complete(qualify=False)
        supplied = runtime.review_context(fixture.root, done, fixture.issue,
                                          fixture.start['maintenance']['baseline'])
        self.assertEqual(supplied['candidate'], done['candidate'])
        self.assertEqual(supplied['maintenance']['documentation'], done['maintenance']['documentation'])
        with patch.object(runtime, 'runtime_contract', side_effect=AssertionError('must preflight before provider lookup')):
            with self.assertRaisesRegex(ValueError, 'requires --review-packet'):
                runtime.run_turn(fixture.root, role='richard', issue=fixture.issue, prompt='bounded review')
        bad = dict(done, maintenance={'baseline': fixture.start['maintenance']['baseline']})
        with self.assertRaisesRegex(ValueError, 'documentation evidence reference is required'):
            runtime.review_context(fixture.root, bad, fixture.issue)
        source = fixture.root / 'src/diffusion.py'
        source.write_text(source.read_text()+'\n# changed candidate\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            runtime.review_context(fixture.root, done, fixture.issue)

    def test_settings_changes_invalidate_runtime_fingerprint(self):
        first = runtime.runtime_contract(self.root, str(self.binary), "bob")
        (self.root / ".claude/settings.json").write_text('{"permissions":{"deny":["Bash"]}}')
        second = runtime.runtime_contract(self.root, str(self.binary), "bob")
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_contract_never_exposes_credentials(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-placeholder-value"}):
            contract = runtime.runtime_contract(self.root, str(self.binary), "bob")
        self.assertNotIn("secret-placeholder-value", json.dumps(contract))

    def test_record_references_exact_report_and_timing(self):
        record = self.start()
        path = self.root / record["report"]["path"]
        self.assertEqual(runtime.digest(path.read_bytes()), record["report"]["sha256"])
        self.assertEqual(runtime.footer_from(path.read_text()), record["footer"])
        self.assertGreater(record["duration_seconds"], 0)
        self.assertEqual(record["usage"]["input_tokens"], 3)
        self.assertLessEqual(record["started_at"], record["finished_at"])

    def test_final_bad_json_cannot_reuse_earlier_valid_footer(self):
        self.assertIsNone(runtime.footer_from('```json\n{"agent":"bob"}\n```\n```json\nBAD\n```'))

    def test_parse_ignores_corrupt_nonobject_stream_rows(self):
        path = self.root / "stream.jsonl"
        path.write_text('[]\nNOT JSON\n{"type":"result","result":"done"}\n')
        _, message, _ = runtime.parse_stream(path)
        self.assertEqual(message, "done")

    def test_inherited_model_is_preserved_and_explicit_model_is_honored(self):
        first = self.start()
        invocation = json.loads((self.root / first['invocation']['path']).read_text())
        self.assertNotIn('--model', invocation['argv'])
        path = self.root / '.claude/agents/bob.md'
        path.write_text(path.read_text().replace('tools:', 'model: project-selected-model\ntools:'))
        second = self.start()
        argv = json.loads((self.root / second['invocation']['path']).read_text())['argv']
        self.assertEqual(argv[argv.index('--model') + 1], 'project-selected-model')

    def test_unknown_or_external_tools_are_refused(self):
        path = self.root / '.claude/agents/bob.md'
        for value in ('Read, mcp__mail__send', 'Read, arbitrary', 'Read, *'):
            path.write_text('---\nname: bob\ntools: ' + value + '\n---\n')
            with self.assertRaisesRegex(ValueError, 'unsupported built-in tool'):
                self.start()

    def test_child_environment_preserves_permissions_and_disables_loop_ownership(self):
        self.binary.write_text(FAKE.replace("mode=prompt.get('mode','ok')", "assert __import__('os').environ.get('ESX_AGENT_RUNTIME_CHILD') == '1'\nassert __import__('os').environ.get('CLAUDE_PROJECT_DIR') == str(pathlib.Path.cwd())\nmode=prompt.get('mode','ok')"))
        self.assertEqual(self.start()['status'], 'completed')

    def test_matching_iteration_is_required_for_each_turn(self):
        folder = self.root / 'devel-loop/loop_state'
        folder.mkdir(parents=True)
        (folder / 'issue-start.json').write_text(json.dumps({'id': 'TEST-001', 'timestamp': 'first'}))
        self.assertEqual(self.start()['status'], 'incomplete')
        self.binary.write_text(FAKE.replace("'received_rounds':len(values)", "'received_rounds':len(values),'iteration_timestamp':prompt.get('iteration')"))
        first = self.start(iteration='first')
        self.assertEqual(first['status'], 'completed')
        self.assertEqual(first['iteration_timestamp'], 'first')
        (folder / 'issue-start.json').write_text(json.dumps({'id': 'TEST-001', 'timestamp': 'second'}))
        second = self.run_turn(session=first['session_id'], correction_round=1,
                               payload={'round': 1, 'iteration': 'second'})
        self.assertEqual(second['status'], 'completed')
        self.assertEqual(second['iteration_timestamp'], 'second')

    def test_native_capture_keeps_exact_report_and_rejects_last_malformed_footer(self):
        import hooks
        fields = {'agent': 'bob', 'issue_id': 'TEST-001', 'iteration_timestamp': 'exact-time',
                  'correction_round': 2}
        event = dict(agent_id='bob-native', agent_type='bob', last_assistant_message=
                     'observed report\n```json\n' + json.dumps(fields) + '\n```')
        good = hooks.capture(self.root, event)
        self.assertEqual(good['status'], 'completed')
        self.assertEqual(good['iteration_timestamp'], 'exact-time')
        self.assertEqual(good['correction_round'], 2)
        self.assertEqual((self.root / good['report']['path']).read_text(), event['last_assistant_message'])
        event['last_assistant_message'] += '\n```json\nINVALID\n```'
        self.assertEqual(hooks.capture(self.root, event)['status'], 'incomplete')

    def test_native_runtime_failures_are_never_success(self):
        import hooks
        base = dict(agent_id='bob-native', agent_type='bob', last_assistant_message='```json\n{"agent":"bob"}\n```')
        for extra, expected in [({'is_error': True}, 'failed'), ({'stop_reason':'max_tokens'}, 'incomplete'),
                                ({'agent_type': 'richard'}, 'incomplete'), ({'agent_id': None}, 'incomplete')]:
            self.assertEqual(hooks.capture(self.root, dict(base, **extra))['status'], expected)

    def test_state_symlink_cannot_write_outside_project(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'devel-loop').mkdir()
            (self.root / 'devel-loop/loop_state').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'leaves project'):
                self.start()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_runtime_drift_and_probe_evidence_are_separate_from_unit_success(self):
        self.assertEqual(runtime.probe_status(self.root, str(self.binary))['status'], 'missing')
        self.start()
        self.assertEqual(runtime.probe_status(self.root, str(self.binary))['status'], 'missing')


if __name__ == "__main__":
    unittest.main()
