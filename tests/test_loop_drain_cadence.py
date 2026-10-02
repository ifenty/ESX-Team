"""1.6.0 loop control: cancel drains, quiet holds, start receipts, heartbeats.

Provider responses here are fixtures. No unit test sends an external message.
"""
import contextlib
import datetime as dt
import io
import json
import unittest
from unittest.mock import patch
import fcntl
import uuid
import test_framework as fixtures
import agent_runtime
import hooks
import loop_control
import loop_gate
import loop_iteration
import notifications
import project
import ralph_stop
import records


class LoopFixture(unittest.TestCase):
    setUp = fixtures.FrameworkTests.setUp
    write_issue = fixtures.FrameworkTests.write_issue
    prepare = fixtures.FrameworkTests.prepare
    reflect = fixtures.FrameworkTests.reflect

    def enable(self, **extra):
        p = self.root / 'esx/project.json'
        cfg = json.loads(p.read_text())
        cfg['communication'] = dict({'provider': 'slack', 'channel': 'C123', 'message_prefix': '[TEST]'}, **extra)
        p.write_text(json.dumps(cfg))

    def run_loop(self, limit=30, **extra):
        self.enable(**extra)
        return loop_control.run(self.root, limit)

    def attempted(self):
        for e in notifications.pending(self.root):
            notifications.record(self.root, e['id'], disposition='unavailable',
                detail='Fixture discovery confirms the test has no external Slack provider.', tool='fixture discovery')

    def events(self):
        return json.loads((self.root / notifications.LEDGER).read_text())['events'].values()

    def next(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = loop_gate.Gate(self.root).next()
        return rc, out.getvalue()

    def stop(self, **event):
        with contextlib.redirect_stderr(io.StringIO()):
            return ralph_stop.step(self.root, event)

    def prepared_without_check(self, **extra):
        """An iteration prepared and announced, but with no --check-start yet."""
        self.write_issue()
        self.run_loop(**extra)
        self.attempted()
        self.reflect()
        self.gate = loop_gate.Gate(self.root)
        with contextlib.redirect_stderr(io.StringIO()):
            self.gate.prepare(self.issue, 'investigation', (), 'arch', 'Qualify the periodic boundary update.',
                              'docs/code_map.md#pipeline', ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'],
                              ['docs/model_contract.md'],
                              'Trace the periodic update into its Fourier and conservation oracle before evaluating acceptance.')
        notifications.synchronize(self.root)
        self.attempted()
        return self.gate.read('issue-start.json')

    def begin_issue(self, **extra):
        """An active iteration: prepared, announced and start-checked."""
        start = self.prepared_without_check(**extra)
        self.gate.check_start()
        return start

    def close_issue(self, start):
        records.save_history(self.root, {'id': start['id'], 'timestamp': start['timestamp'],
                                         'iteration': start['iteration'], 'state_version': start['state_version'],
                                         'outcome': 'partial', 'summary': 'Recorded the synthetic fixture.',
                                         'closed_at': project.now()})
        self.reflect()

    def state_text(self):
        return (self.root / loop_control.STATE).read_text()


class CancelDrainTests(LoopFixture):
    """The owner's rule: cancel never stops the loop mid-issue; it stops the next iteration."""

    def test_cancel_during_an_iteration_keeps_the_loop_working_until_it_closes(self):
        start = self.begin_issue()
        result = loop_control.cancel(self.root, 'Owner requested cancellation')
        self.assertEqual(result['status'], 'cancelling')
        self.assertEqual(result['finishing'], start['id'])
        self.assertTrue((self.root / loop_control.STATE).exists())
        status = loop_control.status(self.root)
        self.assertTrue(status['cancelling'])
        self.assertEqual(status['cancel_reason'], 'Owner requested cancellation')
        # The Stop hook still drives the active iteration.
        self.assertEqual(self.stop()['decision'], 'block')
        notifications.synchronize(self.root)
        self.attempted()
        self.assertIn('finish active iteration', self.next()[1])
        # Notifications still queue: the closeout is announced, not lost.
        self.close_issue(start)
        notifications.synchronize(self.root)
        self.assertIn('issue_closeout', {e['kind'] for e in notifications.pending(self.root)})
        self.attempted()
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('the owner cancelled the loop (Owner requested cancellation)', text)
        self.assertIn('Do not select an issue', text)
        self.assertNotIn('select an issue by impact', text)
        # The loop ends where the next iteration would have started.
        result = self.stop()
        self.assertEqual(result['decision'], 'block')
        self.assertIn('notification-only', result['reason'])
        ending = [e for e in notifications.pending(self.root) if e['kind'] == 'loop_end']
        self.assertEqual(len(ending), 1)
        self.assertIn('Loop ending: cancelled: Owner requested cancellation', ending[0]['text'])
        self.assertIn('No iteration is in progress', ending[0]['text'])
        self.attempted()
        self.assertNotIn('decision', self.stop())
        self.assertFalse((self.root / loop_control.STATE).exists())
        self.assertEqual(len(list((self.root / '.claude').glob('esx-loop.local.md.cancelled.*'))), 1)

    def test_owed_retrospective_is_part_of_the_iteration_being_finished(self):
        start = self.begin_issue()
        loop_control.cancel(self.root, 'stop after this one')
        records.save_history(self.root, {'id': start['id'], 'timestamp': start['timestamp'],
                                         'iteration': start['iteration'], 'state_version': start['state_version'],
                                         'outcome': 'partial', 'summary': 'Recorded the synthetic fixture.'})
        self.assertEqual(ralph_stop.work_in_progress(self.root), start['id'])
        notifications.synchronize(self.root)
        self.attempted()
        self.assertIn('RETROSPECTIVE', self.next()[1])
        self.assertTrue((self.root / loop_control.STATE).exists())

    def test_cancel_with_nothing_in_progress_ends_at_once(self):
        self.run_loop()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop_control.cancel(self.root, 'not needed')['status'], 'cancelled')
        self.assertFalse((self.root / loop_control.STATE).exists())
        self.assertIn('cancelled: not needed', [e for e in self.events() if e['kind'] == 'loop_end'][0]['text'])

    def test_abort_abandons_the_active_iteration_and_says_so(self):
        start = self.begin_issue()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(loop_control.cancel(self.root, 'emergency', now=True)['status'], 'cancelled')
        self.assertFalse((self.root / loop_control.STATE).exists())
        text = [e for e in self.events() if e['kind'] == 'loop_end'][0]['text']
        self.assertIn(f"Unfinished work on {start['id']} remains recorded on disk", text)

    def test_continuing_the_loop_withdraws_a_pending_cancel(self):
        self.begin_issue()
        loop_control.cancel(self.root, 'changed my mind later')
        result = loop_control.run(self.root)
        self.assertEqual(result['cancellation'], 'withdrawn')
        self.assertNotIn('stop_after_current', self.state_text())
        self.assertNotIn('cancelling', loop_control.status(self.root))


