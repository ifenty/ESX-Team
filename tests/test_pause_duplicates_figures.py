"""1.6.2: loop pause, provider usage limits, repeated agent stops, superseded figures.

Offline: synthetic deployment fixture, no provider calls.
"""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework  # noqa: F401  (puts the template tools on sys.path)
from test_loop_drain_cadence import LoopFixture
import agent_runtime
import brief
import doc_contract
import hooks
import loop_control
import notifications
import project
import ralph_stop
import records
import workflow_policy
import workflow_records


class PauseTests(LoopFixture):
    def test_a_paused_loop_lets_turns_end_and_changes_nothing(self):
        start = self.begin_issue(heartbeat_minutes=60)
        result = loop_control.pause(self.root, 'provider usage limit')
        self.assertEqual(result['status'], 'paused')
        before = self.state_text()
        for _ in range(ralph_stop.MAX_DISPATCH_WAITS + ralph_stop.MAX_ADVANCES + 2):
            outcome = self.stop(last_assistant_message='<promise>ESX-LOOP-NO-ACTIONABLE-WORK</promise>')
            self.assertNotIn('decision', outcome)
            self.assertIn('paused', outcome['systemMessage'])
            self.assertIn('provider usage limit', outcome['systemMessage'])
        self.assertEqual(self.state_text(), before)  # no iteration, wait count, advance stamp or ending
        self.assertTrue((self.root / loop_control.STATE).exists())
        self.assertIn('PAUSED', (self.root / '.claude/esx-loop-exit.log').read_text())
        status = loop_control.status(self.root)
        self.assertTrue(status['paused'])
        self.assertEqual(status['pause_reason'], 'provider usage limit')
        self.assertIn('paused (provider usage limit) on ' + start['id'], loop_control.status_line(self.root))
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('PAUSED: the loop is paused (provider usage limit)', text)
        self.assertNotIn('NEXT:', text)
        stamp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=600)).isoformat()
        with patch.object(notifications, 'now', lambda: stamp):
            self.assertIsNone(notifications.heartbeat(self.root))  # no heartbeat while paused

    def test_resuming_continues_at_the_same_iteration(self):
        self.begin_issue()
        loop_control.pause(self.root, 'usage limit')
        self.stop()
        resumed = loop_control.run(self.root)
        self.assertEqual(resumed['pause'], 'resumed')
        self.assertEqual(resumed['iteration'], 1)
        self.assertNotIn('paused', self.state_text())
        self.assertEqual(self.stop()['decision'], 'block')
        self.assertIn('iteration: 2', self.state_text())

    def test_a_timed_pause_lifts_itself_and_leaves_no_fields_behind(self):
        self.run_loop()
        moment = [1_000_000.0]
        with patch.object(ralph_stop, 'clock', lambda: moment[0]):
            loop_control.pause(self.root, 'usage limit', minutes=30)
            self.assertNotIn('decision', self.stop())
            moment[0] += 29 * 60
            self.assertNotIn('decision', self.stop())
            moment[0] += 2 * 60
            self.assertNotIn('paused', loop_control.status(self.root))
            self.assertEqual(self.stop()['decision'], 'block')
        text = self.state_text()
        self.assertIn('iteration: 2', text)
        for field in ('paused:', 'pause_reason:', 'paused_until:'):
            self.assertNotIn(field, text)

    def test_until_takes_an_iso_time_with_an_offset(self):
        self.run_loop()
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)).replace(microsecond=0)
        result = loop_control.pause(self.root, 'usage limit', until=future.isoformat())
        self.assertAlmostEqual(result['paused_until'], future.timestamp(), delta=1)
        for bad, message in (({'until': '2020-01-01T00:00:00+00:00'}, 'in the past'),
                             ({'until': '2099-01-01T00:00:00'}, 'UTC offset'),
                             ({'until': 'tomorrow'}, 'ISO time'),
                             ({'minutes': 5, 'until': future.isoformat()}, 'not both'),
                             ({'minutes': 0}, 'positive')):
            with self.assertRaisesRegex(ValueError, message):
                loop_control.pause(self.root, 'usage limit', **bad)
        with self.assertRaisesRegex(ValueError, 'needs a reason'):
            loop_control.pause(self.root, '  ')

    def test_a_cancel_survives_a_pause_and_abort_works_at_once(self):
        self.begin_issue()
        loop_control.cancel(self.root, 'stop after this issue')
        loop_control.pause(self.root, 'usage limit')
        self.assertIn('stop_after_current: true', self.state_text())
        self.assertNotIn('decision', self.stop())
        resumed = loop_control.run(self.root)
        self.assertEqual(resumed['pause'], 'resumed')
        self.assertNotIn('cancellation', resumed)  # resuming does not withdraw the cancel
        self.assertTrue(loop_control.status(self.root)['cancelling'])
        loop_control.pause(self.root, 'usage limit')
        self.assertEqual(loop_control.resume(self.root)['pause'], 'resumed')
        self.assertTrue(loop_control.status(self.root)['cancelling'])
        loop_control.pause(self.root, 'usage limit')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop_control.cancel(self.root, 'emergency', now=True)['status'], 'cancelled')
        self.assertFalse((self.root / loop_control.STATE).exists())

    def test_pause_needs_an_active_loop(self):
        with self.assertRaisesRegex(ValueError, 'no active ESX loop'):
            loop_control.pause(self.root, 'usage limit')
        self.assertEqual(loop_control.resume(self.root)['status'], 'inactive')


