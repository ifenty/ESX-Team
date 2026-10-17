"""1.7.2: pilot-only fixes reconciled into the kit so a project carrying them can upgrade by three-way merge.

Covers the esx_manager.three_way exit-status fix and each PORT from self-improvement/reconcile_1.7.2.md:
truncated stale-figure listings, the uncaptured-completion notice, framework_test_paths, the verification
outcome classification, and the aligned ralph_stop verification block. Offline, synthetic fixtures.
"""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
from test_framework import KIT
import brief
import doc_contract
import esx_manager
import final_verification
import loop_gate
import project
import verify

TOOLS = KIT / 'template/tools/esx'
PY = ['{python}', '-c']


class ThreeWayTests(unittest.TestCase):
    """git merge-file exits with the NUMBER of conflicts (1..127); only >=128 is an error."""

    BASE = ''.join(f'line {i}\n' for i in range(1, 31)).encode()

    def edit(self, text, changes):
        lines = text.decode().splitlines(keepends=True)
        for number, value in changes.items():
            lines[number - 1] = value + '\n'
        return ''.join(lines).encode()

    def test_three_separate_conflicts_are_a_conflict_not_an_error(self):
        current = self.edit(self.BASE, {3: 'project 3', 15: 'project 15', 27: 'project 27'})
        incoming = self.edit(self.BASE, {3: 'kit 3', 15: 'kit 15', 27: 'kit 27'})
        merged, clean = esx_manager.three_way(current, self.BASE, incoming)
        self.assertFalse(clean)
        self.assertEqual(merged.count(b'<<<<<<< project'), 3)
        self.assertEqual(merged.count(b'>>>>>>> new ESX master'), 3)

    def test_two_conflicts_and_one_conflict(self):
        for count in (1, 2):
            changes = {3 + 10 * i: 'x' for i in range(count)}
            current = self.edit(self.BASE, {n: 'project' for n in changes})
            incoming = self.edit(self.BASE, {n: 'kit' for n in changes})
            merged, clean = esx_manager.three_way(current, self.BASE, incoming)
            self.assertFalse(clean, count)
            self.assertEqual(merged.count(b'<<<<<<<'), count)

    def test_disjoint_edits_still_merge_cleanly(self):
        current = self.edit(self.BASE, {2: 'project 2'})
        incoming = self.edit(self.BASE, {25: 'kit 25'})
        merged, clean = esx_manager.three_way(current, self.BASE, incoming)
        self.assertTrue(clean)
        self.assertIn(b'project 2', merged)
        self.assertIn(b'kit 25', merged)

    def test_exit_status_of_128_or_more_is_an_error_with_stderr(self):
        failed = subprocess.CompletedProcess([], 255, stdout=b'', stderr=b'fatal: out of memory')
        with patch.object(esx_manager.subprocess, 'run', return_value=failed):
            with self.assertRaisesRegex(ValueError, 'git merge-file failed.*out of memory'):
                esx_manager.three_way(b'a\n', b'b\n', b'c\n')


