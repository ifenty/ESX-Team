"""1.6.3: automatic pause and resume at provider usage limits; native footer references; audit at seal.

Offline: synthetic deployment fixture and transcript records shaped like real ones
(an assistant record with error "rate_limit", the API-error flag and the CLI's
synthetic model). No provider calls.
"""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework  # noqa: F401  (puts the template tools on sys.path)
from test_loop_drain_cadence import LoopFixture
import agent_runtime
import brief
import doc_contract
import hooks
import loop_control
import project
import ralph_stop
import records
import verify

LIMIT = {'type': 'assistant', 'error': 'rate_limit', 'isApiErrorMessage': True, 'apiErrorStatus': 429,
         'message': {'role': 'assistant', 'model': '<synthetic>', 'type': 'message', 'stop_reason': 'stop_sequence',
                     'content': [{'type': 'text', 'text': "You've hit your weekly limit · resets Oct 2, 4am"}]}}
USER = {'type': 'user', 'message': {'role': 'user', 'content': 'Continue.'}}
RESET = {'type': 'user', 'isMeta': True, 'message': {'role': 'user', 'content':
         'Your claude.ai usage limit has reset. Continue the task you were working on when the limit was reached.'}}
TOOL_RESULT = {'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'ok'}]}}


def say(text):
    return {'type': 'assistant', 'message': {'role': 'assistant', 'model': 'claude-opus-5-5',
                                             'content': [{'type': 'text', 'text': text}]}}


class Transcripts(unittest.TestCase):
    def write(self, *records):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in folder.iterdir()] and None)
        path = folder / 'transcript.jsonl'
        path.write_text('\n'.join(json.dumps(r) for r in records) + '\n')
        return str(path)


class DetectionTests(Transcripts):
    def test_the_limit_record_is_recognised_by_its_fields_only(self):
        self.assertTrue(ralph_stop.synthetic_limit(LIMIT))
        snake = dict(LIMIT)
        snake.pop('isApiErrorMessage')
        snake['is_api_error_message'] = True
        self.assertTrue(ralph_stop.synthetic_limit(snake))
        for change in ({'error': 'overloaded'}, {'isApiErrorMessage': False},
                       {'message': dict(LIMIT['message'], model='claude-opus-5-5')}, {'type': 'user'}):
            self.assertFalse(ralph_stop.synthetic_limit(dict(LIMIT, **change)), change)
        self.assertFalse(ralph_stop.synthetic_limit(say("You've hit your weekly limit")))  # text alone is nothing

    def test_how_the_current_turn_ended(self):
        self.assertEqual(ralph_stop.provider_turn(self.write(USER, say('working'), TOOL_RESULT, LIMIT)), 'limited')
        self.assertEqual(ralph_stop.provider_turn(self.write(USER, LIMIT)), 'limited')
        self.assertEqual(ralph_stop.provider_turn(self.write(USER, LIMIT, RESET, say('back at work'))), 'working')
        self.assertEqual(ralph_stop.provider_turn(self.write(USER, say('a'), TOOL_RESULT, say('b'))), 'working')
        self.assertIsNone(ralph_stop.provider_turn(self.write(USER)))
        self.assertIsNone(ralph_stop.provider_turn(None))
        self.assertIsNone(ralph_stop.provider_turn('/nonexistent/transcript.jsonl'))

    def test_a_retained_stream_with_only_the_synthetic_record_is_a_limit(self):
        path = Path(self.write(USER, LIMIT))
        self.assertEqual(agent_runtime.provider_limit(path), {'limit_type': None, 'reset_at': None})