class ProviderLimitTests(LoopFixture):
    REJECTED = {'type': 'rate_limit_event', 'rate_limit_info': {
        'status': 'rejected', 'resetsAt': 1790974800, 'rateLimitType': 'five_hour', 'overageStatus': 'rejected'}}
    RESULT = {'type': 'result', 'subtype': 'success', 'is_error': True, 'terminal_reason': 'api_error',
              'api_error_status': 429, 'stop_reason': 'stop_sequence',
              'result': "You've hit your session limit · resets 2pm (America/Los_Angeles)"}

    def stream(self, *events):
        path = Path(tempfile.mkdtemp(dir=self.root)) / 'stdout.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def test_refusal_is_read_from_the_stream_not_the_text(self):
        found = agent_runtime.provider_limit(self.stream(self.REJECTED, self.RESULT))
        self.assertEqual(found, {'limit_type': 'five_hour', 'reset_at': '2026-10-02T21:00:00+00:00'})
        self.assertEqual(agent_runtime.provider_limit(self.stream(self.RESULT)),
                         {'limit_type': None, 'reset_at': None})

    def test_allowed_events_and_ordinary_failures_are_not_limits(self):
        allowed = {'type': 'rate_limit_event', 'rate_limit_info': {'status': 'allowed_warning', 'resetsAt': 1790974800}}
        failed = {'type': 'result', 'is_error': True, 'result': 'the tool crashed', 'api_error_status': 500}
        self.assertIsNone(agent_runtime.provider_limit(self.stream(allowed, failed)))
        self.assertIsNone(agent_runtime.provider_limit(self.root / 'missing.jsonl'))

    def record(self, start, reset):
        with (self.root / project.STATE / 'dispatch_log.jsonl').open('a') as handle:
            handle.write(json.dumps({'event_id': 'e-limit', 'agent_id': 's1', 'agent_type': 'richard',
                                     'issue_id': start['id'], 'status': 'failed',
                                     'provider_limit': {'limit_type': 'five_hour', 'reset_at': reset}}) + '\n')

    def test_next_recommends_a_pause_until_the_reset(self):
        start = self.begin_issue()
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).replace(microsecond=0).isoformat()
        self.record(start, future)
        text = self.next()[1]
        self.assertIn('LIMIT: the provider refused the last richard turn', text)
        self.assertIn(f'--until {future}', text)
        self.assertIn('do not correct or replace the role', text)

    def test_a_limit_that_has_reset_is_not_announced(self):
        start = self.begin_issue()
        self.record(start, '2020-01-01T00:00:00+00:00')
        self.assertNotIn('LIMIT:', self.next()[1])


class RepeatedStopTests(LoopFixture):
    def stop_event(self, agent, footer):
        return hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': agent, 'session_id': 's',
                                         'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})

    def footer(self, start, **extra):
        return dict({'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                     'correction_round': 1, 'verdict': 'APPROVE', 'must_fix': [],
                     'candidate_signature': 'a' * 64}, **extra)

    def test_a_stop_that_repeats_the_same_report_is_a_duplicate_not_a_new_completion(self):
        start = self.begin_issue()
        first = self.stop_event('r1', self.footer(start))
        second = self.stop_event('r1', self.footer(start))
        third = self.stop_event('r1', self.footer(start))
        self.assertNotIn('duplicate_of', first)
        self.assertEqual(second['duplicate_of'], first['event_id'])
        self.assertEqual(third['duplicate_of'], first['event_id'])  # always the original
        log = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        self.assertEqual([r['event_id'] for r in log][-3:], [first['event_id'], second['event_id'], third['event_id']])
        done = {'id': start['id'], 'timestamp': start['timestamp']}
        self.assertTrue(workflow_policy.current_review(first, log, done, 'a' * 64))
        self.assertTrue(workflow_policy.duplicate(second))

    def test_a_different_report_or_another_agent_is_a_new_completion(self):
        start = self.begin_issue()
        first = self.stop_event('r1', self.footer(start))
        changed = self.stop_event('r1', self.footer(start, verdict='REJECT', must_fix=['x']))
        other = self.stop_event('r2', self.footer(start))
        again = self.stop_event('r1', self.footer(start))  # same as `first`, but not the agent's last record
        for record in (changed, other, again):
            self.assertNotIn('duplicate_of', record)
        log = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        done = {'id': start['id'], 'timestamp': start['timestamp']}
        self.assertFalse(workflow_policy.current_review(first, log, done, 'a' * 64))
        self.assertTrue(workflow_policy.current_review(again, log, done, 'a' * 64))

    def test_a_duplicate_cannot_be_selected_into_a_packet(self):
        start = self.begin_issue()
        first = self.stop_event('r1', self.footer(start))
        second = self.stop_event('r1', self.footer(start))
        log = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        with self.assertRaisesRegex(ValueError, f"only repeats completion {first['event_id']}"):
            workflow_records.import_completion(start, log, {'agent': 'richard', 'dispatch_id': 'r1',
                                                            'dispatch_event_id': second['event_id'],
                                                            'correction_round': 1})

    def test_incomplete_stops_are_never_duplicates(self):
        self.begin_issue()
        first = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': 'r1', 'session_id': 's',
                                          'last_assistant_message': 'no footer'})
        second = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': 'r1', 'session_id': 's',
                                           'last_assistant_message': 'no footer'})
        self.assertEqual((first['status'], second['status']), ('incomplete', 'incomplete'))
        self.assertNotIn('duplicate_of', second)