class AdvanceRateTests(LoopFixture):
    def test_more_advances_than_real_work_allows_are_withheld_and_logged(self):
        self.run_loop(limit=200)
        moment = [1000.0]
        with patch.object(ralph_stop, 'clock', lambda: moment[0]):
            for _ in range(ralph_stop.MAX_ADVANCES_PER_MINUTE):
                self.assertEqual(self.stop()['decision'], 'block')
                moment[0] += 1
            before = self.state_text()
            result = self.stop()
            self.assertNotIn('decision', result)
            self.assertIn('paused', result['systemMessage'])
            self.assertEqual(self.state_text(), before)
            self.assertIn('ANOMALY', (self.root / '.claude/esx-loop-exit.log').read_text())
            moment[0] += 61
            self.assertEqual(self.stop()['decision'], 'block')


class StartReceiptTests(LoopFixture):
    def test_next_demands_check_start_before_any_dispatch(self):
        start = self.prepared_without_check()
        text = self.next()[1]
        self.assertIn(f"NEXT: run --check-start for {start['id']} now, before any dispatch or edit", text)
        self.assertNotIn('--check-done', text)
        self.gate.check_start()
        self.assertIn('finish active iteration', self.next()[1])

    def test_late_check_start_is_possible_only_with_a_reason_and_is_flagged(self):
        start = self.prepared_without_check()
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text().replace('def step(', 'def step(  # edited by the work\n        ', 1))
        with self.assertRaisesRegex(ValueError, '--late-reason'):
            self.gate.check_start()
        with self.assertRaisesRegex(ValueError, 'at least 40 characters'):
            self.gate.check_start('forgot')
        reason = 'The implementer was dispatched right after --prepare; the check was missed.'
        self.gate.check_start(reason)
        status = loop_iteration.start_status(self.root, start)
        self.assertTrue(status['validated'])
        self.assertEqual(status['late'], {'reason': reason})

    def test_timely_check_start_is_not_marked_late(self):
        start = self.prepared_without_check()
        self.gate.check_start()
        self.assertNotIn('late', loop_iteration.start_status(self.root, start))


