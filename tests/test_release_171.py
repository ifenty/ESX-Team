"""1.7.1: per-dispatch role models.

Configuration, precedence and enforcement for retained (CLI) dispatch, recording for
native (Agent tool) dispatch, closeout findings when role_models is configured, and the
measured models summary. A project without role_models must behave exactly as before.
Offline, synthetic fixtures.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
import test_runtime
import closeout_doctor
import loop_gate
import project
import team_accounting
from project import STATE, atomic_json
from unittest.mock import patch

runtime = test_runtime.runtime
MODELS = {'bob': {'default': 'inherit', 'allowed': ['opus', 'claude-sonnet-4']},
          'richard': {'default': 'opus', 'allowed': ['opus', 'claude-haiku-4']}}

# The existing fake CLI, reporting the model it was asked for on its init record.
FAKE = test_runtime.FAKE.replace(
    "'session_id':actual,'tools':['Read']}",
    "'session_id':actual,'tools':['Read'],'model':(args[args.index('--model')+1] if '--model' in args else None)}")
assert FAKE != test_runtime.FAKE


def argv_of(root, record):
    return json.loads((Path(root) / record['invocation']['path']).read_text())['argv']


def role_file(root, role, pin=None):
    (Path(root) / '.claude/agents' / (role + '.md')).write_text(
        f"---\nname: {role}\ntools: Read, Bash\nskills: esx-common\n" + (f"model: {pin}\n" if pin else '') + "---\nRole contract.\n")


class RetainedModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.binary = self.root / 'claude-fake'
        self.binary.write_text(FAKE)
        self.binary.chmod(0o755)
        (self.root / '.claude/agents').mkdir(parents=True)
        for role in ('bob', 'richard'):
            role_file(self.root, role)
        # the bare fixture root has no valid project.json for the source signature
        patcher = patch.object(project, 'source_signature', return_value='sig')
        patcher.start()
        self.addCleanup(patcher.stop)

    def refused(self, **kwargs):
        with self.assertRaises(ValueError) as caught:
            self.run_turn(**kwargs)
        return str(caught.exception)

    def configure(self, models=MODELS):
        (self.root / 'esx').mkdir(exist_ok=True)
        (self.root / 'esx/project.json').write_text(json.dumps({'role_models': models} if models else {}))

    def run_turn(self, role='bob', payload=None, **kwargs):
        return runtime.run_turn(self.root, executable=str(self.binary), prompt=json.dumps(payload or {}),
                                **({'role': role, 'issue': 'TEST-001'} if 'session' not in kwargs else {}), **kwargs)

    def state(self, record):
        return json.loads((runtime.session_path(self.root, record['session_id']) / 'session.json').read_text())

    def test_explicit_model_reaches_the_command_line_and_the_record(self):
        record = self.run_turn(model='opus')
        self.assertEqual(record['status'], 'completed', record['error'])
        argv = argv_of(self.root, record)
        self.assertEqual(argv[argv.index('--model') + 1], 'opus')
        self.assertEqual((record['model'], record['model_requested']), ('opus', 'opus'))
        self.assertEqual(self.state(record)['model'], 'opus')

    def test_precedence_explicit_then_pin_then_default_then_inherit(self):
        self.configure(MODELS)
        # richard: default opus, no pin, no explicit
        argv = argv_of(self.root, self.run_turn('richard'))
        self.assertEqual(argv[argv.index('--model') + 1], 'opus')
        # pin beats default (the pin must itself be allowed)
        role_file(self.root, 'richard', 'claude-haiku-4')
        argv = argv_of(self.root, self.run_turn('richard'))
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-haiku-4')
        # explicit beats pin
        argv = argv_of(self.root, self.run_turn('richard', model='opus'))
        self.assertEqual(argv[argv.index('--model') + 1], 'opus')
        # bob: default inherit, no pin -> no --model flag at all
        record = self.run_turn('bob')
        self.assertNotIn('--model', argv_of(self.root, record))
        self.assertEqual(self.state(record)['model'], 'inherit')

    def test_model_outside_allowed_is_refused_at_start_and_lists_the_allowed_names(self):
        self.configure(MODELS)
        message = self.refused(model='gpt-9')
        self.assertIn('not allowed', message)
        self.assertIn('opus', message)
        self.assertIn('claude-sonnet-4', message)
        role_file(self.root, 'bob', 'gpt-9')  # a disallowed pin is refused the same way
        self.assertIn('not allowed', self.refused(role='bob'))

    def test_any_model_is_accepted_without_role_models(self):
        record = self.run_turn(model='whatever-1')
        self.assertEqual(record['status'], 'completed', record['error'])
        self.assertIn('whatever-1', argv_of(self.root, record))

    def test_followup_refuses_a_different_model_and_accepts_the_same_one(self):
        self.configure(MODELS)
        first = self.run_turn(model='opus')
        refused = self.refused(session=first['session_id'], correction_round=1, model='claude-sonnet-4')
        self.assertIn('replacement', refused)
        self.assertIn('--replaces-agent', refused)
        again = self.run_turn(session=first['session_id'], correction_round=1, model='opus', payload={'round': 1})
        self.assertEqual(again['status'], 'completed', again['error'])
        self.assertEqual(again['model_requested'], 'opus')
        # no --model on the followup: the stored model is reused on the command line
        third = self.run_turn(session=first['session_id'], correction_round=2, payload={'round': 2})
        argv = argv_of(self.root, third)
        self.assertEqual(argv[argv.index('--model') + 1], 'opus')
        # an inherit session refuses any concrete model
        inherit = self.run_turn('bob')
        self.assertIn('replacement', self.refused(session=inherit['session_id'], correction_round=1, model='opus'))

    def test_inherit_dispatch_keeps_the_contract_hash_of_a_project_without_role_models(self):
        plain = runtime.runtime_contract(self.root, str(self.binary), 'bob')
        self.assertNotIn('model', plain)
        self.assertEqual(runtime.runtime_contract(self.root, str(self.binary), 'bob', 'inherit')['sha256'], plain['sha256'])
        self.assertEqual(runtime.runtime_contract(self.root, str(self.binary), 'bob', None)['sha256'], plain['sha256'])
        self.assertNotEqual(runtime.runtime_contract(self.root, str(self.binary), 'bob', 'opus')['sha256'], plain['sha256'])
        # sessions: no config, configured-inherit and a role-file pin all keep the plain role hash
        self.assertEqual(self.run_turn()['runtime_fingerprint'], plain['sha256'])
        self.configure(MODELS)
        self.assertEqual(self.run_turn('bob')['runtime_fingerprint'], plain['sha256'])
        role_file(self.root, 'richard', 'opus')
        pinned = runtime.runtime_contract(self.root, str(self.binary), 'richard')
        self.assertEqual(self.run_turn('richard')['runtime_fingerprint'], pinned['sha256'])
        # a chosen model does change the hash, and the followup of that session is not a contract transition
        chosen = self.run_turn('bob', model='opus')
        self.assertNotEqual(chosen['runtime_fingerprint'], plain['sha256'])
        later = self.run_turn(session=chosen['session_id'], correction_round=1, payload={'round': 1})
        self.assertEqual(later['runtime_fingerprint'], chosen['runtime_fingerprint'])
        self.assertEqual(later['status'], 'completed', later['error'])

    def test_cli_accepts_model_on_start_and_followup(self):
        parser_source = (Path(runtime.__file__)).read_text()
        self.assertEqual(parser_source.count('add_argument("--model"'), 2)


class ConfigTests(unittest.TestCase):
    def check(self, value):
        project.validate_role_models(value)

    def test_valid_and_absent(self):
        self.check(None)
        self.check(copy.deepcopy(MODELS))
        self.check({'bob': {'allowed': ['opus']}})

    def test_refusals(self):
        bad = [({'arch': {'allowed': ['opus']}}, 'unknown role'),
               ({'bob': {'allowed': ['opus'], 'extra': 1}}, 'no other keys'),
               ({'bob': {'default': 'sonnet', 'allowed': ['opus']}}, 'default'),
               ({'bob': {'default': 'inherit'}}, 'allowed'),
               ({'bob': {'allowed': []}}, 'allowed'),
               ({'bob': {'allowed': ['opus', '']}}, 'allowed'),
               ({'bob': {'allowed': [3]}}, 'allowed'),
               ({'bob': {'allowed': ['inherit']}}, 'allowed'),
               ({}, 'non-empty'), ([], 'non-empty')]
        for value, word in bad:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, word):
                self.check(value)

    def test_config_validates_it_and_a_project_without_it_is_unchanged(self):
        fixture = test_framework.FrameworkTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        before = project.config(root)
        self.assertNotIn('role_models', before)
        self.assertEqual(project.role_models(root), {})
        path = root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg['role_models'] = {'scout': {'allowed': ['opus']}}
        atomic_json(path, cfg)
        with self.assertRaisesRegex(ValueError, 'unknown role'):
            project.config(root)
        cfg['role_models'] = MODELS
        atomic_json(path, cfg)
        self.assertEqual(project.config(root)['role_models'], MODELS)


class MatchingTests(unittest.TestCase):
    def test_conservative_normalisation(self):
        allowed = ['opus', 'claude-sonnet-4']
        for recorded in ('opus', 'claude-opus-4-5', 'claude-opus-4-5-20251101', 'us-gov.anthropic.claude-opus-5[1m]',
                         'claude-sonnet-4', 'claude-sonnet-4-5-20250929', 'claude-sonnet-4[1m]'):
            with self.subTest(recorded=recorded):
                self.assertIsNotNone(project.model_allowed(recorded, allowed))
        for recorded in ('claude-sonnet-5', 'claude-sonnet-40', 'claude-haiku-4-5', 'sonnet', 'gpt-opusx', '<synthetic>'):
            with self.subTest(recorded=recorded):
                self.assertIsNone(project.model_allowed(recorded, allowed))


def transcript(path, *models):
    rows = [{'type': 'user', 'message': {'role': 'user', 'content': 'hi'}}]
    for model in models:
        rows.append({'type': 'assistant', 'message': {'role': 'assistant', 'model': model, 'content': []}})
    Path(path).write_text(''.join(json.dumps(r) + '\n' for r in rows) + 'not json\n')


class NativeRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def stop(self, path):
        return runtime.stop_record(self.root, {'agent_id': 'a1', 'agent_type': 'bob', 'last_assistant_message': 'x',
                                               'agent_transcript_path': path})

    def test_last_assistant_model_is_stored_and_synthetic_is_ignored(self):
        path = self.root / 't.jsonl'
        transcript(path, 'claude-sonnet-4', 'claude-opus-5')
        self.assertEqual(self.stop(str(path))['model'], 'claude-opus-5')
        transcript(path, 'claude-opus-5', '<synthetic>')
        self.assertEqual(self.stop(str(path))['model'], 'claude-opus-5')
        transcript(path, '<synthetic>')
        self.assertIsNone(self.stop(str(path))['model'])
        logged = [json.loads(l) for l in (self.root / STATE / 'dispatch_log.jsonl').read_text().splitlines()]
        self.assertEqual([r['model'] for r in logged], ['claude-opus-5', 'claude-opus-5', None])

    def test_missing_unreadable_or_absent_transcript_stores_null_without_failing(self):
        for path in (str(self.root / 'nope.jsonl'), None, str(self.root)):
            with self.subTest(path=path):
                record = self.stop(path)
                self.assertIn('model', record)
                self.assertIsNone(record['model'])
        self.assertIsNone(runtime.transcript_model(12))


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.done = self.fixture.complete(qualify=False)

    def models(self, bob=None, richard=None):
        log = self.root / STATE / 'dispatch_log.jsonl'
        rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
        for row in rows:
            row['model'] = {'bob': bob, 'richard': richard}.get(row.get('agent_type'))
        log.write_text(''.join(json.dumps(r) + '\n' for r in rows))

    def configure(self, models):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg.pop('role_models', None)
        if models:
            cfg['role_models'] = models
        atomic_json(path, cfg)
        return loop_gate.Gate(self.root)

    def codes(self, gate):
        return {f['code'] for f in closeout_doctor.diagnose(gate)['findings']}

    def check_done_error(self, gate):
        try:
            gate.check_done()
        except ValueError as exc:
            return str(exc)
        return ''

    def test_unconfigured_project_is_never_checked(self):
        self.models(None, None)
        gate = self.configure(None)
        self.assertFalse({'MODEL_UNRECORDED', 'MODEL_NOT_ALLOWED'} & self.codes(gate))
        self.assertNotIn('MODEL_', self.check_done_error(gate))

    def test_unrecorded_model_is_flagged_when_configured(self):
        self.models(None, None)
        gate = self.configure(MODELS)
        codes = self.codes(gate)
        self.assertIn('MODEL_UNRECORDED', codes)
        self.assertNotIn('MODEL_NOT_ALLOWED', codes)
        self.assertIn('MODEL_UNRECORDED', self.check_done_error(gate))

    def test_disallowed_model_is_flagged_and_says_what_was_compared(self):
        self.models('claude-opus-5', 'claude-sonnet-5')
        gate = self.configure(MODELS)
        found = [f for f in closeout_doctor.diagnose(gate)['findings'] if f['code'] == 'MODEL_NOT_ALLOWED']
        self.assertEqual([f['agent'] for f in found], ['richard-runtime-1'])
        self.assertIn('claude-sonnet-5', found[0]['observed'])
        self.assertIn('prefix', found[0]['observed'])
        self.assertIn('MODEL_NOT_ALLOWED', self.check_done_error(gate))

    def test_allowed_recorded_models_raise_no_model_finding(self):
        self.models('claude-opus-5-20260101', 'claude-haiku-4-5')
        gate = self.configure(MODELS)
        self.assertFalse({'MODEL_UNRECORDED', 'MODEL_NOT_ALLOWED'} & self.codes(gate))
        self.assertNotIn('MODEL_', self.check_done_error(gate))

    def test_only_configured_roles_are_checked(self):
        self.models(None, None)
        gate = self.configure({'bob': MODELS['bob']})
        found = [f for f in closeout_doctor.diagnose(gate)['findings'] if f['code'] == 'MODEL_UNRECORDED']
        self.assertEqual([f['agent'] for f in found], ['bob-runtime-1'])


class MeasurementTests(unittest.TestCase):
    def test_summary_and_measured_report_models_with_unknowns_left_null(self):
        def turn(event, role, model, cost, session):
            return {'event_id': event, 'agent_type': role, 'agent_id': session, 'session_id': session, 'issue_id': 'X-1',
                    'correction_round': 0, 'source': 's', 'model': model, 'started_at': '2026-10-16T10:00:00+00:00',
                    'finished_at': '2026-10-16T10:01:00+00:00',
                    'accounting_components': [{'event_id': event, 'cost_usd': cost, 'kind': 'turn'}]}
        evidence = {'phases': [], 'self_reports': [], 'turns': [
            turn('e1', 'bob', 'claude-opus-5', 1.5, 's1'), turn('e2', 'bob', 'claude-opus-5', 0.5, 's1'),
            turn('e3', 'richard', 'claude-sonnet-4', None, 's2'), turn('e4', 'richard', None, 2.0, 's3')]}
        report = team_accounting.summary('.', 'X-1', evidence=evidence)
        self.assertEqual(report['by_model'], {
            'claude-opus-5': {'dispatches': 2, 'reported_usd': 2.0, 'unknown_cost_events': 0},
            'claude-sonnet-4': {'dispatches': 1, 'reported_usd': 0.0, 'unknown_cost_events': 1},
            'unknown': {'dispatches': 1, 'reported_usd': 2.0, 'unknown_cost_events': 0}})
        self.assertEqual(team_accounting.measured(report)['models'], report['by_model'])

    def test_records_without_a_model_field_leave_models_null(self):
        old = {'event_id': 'e1', 'agent_type': 'bob', 'agent_id': 's', 'session_id': 's', 'issue_id': 'X-1', 'source': 's',
               'accounting_components': [{'event_id': 'e1', 'cost_usd': 1.0}]}
        report = team_accounting.summary('.', 'X-1', evidence={'phases': [], 'self_reports': [], 'turns': [old]})
        self.assertNotIn('by_model', report)
        self.assertIsNone(team_accounting.measured(report)['models'])

    def test_draft_retro_carries_the_models_summary(self):
        import team_retrospective
        fixture = test_framework.FrameworkTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root
        hist = root / STATE / 'loop_history.jsonl'
        hist.parent.mkdir(parents=True, exist_ok=True)
        hist.write_text(json.dumps({'id': 'X-1', 'iteration': 1, 'timestamp': '2026-10-16T10:05:00Z',
                                    'start_timestamp': '2026-10-16T10:00:00Z', 'closed_at': '2026-10-16T10:05:00Z'}) + '\n')
        (root / STATE / 'dispatch_log.jsonl').write_text(json.dumps(
            {'runtime': 'native_subagent', 'event_id': 'n1', 'agent_type': 'bob', 'agent_id': 'a', 'session_id': 's',
             'issue_id': 'X-1', 'model': 'claude-opus-5', 'started_at': '2026-10-16T10:01:00+00:00',
             'finished_at': '2026-10-16T10:02:00+00:00'}) + '\n')
        draft = team_retrospective.draft(root)
        self.assertEqual(draft['measured']['models'],
                         {'claude-opus-5': {'dispatches': 1, 'reported_usd': 0.0, 'unknown_cost_events': 1}})


if __name__ == '__main__':
    unittest.main()