class SupersededFigureTests(LoopFixture):
    def test_a_figure_matches_as_a_whole_token_with_or_without_separators(self):
        pattern = doc_contract.figure_pattern('456')
        for text in ('456 cells', '(456)', 'were 456.', '456, and', 'is 456'):
            self.assertTrue(pattern.search(text), text)
        for text in ('1456', '4567', '0.456', '456.2', 'x456', '456_cells', '1,456'):
            self.assertFalse(pattern.search(text), text)
        self.assertTrue(doc_contract.figure_pattern('17934').search('17,934 real cells'))
        self.assertTrue(doc_contract.figure_pattern('17,934').search('17934 real cells'))
        self.assertFalse(doc_contract.figure_pattern('17934').search('117934'))
        self.assertTrue(doc_contract.figure_pattern('26-41 m').search('max hbl diff 26-41 m)'))
        self.assertTrue(doc_contract.figure_pattern('real kSrf gap').search('a real kSrf gap remains'))

    def table(self, text):
        path = self.root / doc_contract.figures_path('SAMPLE-001')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_stale_lists_every_inventoried_line_that_still_has_an_old_figure(self):
        contract = self.root / 'docs/model_contract.md'
        contract.write_text(contract.read_text() + '\nThe gap is 17,934 cells.\nNow 16123 cells remain.\n')
        (self.root / 'src/diffusion.py').write_text(
            (self.root / 'src/diffusion.py').read_text() + '\n# the old tail was 26-41 m\n')
        rows = doc_contract.read_figures(self.table(
            '# superseded by SAMPLE-001\n17934\t16123\ttke cells\n26-41 m\t0.029 m\thbl max\n\nno hit\n'))
        self.assertEqual(rows[0], {'old': '17934', 'new': '16123', 'note': 'tke cells'})
        self.assertEqual(rows[2], {'old': 'no hit', 'new': '', 'note': ''})
        found = doc_contract.stale_lines(self.root, rows)
        self.assertEqual((found['figures'], found['lines'], found['truncated']), (3, 2, 0))
        where = {(hit['figure'], hit['path']) for hit in found['hits']}
        self.assertEqual(where, {('17934', 'docs/model_contract.md'), ('26-41 m', 'src/diffusion.py')})
        self.assertEqual(doc_contract.stale_lines(self.root, rows, limit=1)['truncated'], 1)

    def test_a_row_without_a_figure_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'first column'):
            doc_contract.read_figures(self.table('\tnew\tnote\n'))

    def test_the_brief_lists_the_lines_for_the_issue_table_and_given_figures(self):
        start = self.begin_issue()
        contract = self.root / 'docs/model_contract.md'
        contract.write_text(contract.read_text() + '\nThe gap is 17,934 cells and the tail is 26-41 m.\n')
        self.table('17934\t16123\ttke cells\n')
        text = brief.build(self.root, 'bob', start['id'], 'Re-measure the gap.', sweep_figures=['26-41 m'])
        self.assertIn('# Superseded figures still present', text)
        self.assertIn('[17934 -> 16123]', text)
        self.assertIn('[26-41 m]', text)
        self.assertIn('docs/model_contract.md:', text)
        self.assertIn('doc_contract.py stale --issue ISSUE', text)  # the working rule
        self.assertNotIn('# Superseded figures still present',
                         brief.build(self.root, 'bob', start['id'], 'No figures here.') if not
                         (self.root / doc_contract.figures_path(start['id'])).unlink() else '')


if __name__ == '__main__':
    unittest.main()