class StaleListingTests(unittest.TestCase):
    """TEAM-DOCCONTRACT-STALE-HITS-TRUNCATION-001: a truncated listing must not read as a total."""

    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        (self.root / 'docs').mkdir(exist_ok=True)
        (self.root / 'docs/model_contract.md').write_text(''.join(f'The grid has 4242 cells ({i}).\n' for i in range(12)))
        self.rows = [{'old': '4242 cells', 'new': '4300 cells', 'note': ''}]

    def test_complete_listing_keeps_the_hits_key(self):
        found = doc_contract.stale_lines(self.root, self.rows)
        self.assertEqual(found['truncated'], 0)
        self.assertIn('hits', found)
        self.assertNotIn('hits_sample', found)
        self.assertEqual(found['lines'], 12)
        self.assertEqual(doc_contract.listed(found), found['hits'])

    def test_truncated_listing_cannot_be_indexed_as_hits(self):
        found = doc_contract.stale_lines(self.root, self.rows, limit=5)
        self.assertEqual((found['lines'], found['truncated'], found['limit']), (12, 7, 5))
        self.assertNotIn('hits', found)
        self.assertEqual(len(found['hits_sample']), 5)
        self.assertEqual(doc_contract.listed(found), found['hits_sample'])
        self.assertIn('warnings', found)

    def test_cli_states_the_total_beside_a_truncated_listing(self):
        table = self.root / 'figures.tsv'
        table.write_text('4242 cells\t4300 cells\tnote\n')
        proc = subprocess.run([sys.executable, str(TOOLS / 'doc_contract.py'), '--root', str(self.root),
                               'stale', '--figures', str(table), '--limit', '5'],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('12 inventoried line(s) match', proc.stderr)
        self.assertIn('do not count the sample', proc.stderr)
        self.assertIn('hits_sample', proc.stdout)

    def test_brief_reads_the_listing_through_listed(self):
        source = (TOOLS / 'brief.py').read_text()
        self.assertNotIn("found['hits']", source)
        self.assertIn('doc_contract.listed(found)', source)


def gate_with_log(rows):
    folder = tempfile.TemporaryDirectory()
    root = Path(folder.name)
    state = root / 'devel-loop/loop_state'
    state.mkdir(parents=True)
    (state / 'dispatch_log.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    gate = loop_gate.Gate.__new__(loop_gate.Gate)
    gate.root = root
    return gate, folder


START = {'id': 'X-1', 'timestamp': '2026-01-01T00:00:00+00:00'}


def record(status, agent='bob', agent_id='a1', rnd=1, error=None):
    row = {'agent_type': agent, 'agent_id': agent_id, 'status': status, 'issue_id': 'X-1', 'correction_round': rnd,
           'footer': {'issue_id': 'X-1', 'iteration_timestamp': START['timestamp'], 'correction_round': rnd}}
    if error:
        row['error'] = error
    return row


class UncapturedCompletionTests(unittest.TestCase):
    """TEAM-BRIEF-UNVALIDATED-INTERFACE-001 (notice), TEAM-GATE-DEFECT-NOTICE-NOT-SUPERSEDED-001 and
    TEAM-GATE-CONSULTATION-NOTICE-PERMANENT-001."""

    def defects(self, rows):
        gate, folder = gate_with_log(rows)
        self.addCleanup(folder.cleanup)
        return gate.defective_completions(START)

    def test_unrepaired_record_is_reported(self):
        self.assertEqual(self.defects([record('incomplete', error='stale orientation')]),
                         [('bob', 'a1', 1, 'stale orientation')])

    def test_reemission_clears_it_per_round(self):
        self.assertEqual(self.defects([record('incomplete', error='bad'), record('completed')]), [])
        self.assertEqual(self.defects([record('incomplete', rnd=1, error='bad'), record('completed', rnd=1),
                                       record('incomplete', rnd=2, error='two')]),
                         [('bob', 'a1', 2, 'two')])

    def test_footerless_consultation_that_later_reported_is_not_a_defect(self):
        lost = {'agent_type': 'richard', 'agent_id': 'r1', 'status': 'incomplete', 'issue_id': None,
                'iteration_timestamp': None, 'correction_round': 0, 'error': 'missing footer'}
        closed = {'agent_type': 'richard', 'agent_id': 'r1', 'status': 'completed', 'issue_id': 'OLD-1',
                  'correction_round': 2, 'footer': {'issue_id': 'OLD-1', 'correction_round': 2}}
        self.assertEqual(self.defects([lost, closed]), [])
        self.assertEqual(self.defects([closed, lost]), [('richard', 'r1', 0, 'missing footer')])

    def test_next_prints_the_notice_and_keeps_the_verification_notice(self):
        source = (TOOLS / 'loop_gate.py').read_text()
        self.assertIn('UNCAPTURED COMPLETION', source)
        self.assertLess(source.index('self.defective_completions(start)'), source.index('final_verification.pending_notice'))
        self.assertEqual(loop_gate.record_error('x ' * 200).endswith('...'), True)
        self.assertEqual(len(loop_gate.record_error('x ' * 200)), 160)


class FrameworkTestPathsTests(unittest.TestCase):
    """esx-fix.md F1: framework tests stay in the acceptance inventory but leave the scientific one."""

    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        (self.root / 'tests/esx').mkdir(parents=True, exist_ok=True)
        (self.root / 'tests/esx/test_tools.py').write_text('')

    def configure(self, **changes):
        cfg = project.config(self.root)
        cfg.update(changes)
        project.atomic_json(self.root / 'esx/project.json', cfg)
        return cfg

    def test_framework_test_leaves_the_scientific_inventory_only(self):
        cfg = self.configure(framework_test_paths=['tests/esx'])
        project.config(self.root)
        self.assertFalse(project.selected('tests/esx/test_tools.py', cfg, scientific=True))
        self.assertTrue(project.selected('tests/esx/test_tools.py', cfg, scientific=False))
        self.assertTrue(project.selected('tests/check_diffusion.py', cfg, scientific=True))

    def test_absent_key_keeps_every_test_scientific(self):
        cfg = project.config(self.root)
        self.assertNotIn('framework_test_paths', cfg)
        self.assertTrue(project.selected('tests/esx/test_tools.py', cfg, scientific=True))

    def test_entry_outside_test_paths_is_refused(self):
        self.configure(framework_test_paths=['docs'])
        with self.assertRaisesRegex(ValueError, 'inside a configured test_paths root'):
            project.config(self.root)

    def test_non_list_is_refused(self):
        self.configure(framework_test_paths='tests/esx')
        with self.assertRaisesRegex(ValueError, 'must be a list'):
            project.config(self.root)

    def test_a_scientific_witness_cannot_be_declared_a_framework_test(self):
        cfg = project.config(self.root)
        cfg['verification']['scientific'].append(['{python}', 'tests/esx/test_tools.py'])
        self.configure(framework_test_paths=['tests/esx/test_tools.py'], verification=cfg['verification'])
        with self.assertRaisesRegex(ValueError, 'executed by the scientific suite'):
            project.config(self.root)


class VerificationOutcomeTests(unittest.TestCase):
    """TEAM-VERIFY-SIGNAL-MISCLASSIFIED-001 corrected per esx-fix.md B: the outcome comes from the runner."""

    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def attempt(self, code=None, argv=None, timeout=None):
        argv = argv or PY + [code]
        real = verify.config
        patched = (lambda root: dict(real(root), command_timeout_seconds=timeout)) if timeout else real
        try:
            with patch.object(verify, 'config', patched):
                result = verify.run(self.root, 'focused', 'tester', fresh=True, override=argv)
            exc = None
        except BaseException as caught:  # noqa: BLE001 -- the type is the datum
            result, exc = None, caught
        records = [json.loads(p.read_text()) for p in (self.root / project.STATE / 'verification').glob('*.json')
                   if len(p.stem) == 64]
        log = getattr(exc, 'log', None) or (result and json.loads(
            (self.root / result['evidence']['path']).read_text())['log'])
        found = next(r for r in records if r.get('log') == log)
        return result, exc, found

    def test_pass_record_is_complete(self):
        result, exc, found = self.attempt('pass')
        self.assertIsNone(exc)
        self.assertEqual((found['outcome'], found['completed_commands'], found['planned_commands']), ('pass', 1, 1))
        verify.load_evidence(self.root, result['evidence'])

    def test_a_failure_that_prints_the_signal_marker_stays_a_failure(self):
        marker = 'verification received signal 15'
        _, exc, found = self.attempt(f'print({marker!r}); raise SystemExit(1)')
        self.assertIs(type(exc), ValueError)
        self.assertIn('verification failed', str(exc))
        self.assertEqual((found['outcome'], found['termination']), ('failed', None))

    def test_exit_124_is_a_failure_not_our_timeout(self):
        _, exc, found = self.attempt('raise SystemExit(124)')
        self.assertIs(type(exc), ValueError)
        self.assertEqual(found['outcome'], 'failed')

    def test_a_real_timeout_has_its_own_class_and_status(self):
        _, exc, found = self.attempt('import time; time.sleep(30)', timeout=1)
        self.assertIsInstance(exc, verify.RunTimedOut)
        self.assertEqual(found['outcome'], 'timeout')
        self.assertIn('command 1', found['reason'])
        self.assertEqual(final_verification.attempt_status(exc), 'TIMED_OUT')

    def test_a_launch_failure_is_infrastructure(self):
        _, exc, found = self.attempt(argv=['/nonexistent/esx-no-such-executable'])
        self.assertIsInstance(exc, verify.RunInfrastructure)
        self.assertEqual(found['outcome'], 'infrastructure')
        self.assertEqual(final_verification.attempt_status(exc), 'INFRASTRUCTURE')

    def test_a_crash_is_a_failure_a_termination_is_an_interruption(self):
        _, exc, found = self.attempt('import os, signal; os.kill(os.getpid(), signal.SIGSEGV)')
        self.assertIs(type(exc), ValueError)
        self.assertEqual(found['outcome'], 'failed')
        self.assertIn('crashed', found['reason'])
        _, exc, found = self.attempt('import os, signal; os.kill(os.getpid(), signal.SIGKILL)')
        self.assertIsInstance(exc, verify.RunInterrupted)
        self.assertEqual((found['outcome'], found['termination'], found['completed_commands']), ('interrupted', 9, 0))

    def test_an_unattributable_signal_is_infrastructure(self):
        _, exc, found = self.attempt('import os, signal; os.kill(os.getpid(), signal.SIGUSR1)')
        self.assertIsInstance(exc, verify.RunInfrastructure)
        self.assertEqual(found['termination'], signal.SIGUSR1)

    def test_a_signal_to_the_runner_is_still_an_interrupted_error_with_the_signal_recorded(self):
        timer = subprocess.Popen([sys.executable, '-c', f'import time,os,signal; time.sleep(1.5); '
                                  f'os.kill({os.getpid()}, signal.SIGTERM)'])
        self.addCleanup(timer.wait)
        _, exc, found = self.attempt('import time; time.sleep(30)')
        self.assertIsInstance(exc, InterruptedError)
        self.assertIsInstance(exc, verify.RunInterrupted)
        self.assertEqual((found['outcome'], found['termination'], found['completed_commands']), ('interrupted', 15, 0))

    def test_evidence_consumers_require_a_complete_pass(self):
        result, _, found = self.attempt('pass')
        forged = dict(found, outcome='interrupted')
        sha = project.digest(forged)
        path = f'{project.STATE}/verification/{sha}.json'
        project.atomic_json(self.root / path, forged)
        with self.assertRaisesRegex(ValueError, 'outcome is interrupted'):
            verify.load_evidence(self.root, {'path': path, 'sha256': sha})
        short = dict(found, completed_commands=0)
        sha = project.digest(short)
        path = f'{project.STATE}/verification/{sha}.json'
        project.atomic_json(self.root / path, short)
        with self.assertRaisesRegex(ValueError, 'did not complete every configured command'):
            verify.load_evidence(self.root, {'path': path, 'sha256': sha})

    def test_zero_failure_lines_is_not_reported_as_no_failure(self):
        source = (TOOLS / 'final_verification.py').read_text()
        self.assertNotIn("'no test failed before the interruption' if", source)
        self.assertIn('does not establish that', source)


class RalphStopAlignmentTests(unittest.TestCase):
    """The verification hold's helpers are defined once and sit where a project that carries them expects."""

    def test_each_helper_is_defined_once_before_native_running(self):
        tree = ast.parse((TOOLS / 'ralph_stop.py').read_text())
        names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        for helper in ('verification_running', 'parent_pid', 'session_process', 'descends_from', 'untracked_runs'):
            self.assertEqual(names.count(helper), 1, helper)
            self.assertLess(names.index(helper), names.index('native_running'), helper)
        self.assertEqual(names[names.index('verification_running'):names.index('native_running')],
                         ['verification_running', 'parent_pid', 'session_process', 'descends_from', 'untracked_runs'])


if __name__ == '__main__':
    unittest.main()
