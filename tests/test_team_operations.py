"""Offline adversarial and concurrency tests for team accounting and controls.

No provider calls. Processes are temporary fake CLIs or bounded Python children.
Historical replay is separately retained in the improvement-cycle evidence.
"""
import concurrent.futures
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'template/tools/esx'))
import team_accounting as accounting
import team_budget as budget
import team_retrospective as retro
import footer_contract
import bounded_command
import loop_gate
import loop_lifecycle

import runtime_tool_hook
ROOT = Path(__file__).resolve().parents[1]

class TeamOperationsTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / accounting.STATE
        self.state.mkdir(parents=True)

    def record(self, event, role='bob', start='2026-09-20T10:00:00+00:00', end='2026-09-20T10:10:00.123456+00:00', cost=1):
        path = self.state / 'agent_runtime/sessions' / role / 'turns' / event / 'record.json'
        accounting.atomic(path, {'event_id': event, 'agent_type': role, 'issue_id': 'TEST', 'session_id': role, 'started_at': start, 'finished_at': end, 'cost_usd': cost, 'correction_round': 0})
        return path

    def closed(self):
        accounting.append(self.state / 'loop_history.jsonl', {'id': 'TEST', 'iteration': 1, 'start_timestamp': '2026-09-20T10:00:00Z', 'timestamp': '2026-09-20T10:15:00Z', 'outcome': 'completed'})

    def test_cost_repair_unknown_and_overlap_are_not_lost(self):
        path = self.record('one')
        self.record('two', 'richard', cost=None)
        accounting.append(path.parent / 'repair-extra.jsonl', {'type': 'result', 'total_cost_usd': 0.25})
        result = accounting.summary(self.root, 'TEST', '2026-09-20T10:00:00Z', '2026-09-20T10:15:00Z')
        self.assertEqual(result['reported_usd'], 1.25)
        self.assertEqual(result['unknown_cost_event_ids'], ['two'])
        self.assertAlmostEqual(result['child_elapsed_seconds'], 600.123456, places=5)
        self.assertEqual(result['coordinator_coverage'], 'missing')

    def test_stream_deduplicates_partial_messages_and_tool_calls(self):
        path = self.state / 'stream.jsonl'
        row = {'type': 'assistant', 'message': {'id': 'm', 'usage': {'output_tokens': 4}, 'content': [{'type': 'tool_use', 'id': 't', 'name': 'Read'}]}}
        accounting.append(path, row)
        accounting.append(path, row)
        value = accounting.stream_usage(path)
        self.assertEqual(value['tool_calls'], 1)
        self.assertEqual(value['usage']['output_tokens'], 4)
        self.assertIsNone(value['cost_usd'])

    def test_duplicate_cost_component_refused(self):
        p = self.record('one')
        r = json.loads(p.read_text())
        r['accounting_components'] = [{'event_id': 'same', 'cost_usd': 1}] * 2
        accounting.atomic(p, r)
        with self.assertRaisesRegex(ValueError, 'duplicate cost'):
            accounting.summary(self.root)

    def test_nonfinite_and_negative_costs_refused(self):
        for cost in (-1, float('nan'), float('inf'), True):
            p = self.record('one')
            r = json.loads(p.read_text())
            r['cost_usd'] = cost
            p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError, 'invalid cost'):
                accounting.summary(self.root)

    def test_retrospective_draft_reconciles_and_detects_tampering(self):
        self.closed()
        self.record('one')
        draft = retro.draft(self.root)
        last = retro.pending(self.root)
        self.assertEqual(retro.validate_measurements(self.root, draft, last), [])
        draft['measured']['cost_usd']['bob'] = 0
        self.assertIn('differs', str(retro.validate_measurements(self.root, draft, last)))

    def test_dispatch_debt_checked_before_provider_lookup(self):
        import agent_runtime
        self.closed()
        with self.assertRaisesRegex(ValueError, 'RETROSPECTIVE_REQUIRED'):
            agent_runtime.run_turn(self.root, role='bob', issue='OTHER', prompt='x', executable='does-not-exist')

    def test_legacy_records_identified_but_not_backfilled(self):
        self.closed()
        accounting.append(self.state / 'retrospective_history.jsonl', {'id': 'TEST', 'closes_timestamp': '2026-09-20T10:15:00Z'})
        self.assertIsNone(retro.pending(self.root))
        self.assertTrue(retro.validate_measurements(self.root, {}, {}))

    def test_repeated_category_schedules_owning_issue(self):
        for i in range(2):
            accounting.append(self.state / 'retrospective_history.jsonl', {'id': str(i), 'problems': [{'category': 'footer_shape'}], 'solutions': [{'problem': 0, 'action': 'deferred', 'issue': 'FIX'}]})
        self.assertEqual(retro.recurring_issues(self.root, {'FIX'}), ['FIX'])
        self.assertEqual(retro.recurring_issues(self.root, set()), [])

    def test_concurrent_reservations_are_atomic_and_overrun_is_recorded_once(self):
        """Allocations are expectations: every launch proceeds, the overrun is recorded."""
        cap = budget.limits('scientific_small', {'usd': 5, 'turn_usd': 2})

        def reserve(i):
            return budget.reserve(self.root, str(i), 'TEST', cap)['reserved_usd']
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            amounts = list(pool.map(reserve, range(64)))
        self.assertEqual(len(amounts), 64)
        self.assertTrue(all(a == 2 for a in amounts), amounts)
        ledger = json.loads(budget.file_for(self.root).read_text())
        self.assertEqual(len(ledger['reservations']), 64)
        overrun = ledger['scopes']['issue:TEST']['overruns']['usd']
        self.assertEqual(overrun['expected'], 5)
        self.assertGreater(overrun['actual'], 5)
        self.assertEqual(overrun['dimension'], 'usd')

    def test_unknown_charge_is_retained_and_not_double_counted(self):
        cap = budget.limits(override={'usd': 2, 'turn_usd': 2})
        budget.reserve(self.root, 'one', 'TEST', cap)
        budget.settle(self.root, 'one', None)
        self.assertEqual(budget.reserve(self.root, 'two', 'TEST', cap)['reserved_usd'], 2)
        ledger = json.loads(budget.file_for(self.root).read_text())
        # The unknown charge keeps its full reservation, so the retry is measured
        # as additional spend rather than silently reusing the first allocation.
        self.assertEqual(ledger['reservations']['one']['status'], 'unknown_reserved')
        self.assertEqual(ledger['reservations']['one']['charged_usd'], 2)
        self.assertEqual(ledger['scopes']['issue:TEST']['overruns']['usd']['actual'], 4)

    def test_run_budget_spans_different_issues_and_repairs(self):
        cap = budget.limits(override={'usd': 3, 'turn_usd': 2})
        budget.reserve(self.root, 'one', 'A', cap, run='RUN', run_budget=cap)
        budget.settle(self.root, 'one', 2)
        r = budget.reserve(self.root, 'repair', 'A', cap, run='RUN', run_budget=cap)
        self.assertEqual(r['reserved_usd'], 2)
        budget.reserve(self.root, 'two', 'B', cap, run='RUN', run_budget=cap)
        # The shared run scope records the aggregate overrun across both issues.
        ledger = json.loads(budget.file_for(self.root).read_text())
        self.assertIn('usd', ledger['scopes']['run:RUN']['overruns'])
        self.assertEqual(ledger['scopes']['run:RUN']['overruns']['usd']['expected'], 3)

    def test_provider_overshoot_is_recorded_and_does_not_stop_launches(self):
        """A cents-scale provider variance must not strand an issue's remaining work."""
        cap = budget.limits()
        budget.reserve(self.root, 'one', 'TEST', cap, amount=1)
        settlement = budget.settle(self.root, 'one', 1.01)
        self.assertTrue(settlement['provider_overshoot'])
        self.assertTrue(budget.reserve(self.root, 'two', 'TEST', cap)['reserved_usd'])
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertNotIn('breached', scope)
        recorded = scope['overruns']['provider_overshoot']
        self.assertEqual((recorded['expected'], recorded['actual']), (1, 1.01))

    def test_tool_calls_are_counted_idempotently_and_overrun_is_recorded(self):
        cap = budget.limits(override={'calls': 5})
        budget.reserve(self.root, 'one', 'TEST', cap)
        budget.allow_tool(self.root, 'one', 'a')
        budget.allow_tool(self.root, 'one', 'a')
        for ident in ('b', 'c', 'd', 'e', 'f'):
            budget.allow_tool(self.root, 'one', ident)
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertEqual(len(scope['calls']), 6)
        self.assertEqual(scope['overruns']['calls']['expected'], 5)

    def test_deadlines_and_corrections_do_not_reset(self):
        cap = budget.limits('scientific_small')
        first = budget.reserve(self.root, 'one', 'TEST', cap)
        budget.settle(self.root, 'one', 0)
        second = budget.reserve(self.root, 'two', 'TEST', cap, correction=1)
        self.assertEqual(first['deadline'], second['deadline'])
        budget.reserve(self.root, 'three', 'TEST', cap, correction=2)
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertEqual(scope['overruns']['corrections']['expected'], 1)
        self.assertEqual(scope['overruns']['corrections']['actual'], 2)
        stored = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST'].get('deadline')
        with patch.object(budget.time, 'time', return_value=first['deadline'] + 1) as clock:
            late = budget.reserve(self.root, 'late', 'TEST', cap)
            # The scope's own recorded deadline never resets, but a later turn must
            # still receive a usable future horizon rather than the elapsed one.
            self.assertGreater(late['deadline'], clock.return_value)
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertEqual(scope.get('deadline'), stored)
        self.assertIn('minutes', scope['overruns'])

    def test_tool_hook_preserves_permission_checks_and_quotes_command(self):
        cap = budget.limits()
        budget.reserve(self.root, 'one', 'TEST', cap)
        value = runtime_tool_hook.handle({'tool_use_id': 't', 'tool_name': 'Bash', 'tool_input': {'command': "printf '%s' '$SECRET'"}}, {'root': str(self.root), 'event_id': 'one', 'folder': str(self.state), 'tool_timeout': 2})
        out = value['hookSpecificOutput']
        self.assertNotIn('permissionDecision', out)
        self.assertIn('bounded_command.py', out['updatedInput']['command'])
        self.assertFalse(out['updatedInput']['run_in_background'])

    def test_hung_command_cannot_kill_healthy_parallel_command(self):

        def command(name, delay, limit):
            return bounded_command.run([sys.executable, '-c', f'import time; time.sleep({delay}); print({name!r})'], limit, self.state, name)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            hung = pool.submit(command, 'hung', 30, 0.15)
            healthy = pool.submit(command, 'healthy', 0.5, 3)
            self.assertEqual(hung.result(), 124)
            self.assertEqual(healthy.result(), 0)

    def test_snapshot_reuse_matches_fresh_and_new_command_sees_new_data(self):
        self.record('one')
        snapshot = accounting.snapshot(self.root)
        self.assertEqual(accounting.summary(self.root), accounting.summary(self.root, evidence=snapshot))
        self.record('two', cost=2)
        self.assertEqual(accounting.summary(self.root, evidence=snapshot)['reported_usd'], 1)
        self.assertEqual(accounting.summary(self.root)['reported_usd'], 3)

    def driver_fixture(self, body):
        import team_driver
        folder = self.root / '.claude'
        folder.mkdir(exist_ok=True)
        (folder / 'esx-loop.local.md').write_text('---\niteration: 1\n---\nFinish bounded work.')
        binary = self.root / 'claude'
        binary.write_text('#!' + sys.executable + '\n' + body)
        binary.chmod(493)
        return team_driver

    def test_driver_records_arch_cost_and_removes_finished_state(self):
        driver = self.driver_fixture("import json; from pathlib import Path; Path('.claude/esx-loop.local.md').unlink(); print(json.dumps({'type':'result','subtype':'success','is_error':False,'total_cost_usd':.25,'usage':{'output_tokens':9}}))")
        with patch.dict(os.environ, {'PATH': str(self.root) + os.pathsep + os.environ['PATH']}):
            self.assertEqual(driver.run(self.root, max_passes=1), 0)
        report = accounting.summary(self.root)
        self.assertEqual(report['reported_usd'], 0.25)
        self.assertEqual(report['coordinator_coverage'], 'recorded')
        self.assertEqual(report['by_role']['arch']['usage']['output_tokens'], 9)
        self.assertEqual(report['phase_events'][0]['phase'], 'coordination')

    def test_driver_rejects_success_exit_with_error_and_keeps_resume_budget(self):
        driver = self.driver_fixture("import json; print(json.dumps({'type':'result','subtype':'error_max_budget_usd','is_error':True,'total_cost_usd':.5}))")
        with patch.dict(os.environ, {'PATH': str(self.root) + os.pathsep + os.environ['PATH']}):
            self.assertEqual(driver.run(self.root, max_passes=2), 3)
            original = json.loads(budget.file_for(self.root).read_text())
            self.assertEqual(driver.run(self.root, max_passes=1), 3)
        updated = json.loads(budget.file_for(self.root).read_text())
        self.assertEqual(len(updated['reservations']), 2)
        self.assertEqual({k: v['started'] for (k, v) in original['scopes'].items()}, {k: v['started'] for (k, v) in updated['scopes'].items()})
        self.assertTrue(all((t['status'] == 'failed' for t in accounting.turns(self.root))))

    def test_driver_failed_launch_saves_zero_cost_receipt(self):
        driver = self.driver_fixture('')
        with patch.object(driver.subprocess, 'Popen', side_effect=FileNotFoundError('missing')):
            self.assertEqual(driver.run(self.root, max_passes=1), 3)
        turn = accounting.turns(self.root)[0]
        self.assertEqual(turn['status'], 'failed')
        self.assertEqual(accounting.summary(self.root)['reported_usd'], 0)
        self.assertEqual(accounting.summary(self.root)['unknown_cost_event_ids'], [])

    def test_tool_duplicate_past_expectation_is_still_idempotent(self):
        cap = budget.limits(override={'calls': 5})
        budget.reserve(self.root, 'one', 'TEST', cap)
        for identity in ('a', 'b', 'c', 'd', 'd', 'e', 'f', 'f'):
            budget.allow_tool(self.root, 'one', identity)
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertEqual(len(scope['calls']), len(set(scope['calls'])))
        self.assertEqual(len(scope['calls']), 6)

    def test_turn_time_and_calls_are_bounded_inside_larger_issue(self):
        cap = budget.limits(override={'minutes': 60, 'calls': 500})
        reservation = budget.reserve(self.root, 'one', 'TEST', cap, turn_seconds=100, turn_calls=5)
        self.assertLess(reservation['deadline'], time.time() + 101)
        for tool in ('a', 'b', 'c', 'd', 'e', 'f'):
            budget.allow_tool(self.root, 'one', tool)
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertEqual(scope['overruns']['turn_calls']['expected'], 5)
        budget.reserve(self.root, 'two', 'TEST', cap, turn_seconds=100, turn_calls=50)
        with patch.object(budget.time, 'time', return_value=reservation['deadline'] - 10):
            budget.allow_tool(self.root, 'two', 'a')
        scope = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']
        self.assertIn('soft_deadline', scope['overruns'])

    def test_copilot_adapter_uses_modified_args_without_granting_permission(self):
        budget.reserve(self.root, 'one', 'TEST', budget.limits())
        event = {'toolName': 'bash', 'toolArgs': json.dumps({'command': 'echo ok', 'mode': 'async'}), 'timestamp': 1234}
        context = {'root': str(self.root), 'event_id': 'one', 'folder': str(self.state), 'tool_timeout': 1}
        result = runtime_tool_hook.handle(event, context)
        self.assertEqual(result['modifiedArgs']['mode'], 'sync')
        self.assertIn('bounded_command.py', result['modifiedArgs']['command'])
        self.assertNotIn('permissionDecision', result)
        runtime_tool_hook.handle(event, context)
        ledger = json.loads(budget.file_for(self.root).read_text())
        self.assertEqual(len(ledger['reservations']['one']['calls']), 1)

    def test_effectiveness_requires_real_improvement_and_bound_evidence(self):
        import hashlib
        path = self.root / 'measurement.json'
        value = {'metric': 'latency', 'unit': 'seconds', 'method': 'repeat workload', 'before': 2, 'after': 1, 'direction': 'lower'}
        accounting.atomic(path, value)
        ref = {'path': 'measurement.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.assertEqual(retro.effectiveness_errors(self.root, ref), [])
        value['after'] = 3
        accounting.atomic(path, value)
        self.assertTrue(retro.effectiveness_errors(self.root, ref))
        ref['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn('direction', str(retro.effectiveness_errors(self.root, ref)))

    def test_repeated_unowned_problem_cannot_disappear_into_landed_prose(self):
        prior = {'problems': [{'category': 'footer_shape'}]}
        accounting.append(self.state / 'retrospective_history.jsonl', prior)
        current = dict(prior, solutions=[{'problem': 0, 'action': 'implemented', 'reference': 'tools/fix.py', 'effectiveness': 'landed'}])
        self.assertTrue(retro.recurrence_errors(self.root, current, {'FIX'}))
        current['solutions'].append({'problem': 0, 'action': 'filed', 'reference': 'FIX'})
        self.assertEqual(retro.recurrence_errors(self.root, current, {'FIX'}), [])

    def test_no_dimension_ever_refuses_work(self):
        """The contract of a monitoring-only allocation: exceed everything, refuse nothing."""
        cap = budget.limits(override={'minutes': 1, 'usd': 1, 'calls': 1, 'corrections': 0, 'turn_usd': 1})
        first = budget.reserve(self.root, 'one', 'TEST', cap)
        budget.settle(self.root, 'one', 99.0)
        with patch.object(budget.time, 'time', return_value=first['deadline'] + 10_000):
            later = budget.reserve(self.root, 'two', 'TEST', cap, correction=7)
            budget.allow_tool(self.root, 'two', 'a')
            budget.allow_tool(self.root, 'two', 'b')
        self.assertEqual(later['reserved_usd'], 1)
        overruns = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']['overruns']
        # soft_deadline is a per-turn liveness signal, so it is not expected here:
        # a turn launched after the nominal wall time still gets a future horizon.
        self.assertEqual(set(overruns), {'minutes', 'corrections', 'usd',
                                         'provider_overshoot', 'calls'})
        for dimension, entry in overruns.items():
            self.assertGreater(entry['observations'], 0, dimension)
            self.assertIn('first_observed_at', entry)
            self.assertIn('detail', entry)

    def test_expired_scope_still_gives_a_turn_a_usable_future_deadline(self):
        """Regression: an elapsed nominal allocation must not hand back a past deadline.

        Under monitoring-only semantics reserve() no longer refuses an expired
        scope. If it returned the scope's own past deadline, run_turn would kill
        every later turn at launch -- observed as a 0.18-second 'timeout' with
        returncode -15 and an empty report.
        """
        cap = budget.limits(override={'minutes': 1})
        first = budget.reserve(self.root, 'one', 'TEST', cap)
        budget.settle(self.root, 'one', 0)
        with patch.object(budget.time, 'time', return_value=first['deadline'] + 10_000) as clock:
            later = budget.reserve(self.root, 'two', 'TEST', cap, turn_seconds=300)
            self.assertGreater(later['deadline'], clock.return_value)
            self.assertGreater(later['soft_deadline'], clock.return_value)
            self.assertAlmostEqual(later['deadline'], clock.return_value + 300, places=3)
            # No turn_seconds: the horizon falls back to the nominal duration.
            fallback = budget.reserve(self.root, 'three', 'TEST', cap)
            self.assertGreater(fallback['deadline'], clock.return_value)
        # The elapsed wall time is still recorded as an overrun.
        self.assertIn('minutes', json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']['overruns'])

    def test_a_live_scope_deadline_still_bounds_a_longer_turn(self):
        """A still-valid nominal deadline keeps constraining the turn."""
        cap = budget.limits(override={'minutes': 10})
        reservation = budget.reserve(self.root, 'one', 'TEST', cap, turn_seconds=99_999)
        self.assertLess(reservation['deadline'], time.time() + 10 * 60 + 1)

    def test_repeated_crossing_updates_one_observation_rather_than_growing(self):
        """Monitoring must not itself become an unbounded cost."""
        cap = budget.limits(override={'calls': 1})
        budget.reserve(self.root, 'one', 'TEST', cap)
        for identity in 'abcdefgh':
            budget.allow_tool(self.root, 'one', identity)
        entry = json.loads(budget.file_for(self.root).read_text())['scopes']['issue:TEST']['overruns']['calls']
        self.assertEqual(entry['observations'], 7)
        self.assertEqual(entry['expected'], 1)
        self.assertEqual(entry['actual'], 8)

    def test_phase_is_recorded_even_when_work_fails(self):
        with self.assertRaises(RuntimeError):
            with accounting.phase(self.root, 'TEST', 'review'):
                raise RuntimeError('failure')
        self.assertEqual(len(accounting.rows(self.state / 'phase_events.jsonl')), 1)
if __name__ == '__main__':
    unittest.main()
