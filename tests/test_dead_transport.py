"""Session-scoped provider outage: one recorded discovery, forced re-probes.

Provider behavior here is a fixture. No unit test sends an external message.
"""
import contextlib
import io
import json
import re
import unittest
import test_framework as fixtures
import loop_control
import loop_gate
import notifications

EVIDENCE = 'Slack exposes only authenticate/complete_authentication; slack_send_message is absent.'


class DeadTransportTests(unittest.TestCase):
    setUp = fixtures.FrameworkTests.setUp
    write_issue = fixtures.FrameworkTests.write_issue

    def start(self):
        self.write_issue()
        p = self.root / 'esx/project.json'
        cfg = json.loads(p.read_text())
        cfg['communication'] = {'provider': 'slack', 'channel': 'C123', 'message_prefix': '[TEST]'}
        p.write_text(json.dumps(cfg))
        loop_control.run(self.root, 30)

    def iterate(self, n):
        p = self.root / loop_control.STATE
        p.write_text(re.sub(r'(?m)^iteration: \d+$', f'iteration: {n}', p.read_text()))

    def file_issues(self, first, count):
        p = self.root / 'open_issues.md'
        text = p.read_text()
        for i in range(first, first + count):
            text += f'\n## UNRESOLVED: finding {i}\n**Status**: Unresolved\n**UUID**: SAMPLE-{i:03d}\n**Anchors**: src/diffusion.py::step\n'
        p.write_text(text)
        notifications.synchronize(self.root)

    def declare(self):
        return notifications.outage(self.root, 'slack', 'ToolSearch slack send', EVIDENCE)

    def next(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = loop_gate.Gate(self.root).next()
        return rc, out.getvalue()

    def ledger(self):
        return json.loads((self.root / notifications.LEDGER).read_text())

    def test_one_outage_covers_queued_and_later_events(self):
        self.start()
        self.file_issues(2, 2)
        queued = [e['id'] for e in notifications.pending(self.root)]
        self.assertEqual(len(queued), 3)
        o = self.declare()
        self.assertEqual(o['covered'], queued)
        self.assertEqual(notifications.pending(self.root), [])
        self.file_issues(4, 1)
        data = self.ledger()
        self.assertEqual(notifications.pending(self.root), [])
        later = [e for e in data['events'].values() if e['subject'] == 'SAMPLE-004']
        self.assertEqual(later[0]['status'], 'outage_covered')
        self.assertEqual(later[0]['outage'], o['id'])
        self.assertEqual(later[0]['attempts'], [])  # not individually adjudicated
        self.assertEqual(len(data['outages'][o['id']]['probes']), 1)  # discovery recorded once
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('select an issue', text)

    def test_status_separates_outage_coverage_from_failed(self):
        self.start()
        first = notifications.pending(self.root)[0]['id']
        notifications.record(self.root, first, disposition='failed', tool='slack_send_message',
                             detail='Executed send returned channel_not_found for C123.')
        self.file_issues(2, 1)
        self.declare()
        summary = notifications.status(self.root)['summary']
        self.assertEqual(summary['failed'], [first])
        self.assertEqual(len(summary['outage_covered']), 1)
        self.assertNotIn(first, summary['outage_covered'])
        self.assertEqual(summary['by_status'], {'failed': 1, 'outage_covered': 1})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(notifications.main(['--root', str(self.root), 'status']), 0)
        self.assertEqual(json.loads(out.getvalue())['summary']['failed'], [first])

    def test_reprobe_forced_each_iteration(self):
        self.start()
        self.declare()
        self.assertIn('select an issue', self.next()[1])
        self.iterate(2)
        rc, text = self.next()
        self.assertEqual(rc, 0)
        self.assertIn('re-probe the slack provider', text)
        self.assertIn('no probe recorded in loop iteration 2', text)
        self.assertNotIn('select an issue', text)
        notifications.reprobe(self.root, 'slack', 'ToolSearch slack send', 'down', EVIDENCE)
        self.assertIn('select an issue', self.next()[1])

    def test_reprobe_forced_every_n_covered_events(self):
        self.start()
        self.declare()
        self.file_issues(2, notifications.OUTAGE_PROBE_EVENTS - 1)
        self.assertIn('select an issue', self.next()[1])
        self.file_issues(2 + notifications.OUTAGE_PROBE_EVENTS, 1)
        self.assertEqual(notifications.pending(self.root), [])
        text = self.next()[1]
        self.assertIn(f'{notifications.OUTAGE_PROBE_EVENTS} events covered since the last probe', text)
        self.assertNotIn('select an issue', text)
        notifications.reprobe(self.root, 'slack', 'ToolSearch slack send', 'down', EVIDENCE)
        self.assertIn('select an issue', self.next()[1])

    def test_outage_bound_requires_renewal_with_fresh_evidence(self):
        self.start()
        self.declare()
        bound = 1 + notifications.OUTAGE_RENEW_ITERATIONS
        self.iterate(bound)
        with self.assertRaisesRegex(ValueError, 'renew'):
            notifications.reprobe(self.root, 'slack', 'ToolSearch slack send', 'down', EVIDENCE)
        self.file_issues(2, 1)
        # New issue and this iteration's progress event are no longer silently covered.
        self.assertEqual(sorted(e['kind'] for e in notifications.pending(self.root)), ['issue_opened', 'progress'])
        text = self.next()[1]
        self.assertIn('deliver 2 pending', text)
        self.assertIn('renew', text)
        with self.assertRaisesRegex(ValueError, 'probe evidence'):
            notifications.outage(self.root, 'slack', 'ToolSearch slack send', 'still down')
        o = notifications.outage(self.root, 'slack', 'ToolSearch slack send', EVIDENCE + ' Re-checked.')
        self.assertEqual([p['result'] for p in o['probes']], ['declared', 'renewed'])
        self.assertEqual(o['bound_iteration'], bound)
        self.assertEqual(len(self.ledger()['outages']), 1)
        self.assertEqual(notifications.pending(self.root), [])
        self.assertIn('select an issue', self.next()[1])

    def test_clear_requires_reprobe_and_later_events_are_individual(self):
        self.start()
        o = self.declare()
        self.iterate(2)
        with self.assertRaisesRegex(ValueError, 'probe evidence'):
            notifications.reprobe(self.root, 'slack', 'slack_send_message', 'up', 'ok')
        cleared = notifications.reprobe(self.root, 'slack', 'slack_send_message', 'up',
                                        'slack_send_message is listed again and a probe post returned ts.')
        self.assertEqual(cleared['status'], 'cleared')
        self.file_issues(2, 1)
        events = self.ledger()['events'].values()
        self.assertEqual(sum(e['status'] == 'outage_covered' for e in events), len(o['covered']))
        # Events queued after clearing (new issue, this iteration's progress) are individual again.
        self.assertEqual(sorted(e['kind'] for e in notifications.pending(self.root)), ['issue_opened', 'progress'])
        text = self.next()[1]
        self.assertIn('pending loop notification', text)
        self.assertNotIn('re-probe', text)
        with self.assertRaisesRegex(ValueError, 'no active slack outage'):
            notifications.reprobe(self.root, 'slack', 'slack_send_message', 'down', EVIDENCE)

    def test_outage_is_session_and_provider_scoped(self):
        with self.assertRaisesRegex(ValueError, 'active ESX loop'):
            self.declare()
        self.start()
        notifications.outage(self.root, 'teams', 'Tool discovery', EVIDENCE)
        self.assertEqual(len(notifications.pending(self.root)), 1)  # other provider: still pending
        self.assertIn('pending loop notification', self.next()[1])
        self.declare()
        p = self.root / loop_control.STATE
        p.write_text(re.sub(r'(?m)^run_id: \S+$', 'run_id: another-session', p.read_text()))
        notifications.synchronize(self.root)
        self.assertEqual(len(notifications.pending(self.root)), 1)  # new run's loop_start not covered

    def test_cli_outage_and_reprobe(self):
        self.start()
        base = ['--root', str(self.root)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(notifications.main(base + ['outage', '--provider', 'slack', '--tool', 'ToolSearch',
                                                        '--probe-evidence', EVIDENCE]), 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'active')
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(notifications.main(base + ['reprobe', '--provider', 'slack', '--tool', 'ToolSearch',
                                                        '--result', 'up', '--probe-evidence', EVIDENCE]), 0)
        self.assertEqual(json.loads(out.getvalue())['status'], 'cleared')


if __name__ == '__main__':
    unittest.main()
