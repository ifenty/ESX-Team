"""1.6.7: brief interface check, interpreter identity, provider-limit pause clock.

G: brief.py refuses commands naming flags the ESX tool does not accept, without
   blaming an oriented target path (TEAM-BRIEF-UNVALIDATED-INTERFACE-001,
   TEAM-BRIEF-ORIENTATION-SELFCOLLISION-001).
H: the interpreter's identity is recorded at --prepare and a change is announced
   (TEAM-ENV-INTERPRETER-DRIFT-001).
I: provider-limit pause time shifts the scope deadline (TEAM-PAUSE-DEADLINE-CLAMP-001).
Offline, synthetic deployment fixtures.
"""
import contextlib
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
import test_limits_and_footers as limits
from test_loop_drain_cadence import LoopFixture
import audit
import brief
import loop_control
import loop_gate
import project
import ralph_stop
import team_budget as budget

ROOT = Path(__file__).resolve().parents[1] / 'template'


class BriefInterfaceTests(unittest.TestCase):
    def test_nonexistent_flags_and_tools_are_caught(self):
        bad = brief.interface_errors(ROOT, 'run tools/esx/loop_gate.py --check-start --issue X --agent bob')
        self.assertEqual(bad, ['loop_gate.py does not accept --agent', 'loop_gate.py does not accept --issue'])
        self.assertTrue(brief.interface_errors(ROOT, 'tools/esx/nope_missing.py --x'))

    def test_legitimate_commands_are_not_refused(self):
        for command in ['tools/esx/loop_gate.py --check-start',
                        'tools/esx/doc_contract.py navigate --issue X --use Y',
                        'tools/esx/verify.py --suite focused --owner abc --fresh',
                        'tools/esx/project.py signature',
                        'Use tools/esx/project.py signature then tools/esx/verify.py --suite focused --owner X --fresh',
                        'Run tools/esx/verify.py --suite focused --owner X --fresh then tests/rnf/check.py --build']:
            self.assertEqual(brief.interface_errors(ROOT, command), [], command)

    def test_a_command_span_stops_at_a_quote(self):
        payload = ('"cmd": "python tools/esx/verify.py --suite focused --owner a1 --fresh", '
                   '"coverage": "refusal_check --mpi 2 was run outside verify.py"')
        self.assertEqual(brief.interface_errors(ROOT, payload), [])

    def test_a_tool_path_used_as_a_flag_value_is_not_a_command(self):
        line = ('/usr/bin/python3 tools/esx/doc_contract.py navigate --issue X --baseline {} --role bob --map m '
                '--target tools/esx/brief.py::build --target tools/esx/project.py::config '
                '--doc tools/esx/audit.py --use "Read the owners"')
        self.assertEqual(brief.interface_errors(ROOT, line), [])
        # A genuinely bad flag in the same text is still caught.
        self.assertEqual(brief.interface_errors(ROOT, line + ' then tools/esx/audit.py --bogus'),
                         ['audit.py does not accept --bogus'])

    def test_citations_resolve(self):
        self.assertEqual(brief.citation_errors(ROOT, 'see tools/esx/brief.py:1-5'), [])
        self.assertTrue(brief.citation_errors(ROOT, 'see tools/esx/brief.py:99999'))
        self.assertTrue(brief.citation_errors(ROOT, 'see tools/esx/missing.py:3'))


class BriefBuildTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.prepare()
        # The deployed brief tool introspects the deployed scripts.
        self.nav = project.json_file(self.root, project.STATE + '/issue-start.json')['maintenance']['orientation']

    def esx_nav(self):
        import doc_contract
        real = doc_contract.load

        def load(root, ref, kind, issue):
            nav = dict(real(root, ref, kind, issue))
            nav['targets'] = ['tools/esx/brief.py::build', 'tools/esx/project.py::config']
            nav['documents'] = ['docs/model_contract.md']
            return nav
        return mock.patch.object(doc_contract, 'load', load)

    def test_orientation_naming_esx_tools_is_not_refused_and_is_rendered(self):
        with self.esx_nav():
            text = brief.build(self.root, 'bob', self.fixture.issue, 'Change the brief tool.')
        self.assertIn('--target tools/esx/brief.py::build --target tools/esx/project.py::config', text)
        self.assertNotIn(brief.ORIENT_SLOT, text)
        self.assertNotIn(brief.PACKET_SLOT, text)

    def test_a_bad_flag_in_the_instructions_refuses_the_brief(self):
        with self.assertRaisesRegex(ValueError, 'loop_gate.py does not accept --agent'):
            brief.build(self.root, 'bob', self.fixture.issue, 'Run tools/esx/loop_gate.py --check-start --agent bob.')

    def test_the_quoted_packet_is_not_scanned(self):
        packet = project.json_file(self.root, project.STATE + '/issue-start.json')
        packet = dict(packet, quoted='run tools/esx/loop_gate.py --check-start --agent bob')
        import agent_runtime
        with mock.patch.object(agent_runtime, 'review_context', lambda *a, **k: None):
            packet['maintenance'] = dict(packet['maintenance'], documentation={'path': 'p', 'sha256': 's'})
            text = brief.build(self.root, 'richard', self.fixture.issue, 'Review it.', 'Is it right?', packet)
        self.assertIn('--agent bob', text)  # present as quoted payload, not refused

    def test_brief_states_footer_identity_and_the_broken_environment_rule(self):
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Qualify the update.')
        self.assertIn('The "agent" field must be exactly "bob"', text)
        self.assertIn('records the whole turn as `incomplete`', text)
        self.assertIn('environment is broken', text)
        self.assertIn('failing import', text)


class InterpreterIdentityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.reflect()
        self.fixture.write_issue()

    def facts(self, version):
        return {'version': version, 'optimize': 0, 'prefix': '/p', 'base_prefix': '/p'}

    def prepare(self, version):
        gate = loop_gate.Gate(self.root)
        py = sys.executable
        with mock.patch.object(project, 'pinned_facts', lambda cfg: self.facts(version)), \
                mock.patch.object(loop_gate.team_retrospective, 'require_clear', lambda root: None), \
                mock.patch.object(loop_gate.team_retrospective, 'require_followup', lambda root: None), \
                mock.patch.object(project, 'interpreter', lambda cfg=None: py), \
                contextlib.redirect_stderr(io.StringIO()):
            start = gate.prepare(self.fixture.issue, 'investigation', (), 'arch', 'Qualify the periodic boundary update.',
                                 'docs/code_map.md#pipeline', ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'],
                                 ['docs/model_contract.md'], 'Trace the periodic update into its oracle before evaluating acceptance.')
        return gate, start

    def history(self, start, **changes):
        path = self.root / project.STATE / 'loop_history.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {'id': 'OLD-1', 'timestamp': '2026-01-01T00:00:00+00:00', 'interpreter': start['interpreter']}
        row.update(changes)
        path.write_text(json.dumps(row) + '\n')

    def test_identity_has_version_path_and_a_distribution_digest(self):
        with mock.patch.object(project, 'pinned_facts', lambda cfg: self.facts('3.99.0')):
            identity = project.interpreter_identity({})
        self.assertEqual(identity['version'], '3.99.0')
        self.assertEqual(identity['executable'], sys.executable)
        self.assertRegex(identity['distributions'], '^[0-9a-f]{64}$')

    def test_a_different_interpreter_produces_the_notice(self):
        _, first = self.prepare('3.10.19')
        (self.root / project.STATE / 'issue-start.json').unlink()
        self.history(first)
        gate, second = self.prepare('3.14.7')
        self.assertEqual(second['interpreter']['version'], '3.14.7')
        notice = [n for n in gate.notices if n.startswith('INTERPRETER CHANGED')]
        self.assertEqual(len(notice), 1)
        self.assertIn('3.10.19', notice[0])
        self.assertIn('3.14.7', notice[0])

    def test_the_same_interpreter_produces_no_notice(self):
        _, first = self.prepare('3.10.19')
        (self.root / project.STATE / 'issue-start.json').unlink()
        self.history(first)
        gate, _ = self.prepare('3.10.19')
        self.assertEqual([n for n in gate.notices if 'INTERPRETER' in n], [])

    def test_next_shows_the_notice_for_an_active_iteration(self):
        _, first = self.prepare('3.10.19')
        self.history(first)
        path = self.root / project.STATE / 'issue-start.json'
        start = json.loads(path.read_text())
        start['interpreter'] = dict(start['interpreter'], version='3.14.7')
        path.write_text(json.dumps(start))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(loop_gate.Gate, 'check_diagnosis', lambda *a: None):
            loop_gate.Gate(self.root).next()
        self.assertIn('INTERPRETER CHANGED', out.getvalue())

    def test_an_old_start_file_without_the_key_is_accepted(self):
        _, start = self.prepare('3.10.19')
        path = self.root / project.STATE / 'issue-start.json'
        start.pop('interpreter')
        path.write_text(json.dumps(start))
        self.assertIsNone(loop_gate.Gate.interpreter_notice(start, [{'id': 'X', 'timestamp': 'T', 'interpreter': {'version': 'v'}}]))
        self.history({'interpreter': {'version': 'older'}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            loop_gate.Gate(self.root).next()
        self.assertNotIn('INTERPRETER CHANGED', out.getvalue())

    def test_required_imports_are_checked_by_the_audit(self):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        path.write_text(json.dumps(dict(cfg, required_imports=['json', 'esx_no_such_module_xyz'])))
        with self.assertRaisesRegex(ValueError, 'esx_no_such_module_xyz') as caught:
            audit.check(self.root)
        self.assertNotIn(', json', str(caught.exception).split('imported by')[1].split('(')[0])
        path.write_text(json.dumps(dict(cfg, required_imports=['json', 'os.path'])))
        self.assertEqual(audit.check(self.root)['status'], 'PASS')

    def test_required_imports_must_be_module_names(self):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        for bad in ('json', ['json; import os'], [3]):
            path.write_text(json.dumps(dict(cfg, required_imports=bad)))
            with self.assertRaisesRegex(ValueError, 'required_imports'):
                project.config(self.root)


class PauseClockTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.cap = budget.limits('scientific_small')  # 30 nominal minutes: deadline = started + 1800

    def reserve(self, event, now, **kwargs):
        with mock.patch.object(budget.time, 'time', return_value=now):
            return budget.reserve(self.root, event, 'TEAM-TEST-001', self.cap, turn_seconds=5400, **kwargs)

    def scope(self):
        return json.loads(budget.file_for(self.root).read_text())

    def test_a_recorded_pause_shifts_the_deadline_but_not_the_stored_baseline(self):
        self.reserve('first', 1000)
        budget.record_pause(self.root, 1200, 2200)
        receipt = self.reserve('after', 2300)
        self.assertEqual(receipt['deadline'], 1000 + 1800 + 1000)
        self.assertEqual(receipt['soft_deadline'], 1000 + 1440 + 1000)
        self.assertGreaterEqual(receipt['deadline'] - 2300, min(5400, (1000 + 1800 - 2300) + 1000))
        self.assertNotIn('deadline', self.scope()['scopes']['issue:TEAM-TEST-001'])

    def test_thirty_minutes_of_pause_gives_remaining_nominal_plus_thirty(self):
        self.reserve('first', 1000)
        budget.record_pause(self.root, 1100, 1100 + 1800)
        receipt = self.reserve('after', 2950)
        self.assertEqual(receipt['deadline'], 1000 + 1800 + 1800)
        self.assertGreaterEqual(receipt['deadline'] - 2950, min(5400, 0 + 1800 - 150))

    def test_without_a_pause_nothing_changes(self):
        self.reserve('first', 1000)
        self.assertEqual(self.reserve('second', 2300)['deadline'], 2800)

    def test_a_pause_that_does_not_overlap_the_scope_shifts_nothing(self):
        budget.record_pause(self.root, 100, 600)  # before the scope began
        self.reserve('first', 1000)
        budget.record_pause(self.root, 5000, 6000)  # after the reservation below
        self.assertEqual(self.reserve('second', 2300)['deadline'], 2800)

    def test_an_owner_source_interval_shifts_nothing(self):
        self.reserve('first', 1000)
        with budget.transaction(self.root) as ledger:
            ledger['pauses'] = [{'start': 1200, 'end': 2200, 'source': 'owner'}]
        self.assertEqual(self.reserve('second', 2300)['deadline'], 2800)

    def test_an_open_interval_counts_up_to_now(self):
        self.reserve('first', 1000)
        budget.record_pause(self.root, 1200)
        self.assertEqual(self.reserve('second', 2300)['deadline'], 2800 + 1100)

    def test_a_second_open_start_does_not_double_count(self):
        self.reserve('first', 1000)
        budget.record_pause(self.root, 1200)
        budget.record_pause(self.root, 1500)
        self.assertEqual(len(self.scope()['pauses']), 1)

    def test_extend_uses_the_shifted_deadline(self):
        from process_evidence import ref
        self.reserve('first', 1000)
        budget.settle(self.root, 'first', 0)
        budget.record_pause(self.root, 1200, 2200)
        scope = self.scope()['scopes']['issue:TEAM-TEST-001']
        request = {'issue': 'TEAM-TEST-001', 'authorization_id': 'fixture-owner-1', 'authorized_by': 'Owner',
                   'evidence': 'fixture', 'reason': 'continue', 'expected_scope_sha256': budget.scope_digest(scope),
                   'add_minutes': 20}
        path = self.root / 'authorization.json'
        path.write_text(json.dumps(request))
        with mock.patch.object(budget.time, 'time', return_value=2300):
            budget.extend(self.root, ref(self.root, path), True)
        # Shifted base 3800 plus 20 minutes; the later reserve adds the 1000 s shift once, not twice.
        self.cap = budget.assignment(self.root, 'TEAM-TEST-001')[0]
        self.assertEqual(self.reserve('resumed', 2400)['deadline'], 3800 + 1200)


class PauseRecordingTests(LoopFixture, limits.Transcripts):
    def write(self, *records):
        return limits.Transcripts.write(self, *records)

    def pauses(self):
        path = budget.file_for(self.root)
        return json.loads(path.read_text()).get('pauses', []) if path.exists() else []

    def test_provider_limit_pause_and_resume_are_recorded(self):
        self.begin_issue()
        clock = iter([1000.0, 1900.0])
        with mock.patch.object(ralph_stop, 'clock', lambda: next(clock)):
            loop_control.pause(self.root, 'provider usage limit', source='provider_limit')
            self.assertEqual(self.pauses(), [{'start': 1000.0, 'end': None, 'source': 'provider_limit'}])
            loop_control.resume(self.root)
        self.assertEqual(self.pauses(), [{'start': 1000.0, 'end': 1900.0, 'source': 'provider_limit'}])

    def test_an_owner_pause_is_not_recorded(self):
        self.begin_issue()
        loop_control.pause(self.root, 'owner wants a break')
        loop_control.resume(self.root)
        self.assertEqual(self.pauses(), [])

    def test_the_hook_records_its_automatic_pause_and_resume(self):
        self.begin_issue()
        limited = self.write(limits.USER, limits.say('started'), limits.LIMIT)
        clock = iter([2000.0, 2600.0])
        with mock.patch.object(ralph_stop, 'clock', lambda: next(clock, 9999.0)):
            self.stop(transcript_path=limited)
            self.assertEqual(len(self.pauses()), 1)
            self.assertIsNone(self.pauses()[0]['end'])
            self.stop(transcript_path=self.write(limits.USER, limits.LIMIT, limits.RESET, limits.say('back')))
        row = self.pauses()[0]
        self.assertEqual(row['source'], 'provider_limit')
        self.assertIsNotNone(row['end'])
        self.assertGreaterEqual(row['end'], row['start'])


if __name__ == '__main__':
    unittest.main()
