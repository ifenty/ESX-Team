"""Coordinator (Arch) cost is recorded separately and never redefines agent figures.

Offline: temporary loop_state fixtures only, no provider calls.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'template/tools/esx'))
import team_accounting as accounting
import team_retrospective as retro

START, END = '2026-09-20T10:00:00+00:00', '2026-09-20T10:15:00+00:00'


class CoordinatorCostTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / accounting.STATE
        self.state.mkdir(parents=True)

    def record(self, event, role='bob', cost=1.0):
        path = self.state / 'agent_runtime/sessions' / role / 'turns' / event / 'record.json'
        accounting.atomic(path, {'event_id': event, 'agent_type': role, 'issue_id': 'TEST', 'session_id': role,
                                 'started_at': '2026-09-20T10:01:00+00:00', 'finished_at': '2026-09-20T10:11:00+00:00',
                                 'cost_usd': cost, 'correction_round': 0})

    def arch_phase(self, name='closeout', started='2026-09-20T10:12:00+00:00', finished='2026-09-20T10:14:00+00:00'):
        accounting.append(self.state / 'phase_events.jsonl', {'event_id': name + started, 'issue_id': 'TEST', 'phase': name,
                          'role': 'arch', 'started_at': started, 'finished_at': finished, 'reason': None})

    def close(self):
        accounting.atomic(self.state / 'issue-start.json', {'id': 'TEST', 'timestamp': START})
        accounting.append(self.state / 'loop_history.jsonl', {'id': 'TEST', 'iteration': 1, 'timestamp': START,
                          'start_timestamp': START, 'closed_at': END, 'outcome': 'completed'})

    def summary(self):
        return accounting.summary(self.root, 'TEST', START, END)

    def test_iteration_with_arch_record_reports_recorded_with_coordinator_fields(self):
        self.record('b1')
        self.arch_phase()
        self.close()
        accounting.record_arch(self.root, 'TEST', 'coordination', 35, 'Claude Code /cost delta', usd=4.1)
        report = self.summary()
        self.assertEqual(report['coordinator_coverage'], 'recorded')
        c = report['coordinator']
        self.assertEqual(c['self_reported']['minutes'], 35)
        self.assertEqual(c['self_reported']['usd'], 4.1)
        self.assertEqual(c['self_reported']['records'][0]['source'], 'Claude Code /cost delta')
        self.assertAlmostEqual(c['tool_measured']['effort_seconds'], 120)
        self.assertIsNone(c['provider_reported_usd'])
        measured = accounting.measured(report)
        self.assertEqual(measured['coordinator']['self_reported_usd'], 4.1)
        self.assertEqual(measured['coordinator']['tool_measured_minutes'], 2.0)
        self.assertIn('self-reported 35 min, $4.10', measured['cost_scope'])
        self.assertIn('not added to cost_usd', measured['cost_scope'])

    def test_iteration_without_arch_record_still_reports_missing(self):
        self.record('b1')
        self.arch_phase()  # gate wall time alone is partial, never "recorded"
        self.close()
        report = self.summary()
        self.assertEqual(report['coordinator_coverage'], 'missing')
        self.assertIsNone(report['coordinator']['self_reported']['minutes'])
        self.assertIn('NOT included', accounting.measured(report)['cost_scope'])

    def test_record_for_other_iteration_or_issue_is_not_counted(self):
        self.close()
        accounting.append(self.state / accounting.SELF_REPORTS, {'record_id': 'x', 'issue_id': 'TEST', 'role': 'arch',
                          'phase': 'coordination', 'minutes': 5, 'usd': 1, 'source': 'earlier iteration',
                          'recorded_at': '2026-09-19T10:00:00+00:00', 'iteration_start': '2026-09-19T09:00:00+00:00'})
        accounting.record_arch(self.root, 'OTHER', 'coordination', 5, 'another issue entirely')
        self.assertEqual(self.summary()['coordinator_coverage'], 'missing')

    def test_existing_dispatched_agent_figures_are_unchanged(self):
        self.record('b1', cost=2.3)
        self.record('r1', 'richard', cost=2.02)
        self.arch_phase()
        self.close()
        before = self.summary()
        accounting.record_arch(self.root, 'TEST', 'coordination', 50, 'Claude Code session cost', usd=9.0)
        after = self.summary()
        for key in ('reported_usd', 'span_seconds', 'child_elapsed_seconds', 'by_role', 'unknown_cost_event_ids', 'by_phase'):
            self.assertEqual(before[key], after[key], key)
        b, a = accounting.measured(before), accounting.measured(after)
        for key in ('span_minutes', 'dispatches', 'rounds', 'cost_usd'):
            self.assertEqual(b[key], a[key], key)
        self.assertEqual(a['cost_usd'], {'bob': 2.3, 'richard': 2.02})
        self.assertNotIn('arch', a['cost_usd'])

    def test_record_arch_requires_provenance_and_valid_numbers(self):
        for args in ((0, 'Claude Code /cost'), (5, 'short'), (float('nan'), 'Claude Code /cost')):
            with self.assertRaises(ValueError):
                accounting.record_arch(self.root, 'TEST', 'coordination', *args)
        with self.assertRaises(ValueError):
            accounting.record_arch(self.root, 'TEST', 'coordination', 5, 'Claude Code /cost', usd=-1)
        with self.assertRaises(ValueError):
            accounting.record_arch(self.root, 'TEST', 'lunch', 5, 'Claude Code /cost')
        self.assertFalse((self.state / accounting.SELF_REPORTS).exists())

    def test_record_while_active_uses_window_and_after_close_attaches(self):
        accounting.atomic(self.state / 'issue-start.json', {'id': 'TEST', 'timestamp': START})
        active = accounting.record_arch(self.root, 'TEST', 'orientation', 3, 'Claude Code /cost')
        self.assertIsNone(active['iteration_start'])
        self.close()
        closed = accounting.record_arch(self.root, 'TEST', 'closeout', 4, 'Claude Code /cost')
        self.assertEqual(closed['iteration_start'], START)
        # recorded now (after END) but attached, so it counts; the active one is outside the fixture window
        self.assertEqual(self.summary()['coordinator']['self_reported']['minutes'], 4)

    def test_cli_records_and_draft_states_scope(self):
        self.record('b1')
        self.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = accounting.main(['record-arch', '--root', str(self.root), '--issue', 'TEST', '--phase', 'coordination',
                                    '--minutes', '12.5', '--source', 'Claude Code /cost at closeout'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['minutes'], 12.5)
        with contextlib.redirect_stdout(io.StringIO()) as blocked:
            self.assertEqual(accounting.main(['record-arch', '--root', str(self.root), '--issue', 'TEST',
                                              '--phase', 'coordination', '--minutes', '1', '--source', 'x']), 1)
        self.assertIn('blocked', blocked.getvalue())
        draft = retro.draft(self.root)
        self.assertEqual(draft['measured']['coordinator_coverage'], 'recorded')
        self.assertIn('cost unknown', draft['measured']['cost_scope'])
        self.assertEqual(retro.validate_measurements(self.root, draft, accounting.rows(self.state / 'loop_history.jsonl')[-1]), [])
        concise = accounting.concise(accounting.summary(self.root, 'TEST', START, END))
        self.assertIn('Arch recorded', concise)
        self.assertIn('coordinator cost is recorded separately', concise)

    def test_phase_role_is_recorded_only_when_given(self):
        with accounting.phase(self.root, 'TEST', 'closeout', role='arch'):
            pass
        with accounting.phase(self.root, 'TEST', 'review'):
            pass
        events = accounting.rows(self.state / 'phase_events.jsonl')
        self.assertEqual(events[0]['role'], 'arch')
        self.assertNotIn('role', events[1])


if __name__ == '__main__':
    unittest.main()