class HeartbeatTests(LoopFixture):
    def later(self, minutes):
        stamp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).isoformat()
        return patch.object(notifications, 'now', lambda: stamp)

    def test_heartbeat_replaces_per_iteration_progress_and_is_one_sentence(self):
        start = self.begin_issue(heartbeat_minutes=60)
        self.stop()  # iteration 2
        notifications.synchronize(self.root)
        self.assertNotIn('progress', {e['kind'] for e in self.events()})
        self.assertIsNone(notifications.heartbeat(self.root))  # not due yet
        with self.later(61):
            identity = notifications.heartbeat(self.root)
        self.assertIsNotNone(identity)
        text = next(e for e in self.events() if e['id'] == identity)['text']
        self.assertTrue(text.startswith('[TEST] Loop iteration 2/30: working on ' + start['id']))
        self.assertIn('remaining; 1 open issues.', text)
        self.assertEqual(text.count('. '), 0)  # one sentence
        with self.later(90):
            self.assertIsNone(notifications.heartbeat(self.root))  # next one is due an hour after the last
        with self.later(125):
            self.assertIsNotNone(notifications.heartbeat(self.root))
        self.assertEqual(sum(e['kind'] == 'loop_heartbeat' for e in self.events()), 2)

    def test_heartbeat_waits_while_another_event_was_just_queued(self):
        self.begin_issue(heartbeat_minutes=60)
        with self.later(61):
            (self.root / 'open_issues.md').write_text(
                (self.root / 'open_issues.md').read_text()
                + '\n## UNRESOLVED: Second sample\n**Status**: Unresolved\n**UUID**: SAMPLE-002\n'
                  '**Anchors**: src/diffusion.py::step\n')
            notifications.synchronize(self.root)  # queues issue_opened at this moment
            self.assertNotIn('loop_heartbeat', {e['kind'] for e in self.events()})
        with self.later(61 + 11):
            self.assertIsNotNone(notifications.heartbeat(self.root))

    def test_project_without_the_setting_keeps_progress_posts_and_gets_no_heartbeat(self):
        self.begin_issue()
        self.stop()
        notifications.synchronize(self.root)
        self.assertIn('progress', {e['kind'] for e in self.events()})
        with self.later(600):
            self.assertIsNone(notifications.heartbeat(self.root))

    def test_status_line_and_next_report_where_the_loop_is(self):
        start = self.begin_issue()
        line = loop_control.status_line(self.root)
        self.assertRegex(line, r'^ESX status \d\d:\d\d: Loop iteration 1/30: working on ' + start['id'])
        self.assertIn('STATUS: Loop iteration 1/30', self.next()[1])
        loop_control.cancel(self.root, 'later')
        self.assertIn('cancelling after the current issue on ' + start['id'], loop_control.status_line(self.root))
        with contextlib.redirect_stderr(io.StringIO()):
            loop_control.cancel(self.root, 'now', now=True)
        self.assertIn('no active loop', loop_control.status_line(self.root))


class LoopEndTextTests(LoopFixture):
    def test_unsent_ending_is_superseded_when_the_loop_goes_on(self):
        self.run_loop()
        self.attempted()
        notifications.synchronize(self.root, terminal='no actionable work')
        first = [e for e in self.events() if e['kind'] == 'loop_end']
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]['status'], 'pending')
        self.stop()  # the loop continued instead of ending
        notifications.synchronize(self.root)
        self.assertEqual([e['status'] for e in self.events() if e['kind'] == 'loop_end'], ['superseded'])
        self.assertNotIn('loop_end', {e['kind'] for e in notifications.pending(self.root)})
        notifications.synchronize(self.root, terminal='iteration budget 30 reached')
        pending = [e for e in notifications.pending(self.root) if e['kind'] == 'loop_end']
        self.assertEqual(len(pending), 1)
        self.assertIn('iteration budget 30 reached', pending[0]['text'])

    def test_promise_mechanism_does_not_overwrite_the_recorded_reason(self):
        self.run_loop()
        self.attempted()
        notifications.synchronize(self.root, terminal='no actionable work')
        notifications.synchronize(self.root, terminal='current completion promise fulfilled')
        text = [e for e in self.events() if e['kind'] == 'loop_end'][0]['text']
        self.assertIn('Loop ending: no actionable work.', text)

    def test_one_ending_is_announced_once(self):
        self.run_loop()
        self.attempted()
        notifications.synchronize(self.root, terminal='no actionable work')
        self.attempted()
        notifications.synchronize(self.root, terminal='current completion promise fulfilled')
        self.assertEqual(sum(e['kind'] == 'loop_end' for e in self.events()), 1)
        self.assertFalse(notifications.pending(self.root))