class AutoPauseTests(LoopFixture, Transcripts):
    def write(self, *records):
        return Transcripts.write(self, *records)

    def events(self, kind):
        return [e for e in json.loads((self.root / 'devel-loop/loop_state/notifications.json').read_text())['events']
                .values() if e['kind'] == kind]

    def test_a_limit_pauses_the_loop_and_real_work_resumes_it(self):
        self.begin_issue()
        limited = self.write(USER, say('started'), LIMIT)
        before = self.stop(transcript_path=self.write(USER, say('one iteration')))
        self.assertEqual(before['decision'], 'block')
        self.assertIn('iteration: 2', self.state_text())
        result = self.stop(transcript_path=limited)
        self.assertNotIn('decision', result)
        self.assertIn('provider usage limit', result['systemMessage'])
        status = loop_control.status(self.root)
        self.assertTrue(status['paused'])
        self.assertEqual(status['pause_source'], 'provider_limit')
        self.assertIsNone(status['paused_until'])  # a transcript gives no machine-readable reset time
        self.assertEqual(len(self.events('loop_paused')), 1)
        frozen = self.state_text()
        for _ in range(ralph_stop.MAX_ADVANCES + 2):  # a long (weekly) limit: every stop is quiet, nothing counts
            self.assertNotIn('decision', self.stop(transcript_path=limited))
        self.assertEqual(self.state_text(), frozen)
        self.assertEqual(len(self.events('loop_paused')), 1)
        resumed = self.stop(transcript_path=self.write(USER, LIMIT, RESET, say('the limit has reset')))
        self.assertEqual(resumed['decision'], 'block')  # real work happened: a normal Stop
        self.assertIn('iteration: 3', self.state_text())
        self.assertNotIn('paused', loop_control.status(self.root))
        self.assertEqual(len(self.events('loop_resumed')), 1)
        log = (self.root / '.claude/esx-loop-exit.log').read_text()
        self.assertIn('AUTO_PAUSE', log)
        self.assertIn('AUTO_RESUME', log)

    def test_an_owner_pause_is_never_lifted_by_work(self):
        self.begin_issue()
        loop_control.pause(self.root, 'owner wants a break')
        result = self.stop(transcript_path=self.write(USER, say('still working')))
        self.assertNotIn('decision', result)
        self.assertEqual(loop_control.status(self.root)['pause_source'], 'owner')
        self.assertIn('iteration: 1', self.state_text())

    def test_a_limit_during_an_owner_pause_keeps_the_owner_pause(self):
        self.begin_issue()
        loop_control.pause(self.root, 'owner wants a break')
        self.stop(transcript_path=self.write(USER, LIMIT))
        self.assertEqual(loop_control.status(self.root)['pause_reason'], 'owner wants a break')
        self.assertEqual(loop_control.status(self.root)['pause_source'], 'owner')

    def test_a_pending_cancel_survives_an_automatic_pause_and_resume(self):
        self.begin_issue()
        loop_control.cancel(self.root, 'stop after this issue')
        self.stop(transcript_path=self.write(USER, LIMIT))
        self.assertTrue(loop_control.status(self.root)['paused'])
        self.stop(transcript_path=self.write(USER, say('working again')))
        status = loop_control.status(self.root)
        self.assertNotIn('paused', status)
        self.assertTrue(status['cancelling'])

    def test_a_refused_retained_turn_pauses_until_its_reset(self):
        self.begin_issue()
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).replace(microsecond=0)
        agent_runtime.pause_for_provider_limit(self.root, {'limit_type': 'five_hour', 'reset_at': future.isoformat()},
                                               'retained richard')
        status = loop_control.status(self.root)
        self.assertEqual(status['pause_source'], 'provider_limit')
        self.assertAlmostEqual(status['paused_until'], future.timestamp(), delta=1)
        self.assertIn('retained richard', status['pause_reason'])

    def test_no_automatic_pause_for_a_past_reset_an_owner_pause_or_no_loop(self):
        self.begin_issue()
        agent_runtime.pause_for_provider_limit(self.root, {'reset_at': '2020-01-01T00:00:00+00:00'}, 'retained bob')
        self.assertNotIn('paused', loop_control.status(self.root))
        loop_control.pause(self.root, 'owner wants a break')
        agent_runtime.pause_for_provider_limit(self.root, {'reset_at': None}, 'retained bob')
        self.assertEqual(loop_control.status(self.root)['pause_reason'], 'owner wants a break')
        with contextlib.redirect_stderr(io.StringIO()):
            loop_control.cancel(self.root, 'done', now=True)
        agent_runtime.pause_for_provider_limit(self.root, {'reset_at': None}, 'retained bob')  # no loop: no error
        self.assertFalse((self.root / loop_control.STATE).exists())

    def test_a_native_subagent_refused_for_a_limit_is_a_failed_turn_and_pauses_the_loop(self):
        self.begin_issue()
        record = hooks.capture(self.root, {'agent_type': 'bob', 'agent_id': 'b1', 'session_id': 's',
                                           'last_assistant_message': '',
                                           'agent_transcript_path': self.write(USER, say('working'), LIMIT)})
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['error'], 'provider usage limit')
        self.assertEqual(record['provider_limit'], {'limit_type': None, 'reset_at': None})
        self.assertEqual(loop_control.status(self.root)['pause_source'], 'provider_limit')


