"""Loop command, autonomous routing and notification delivery failure witnesses.

Provider responses here are fixtures. No unit test sends an external message.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_framework as fixtures
import loop_control
import loop_gate
import notifications
import project
import ralph_stop
import records


class AutonomousTests(unittest.TestCase):
    setUp = fixtures.FrameworkTests.setUp
    write_issue = fixtures.FrameworkTests.write_issue
    prepare = fixtures.FrameworkTests.prepare

    def enable(self):
        p = self.root / 'esx/project.json'
        cfg = json.loads(p.read_text())
        cfg['communication'] = {'provider': 'slack', 'channel': 'C123', 'message_prefix': '[TEST]'}
        p.write_text(json.dumps(cfg))

    def start(self, limit=30):
        self.enable()
        return loop_control.run(self.root, limit)

    def attempted(self):
        for e in notifications.pending(self.root):
            notifications.record(self.root, e['id'], disposition='unavailable',
                detail='Fixture discovery confirms the test has no external Slack provider.', tool='fixture discovery')

    def snapshot(self):
        return json.loads((self.root / notifications.LEDGER).read_text())

    def next(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = loop_gate.Gate(self.root).next()
        return rc, out.getvalue()

    def test_run_reuses_active_budget_and_exact_state(self):
        self.assertEqual(self.start(7)['action'], 'started')
        p = self.root / loop_control.STATE
        before = p.read_bytes()
        self.assertEqual(loop_control.run(self.root)['action'], 'continued')
        self.assertEqual(before, p.read_bytes())
        with self.assertRaisesRegex(ValueError, 'budget differs'):
            loop_control.run(self.root, 30)
        self.assertEqual(before, p.read_bytes())
        self.assertEqual(len(notifications.pending(self.root)), 1)

    def test_run_refuses_external_plugin_and_child(self):
        p = self.root / '.claude/ralph-loop.local.md'
        p.write_text('active plugin')
        with self.assertRaisesRegex(ValueError, 'external Ralph'):
            loop_control.run(self.root)
        p.unlink()
        with patch.dict('os.environ', {'ESX_AGENT_RUNTIME_CHILD': '1'}):
            with self.assertRaisesRegex(ValueError, 'retained role'):
                loop_control.run(self.root)
        self.assertFalse((self.root / loop_control.STATE).exists())

    def test_required_pending_prevents_completion_until_attempt(self):
        self.start()
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('notification', text)
        self.assertNotIn(loop_gate.PROMISE, text)
        self.attempted()
        rc, text = self.next()  # queues the final summary
        self.assertEqual(rc, 0)
        self.assertEqual(notifications.pending(self.root)[0]['kind'], 'loop_end')
        self.attempted()
        rc, text = self.next()
        self.assertEqual(rc, 3)
        self.assertIn(loop_gate.PROMISE, text)

    def test_provider_failure_allows_actionable_scientific_work(self):
        self.write_issue()
        self.start()
        self.attempted()
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('select an issue', text)
        self.assertIn('SAMPLE-001', text)
        self.assertTrue(all(e['attempts'] for e in self.snapshot()['events'].values()))

    def test_receipt_requires_real_shape_destination_and_authorization(self):
        self.start()
        e = notifications.pending(self.root)[0]
        good = {'ok': True, 'channel': 'C123', 'ts': '1789344000.123456'}
        for response in ({}, {**good, 'ok': False}, {**good, 'channel': 'OTHER'}, {**good, 'ts': 'made up'}):
            with self.assertRaises(ValueError):
                notifications.record(self.root, e['id'], response=response, tool='fixture', authorization='test only')
        with self.assertRaisesRegex(ValueError, 'authorization'):
            notifications.record(self.root, e['id'], response=good, tool='fixture')
        notifications.record(self.root, e['id'], response=good, tool='fixture', authorization='test only')
        self.assertEqual(notifications.pending(self.root), [])
        with self.assertRaisesRegex(ValueError, 'already delivered'):
            notifications.record(self.root, e['id'], response=good, tool='fixture', authorization='test only')

    def test_actual_slack_mcp_response_shape(self):
        self.start()
        e = notifications.pending(self.root)[0]
        actual_shape = {'message_link': 'https://workspace.slack.com/archives/C123/p1789536923555129',
                        'message_context': {'channel_id': 'C123', 'message_ts': '1789536923.555129'}}
        notifications.record(self.root, e['id'], response=actual_shape, tool='fixture MCP', authorization='test only')
        self.assertEqual(self.snapshot()['events'][e['id']]['attempts'][0]['response'], actual_shape)

    def test_pending_is_chronological_despite_serialized_hash_order(self):
        self.start()
        d = self.snapshot()
        e = next(iter(d['events'].values()))
        d['events'] = {
            'ffffffff': dict(e, id='ffffffff', created_at='2026-01-01T00:00:00+00:00'),
            'aaaaaaaa': dict(e, id='aaaaaaaa', created_at='2026-01-02T00:00:00+00:00'),
        }
        project.atomic_json(self.root / notifications.LEDGER, d)
        self.assertEqual([e['id'] for e in notifications.pending(self.root)], ['ffffffff','aaaaaaaa'])

    def test_intentions_are_not_delivery_attempts(self):
        self.start()
        e = notifications.pending(self.root)[0]
        for status in ('pending', 'disabled', 'draft'):
            with self.assertRaises(ValueError):
                notifications.record(self.root, e['id'], disposition=status,
                    detail='We intend to eventually send this notification.', tool='fixture')
        with self.assertRaises(ValueError):
            notifications.record(self.root, e['id'], disposition='unavailable', detail='none', tool='fixture')
        self.assertEqual(len(notifications.pending(self.root)), 1)

    def test_new_issue_and_lesson_collected_once_without_backlog_spam(self):
        self.write_issue()
        self.start()
        self.attempted()
        p = self.root / 'open_issues.md'
        p.write_text(p.read_text() + '\n## UNRESOLVED: new finding\n**Status**: Unresolved\n**UUID**: SAMPLE-002\n**Anchors**: src/diffusion.py::step\n')
        with (self.root / 'lessons_learned.md').open('a') as f:
            f.write('\n- [LL-001] Preserve periodic flux conservation. Trigger: changing boundaries.\n')
        with (self.root / 'lessons_learned_evidence.md').open('a') as f:
            f.write('\n## [LL-001] Periodic conservation\nMeasured fixture evidence.\n')
        notifications.synchronize(self.root)
        notifications.synchronize(self.root)
        self.assertEqual([(e['kind'],e['subject']) for e in notifications.pending(self.root)],
                         [('issue_opened','SAMPLE-002'),('lesson','LL-001')])

    def test_closeout_comes_from_validated_history_only_and_refresh_deduplicates(self):
        self.write_issue()
        self.start()
        self.attempted()
        self.root.joinpath('open_issues.md').write_text('# Open issues\n')
        self.root.joinpath('closed_issues.md').write_text('# Closed\n\n## RESOLVED: test\n**Status**: Resolved\n**UUID**: SAMPLE-001\n')
        notifications.synchronize(self.root)
        self.assertFalse(notifications.pending(self.root))
        done = {'id': 'SAMPLE-001', 'timestamp': project.now(), 'outcome': 'completed', 'summary': 'Validated synthetic fixture.'}
        records.save_history(self.root, done)
        notifications.synchronize(self.root)
        self.assertEqual(notifications.pending(self.root)[0]['kind'], 'issue_closeout')
        done['communication'] = {'status': 'sent', 'receipt': 'fixture'}
        records.save_history(self.root, done)
        notifications.synchronize(self.root)
        self.assertEqual(len(notifications.pending(self.root)), 1)

    def test_check_start_requires_notification_attempt(self):
        self.start()
        with contextlib.redirect_stderr(io.StringIO()):
            self.prepare('investigation')
        with self.assertRaisesRegex(ValueError, 'notification'):
            self.gate.check_start()
        self.attempted()
        self.gate.check_start()

    def test_budget_allows_last_work_turn_then_one_bounded_delivery_turn(self):
        self.write_issue()
        self.start(1)
        self.attempted()
        self.assertIn('select an issue', self.next()[1])
        with contextlib.redirect_stderr(io.StringIO()):
            result = ralph_stop.step(self.root, {})
        self.assertEqual(result['decision'], 'block')
        self.assertIn('notification-only', result['reason'])
        self.assertEqual(loop_control.status(self.root)['iteration'], 1)
        self.assertEqual(notifications.pending(self.root)[0]['kind'], 'loop_end')
        self.attempted()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotIn('decision', ralph_stop.step(self.root, {}))
        self.assertFalse((self.root / loop_control.STATE).exists())
        self.assertFalse(notifications.pending(self.root))
        self.assertEqual(sum(e['kind'] == 'loop_end' for e in self.snapshot()['events'].values()), 1)

    def test_unattempted_finalization_cannot_extend_loop_forever(self):
        self.start(1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ralph_stop.step(self.root, {})['decision'], 'block')
            self.assertNotIn('decision', ralph_stop.step(self.root, {}))
        self.assertTrue(notifications.pending(self.root))

    def test_corrupt_records_cannot_prevent_budget_termination(self):
        self.start(1)
        (self.root / 'open_issues.md').write_text('## UNRESOLVED: missing UUID\n')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertNotIn('decision', ralph_stop.step(self.root, {}))
        self.assertFalse((self.root / loop_control.STATE).exists())

    def test_existing_legacy_state_retains_notification_identity_in_finalizer(self):
        self.start(1)
        p = self.root / loop_control.STATE
        p.write_text('\n'.join(line for line in p.read_text().splitlines() if not line.startswith('run_id:')) + '\n')
        # Reset only this disposable ledger to emulate a pre-upgrade loop.
        (self.root / notifications.LEDGER).unlink()
        notifications.synchronize(self.root)
        self.attempted()
        with contextlib.redirect_stderr(io.StringIO()):
            ralph_stop.step(self.root, {})
        notifications.synchronize(self.root)
        self.assertEqual(len(self.snapshot()['runs']), 1)

    def test_cancel_preserves_outbox_and_new_run_gets_new_identity(self):
        self.start()
        with contextlib.redirect_stderr(io.StringIO()):
            loop_control.cancel(self.root)
        self.assertEqual({e['kind'] for e in notifications.pending(self.root)}, {'loop_start','loop_end'})
        self.start()
        self.assertEqual(sum(e['kind'] == 'loop_start' for e in self.snapshot()['events'].values()), 2)

    def test_failure_retry_preserves_history(self):
        self.start()
        e = notifications.pending(self.root)[0]
        self.attempted()
        notifications.record(self.root, e['id'], response={'ok': True, 'channel': 'C123', 'ts': '1789344000.123456'},
            tool='fixture recovered', authorization='test only')
        self.assertEqual(len(self.snapshot()['events'][e['id']]['attempts']), 2)

    def test_no_provider_config_means_no_external_events(self):
        loop_control.run(self.root)
        self.assertEqual(notifications.pending(self.root), [])

    def test_cli_uses_root_with_spaces(self):
        self.enable()
        tool = self.root / 'tools/esx/loop_control.py'
        run = subprocess.run([sys.executable, '-B', str(tool), 'run', '--max-iterations', '2'],
                             cwd=self.root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['max_iterations'], 2)


if __name__ == '__main__':
    unittest.main()