class SubagentIdentityTests(LoopFixture):
    def test_a_native_subagent_is_told_its_own_runtime_id(self):
        context = hooks.started(self.root, {'agent_id': 'aab958da274affe3e', 'agent_type': 'richard', 'session_id': 's1'})
        self.assertIn('your runtime agent id is aab958da274affe3e', context)
        self.assertIn('--owner', context)
        self.assertNotIn('warning', context)
        self.assertEqual(hooks.whoami(self.root, 'richard'), 'aab958da274affe3e')

    def test_whoami_refuses_to_guess(self):
        with self.assertRaisesRegex(ValueError, '0 running richard'):
            hooks.whoami(self.root, 'richard')
        hooks.started(self.root, {'agent_id': 'r1', 'agent_type': 'richard', 'session_id': 's1'})
        hooks.started(self.root, {'agent_id': 'r2', 'agent_type': 'richard', 'session_id': 's1'})
        hooks.started(self.root, {'agent_id': 'b1', 'agent_type': 'bob', 'session_id': 's1'})
        with self.assertRaisesRegex(ValueError, '2 running richard'):
            hooks.whoami(self.root, 'richard')
        self.assertEqual(hooks.whoami(self.root, 'bob'), 'b1')

    def test_a_role_launched_before_check_start_is_warned(self):
        start = self.prepared_without_check()
        context = hooks.started(self.root, {'agent_id': 'b1', 'agent_type': 'bob', 'session_id': 's1'})
        self.assertIn(f"iteration {start['id']} has no --check-start receipt", context)
        self.gate.check_start()
        self.assertNotIn('warning', hooks.started(self.root, {'agent_id': 'b2', 'agent_type': 'bob', 'session_id': 's1'}))


class RetainedTurnTests(LoopFixture):
    def configure(self, value):
        p = self.root / 'esx/project.json'
        cfg = json.loads(p.read_text())
        cfg['runtime'] = {'turn_timeout_seconds': value}
        p.write_text(json.dumps(cfg))

    def test_turn_timeout_depends_on_role_project_and_explicit_request(self):
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'bob'), 3600)
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'richard'), 1800)
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'bob', 120), 120)
        self.configure(2400)
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'richard'), 2400)
        self.configure({'bob': 5400, 'default': 2000})
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'bob'), 5400)
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'scout'), 2000)
        self.configure({'bob': 5400})
        self.assertEqual(agent_runtime.turn_timeout(self.root, 'richard'), 1800)
        self.configure('long')
        with self.assertRaisesRegex(ValueError, 'positive number'):
            agent_runtime.turn_timeout(self.root, 'bob')

    def test_wait_blocks_while_a_turn_lock_is_held_and_returns_when_it_is_free(self):
        session = str(uuid.uuid4())
        folder = agent_runtime.session_path(self.root, session)
        folder.mkdir(parents=True)
        self.assertEqual(agent_runtime.wait_for_turns(self.root, 5, session, poll=0.01)['status'], 'idle')
        with (folder / '.turn.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            result = agent_runtime.wait_for_turns(self.root, 0.05, session, poll=0.01)
            self.assertEqual(result['status'], 'running')
            self.assertIn('run wait again', result['next'])
            fcntl.flock(handle, fcntl.LOCK_UN)
        self.assertEqual(agent_runtime.wait_for_turns(self.root, 5, session, poll=0.01)['status'], 'idle')
        self.assertEqual(agent_runtime.wait_for_turns(self.root, 5, poll=0.01)['status'], 'idle')

    def test_a_retained_wait_reads_as_status_and_names_the_helper(self):
        self.run_loop()
        with patch.object(ralph_stop, 'retained_in_flight', return_value=True):
            result = self.stop()
        self.assertEqual(result['decision'], 'block')
        self.assertTrue(result['reason'].startswith('ESX status, not an error'))
        self.assertIn('agent_runtime.py wait', result['reason'])
        self.assertIn('iteration: 1', self.state_text())


if __name__ == '__main__':
    unittest.main()