class NativeFooterReferenceTests(LoopFixture):
    def footer(self, start, **extra):
        return dict({'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                     'correction_round': 0, 'verdict': 'APPROVE', 'must_fix': []}, **extra)

    def stop_with(self, footer, agent='r1'):
        return hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': agent, 'session_id': 's',
                                         'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})

    def test_a_mistyped_evidence_hash_is_caught_when_the_agent_stops(self):
        start = self.begin_issue()
        evidence = verify.run(self.root, 'focused', 'r1', fresh=True)['evidence']
        good = self.stop_with(self.footer(start, independent_check={'evidence': evidence}))
        self.assertEqual(good['status'], 'completed')
        typo = dict(evidence, sha256=evidence['sha256'][:8] + ('5' if evidence['sha256'][8] != '5' else '4')
                    + evidence['sha256'][9:])
        typo['path'] = evidence['path'].replace(evidence['sha256'], typo['sha256'])
        bad = self.stop_with(self.footer(start, verdict='REJECT', must_fix=['x'], independent_check={'evidence': typo}))
        self.assertEqual(bad['status'], 'incomplete')
        self.assertIn('independent_check.evidence', bad['error'])
        self.assertIn('does not resolve', bad['error'])

    def test_evidence_owned_by_another_agent_is_refused(self):
        start = self.begin_issue()
        evidence = verify.run(self.root, 'focused', 'someone-else', fresh=True)['evidence']
        record = self.stop_with(self.footer(start, independent_check={'evidence': evidence}))
        self.assertEqual(record['status'], 'incomplete')
        self.assertIn('owned by someone-else, not by the reporting agent r1', record['error'])

    def test_missing_orientation_and_report_references_are_named(self):
        start = self.begin_issue()
        ghost = {'path': 'devel-loop/loop_state/maintenance/' + '0' * 64 + '.json', 'sha256': '0' * 64}
        record = self.stop_with(self.footer(start, orientation=ghost, documentation_review={'report': ghost}))
        self.assertEqual(record['status'], 'incomplete')
        self.assertIn('orientation:', record['error'])
        self.assertIn('documentation_review.report:', record['error'])

    def test_footers_without_references_and_other_roles_are_unaffected(self):
        start = self.begin_issue()
        self.assertEqual(self.stop_with(self.footer(start))['status'], 'completed')
        scout = hooks.capture(self.root, {'agent_type': 'scout', 'agent_id': 's1', 'session_id': 's',
                                          'last_assistant_message': '```json\n' + json.dumps(
                                              {'agent': 'scout', 'independent_check': {'evidence': {
                                                  'path': 'x', 'sha256': 'y'}}}) + '\n```'})
        self.assertEqual(scout['status'], 'completed')


class AuditAtSealTests(LoopFixture):
    def test_a_plan_cannot_be_sealed_over_a_map_that_does_not_audit(self):
        start = self.begin_issue()
        base = start['maintenance']['baseline']
        code_map = self.root / 'docs/code_map.md'
        code_map.write_text(code_map.read_text() + '\n- Replay helper: `scripts/missing_helper.py::build`\n')
        plan = doc_contract.draft(self.root, start['id'], base)
        for row in plan['dispositions']:
            row.update(action='reviewed_unchanged', references=[row['target']],
                       reason='The touched map row is accurately described by the code map pipeline section.')
        plan['map_delta'] = {'status': 'updated', 'references': ['docs/code_map.md#pipeline'],
                             'reason': 'The pipeline gains a row for the replay helper used by this fixture change.'}
        with self.assertRaisesRegex(ValueError, 'code map does not audit'):
            doc_contract.seal(self.root, plan)

    def test_the_implementer_brief_asks_for_the_audit(self):
        start = self.begin_issue()
        text = brief.build(self.root, 'bob', start['id'], 'Qualify the periodic update.')
        self.assertIn('tools/esx/audit.py', text)
        self.assertIn('report its result verbatim', text)


if __name__ == '__main__':
    unittest.main()
