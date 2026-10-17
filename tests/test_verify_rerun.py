"""Interrupted, failed and re-run final scientific verification attempts.

A signal-killed suite must read as INTERRUPTED rather than a candidate failure,
the gate must name the latest attempt instead of a missing file, and a prepared
closeout is re-bound to a later passing receipt by command, never by hand edit.
"""
import json
import os
import signal
import threading
import time
import unittest

import test_framework
import final_verification
import loop_lifecycle
import project
import verify

# Emulates a pytest session: progress lines, then either a hang (to be killed),
# a genuine failure with its summary line, or a pass with its summary line.
SUITE = '''
import os, sys, time
from pathlib import Path
print("============================= test session starts ==============================", flush=True)
print("collected 3 items", flush=True)
print("tests/test_model.py::test_one PASSED [ 33%]", flush=True)
if Path("results/hang").exists():
    Path("results/child.pid").write_text(str(os.getpid()))
    time.sleep(60)
if Path("results/drift").exists():
    p = Path("src/diffusion.py"); p.write_text(p.read_text() + "\\n# drift\\n")
if Path("results/fail").exists():
    print("tests/test_model.py::test_two FAILED [ 66%]")
    print("=========================== 1 failed, 2 passed in 0.12s ===========================")
    sys.exit(1)
print("============================== 3 passed in 0.12s ===============================")
'''


class VerifyRerunTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        cfg = project.config(self.root)
        cfg['verification']['scientific'].append(['{python}', '-c', SUITE])
        project.atomic_json(self.root / 'esx/project.json', cfg)
        (self.root / 'results').mkdir(exist_ok=True)

    def passed(self):
        done = self.fixture.complete(qualify=False)
        result = final_verification.run(self.root, done, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        self.fixture.save_done(done)
        return done

    def latest(self):
        ref, record = final_verification.latest_attempt(self.root)
        self.assertIsNotNone(record)
        return record

    def killed_rerun(self, done):
        """Terminate the suite's child process from outside while it runs."""
        (self.root / 'results/hang').touch()
        pid_file = self.root / 'results/child.pid'

        def kill():
            deadline = time.monotonic() + 30
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
        killer = threading.Thread(target=kill)
        killer.start()
        try:
            with self.assertRaisesRegex(ValueError, 'interrupted'):
                final_verification.run(self.root, done, 'arch', fresh=True)
        finally:
            killer.join()
            (self.root / 'results/hang').unlink()
            pid_file.unlink(missing_ok=True)

    def test_killed_child_is_interrupted_and_gate_names_the_attempt(self):
        done = self.passed()
        self.killed_rerun(done)
        record = self.latest()
        self.assertEqual(record['status'], 'INTERRUPTED')
        log = (self.root / record['log']).read_text()
        self.assertEqual(record['failure_lines'], 0, log)
        self.assertFalse([line for line in log.splitlines()
                          if not line.startswith('COMMAND ') and verify.FAILURE_LINE.search(line)])
        self.assertIsNone(verify.PYTEST_SUMMARY.search(log))
        # The superseded receipt stays void; the gate explains why instead of Errno 2.
        with self.assertRaisesRegex(ValueError, 'INTERRUPTED') as caught:
            final_verification.check_receipt(self.root, done)
        with self.assertRaises(ValueError) as gate:
            self.fixture.gate.check_done()
        for message in (str(caught.exception), str(gate.exception)):
            self.assertIn(record['log'], message)
            self.assertIn('no failure-marked line was observed', message)
            self.assertNotIn('Errno', message)

    def test_genuine_failure_is_failed(self):
        done = self.passed()
        (self.root / 'results/fail').touch()
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            final_verification.run(self.root, done, 'arch', fresh=True)
        record = self.latest()
        self.assertEqual(record['status'], 'FAILED')
        self.assertGreater(record['failure_lines'], 0)
        with self.assertRaisesRegex(ValueError, 'is FAILED.*reported a failure'):
            self.fixture.gate.check_done()

    def test_source_change_during_run_has_its_own_status(self):
        done = self.passed()
        (self.root / 'results/drift').touch()
        with self.assertRaisesRegex(ValueError, 'source changed'):
            final_verification.run(self.root, done, 'arch', fresh=True)
        record = self.latest()
        self.assertEqual(record['status'], 'SOURCE_CHANGED')
        self.assertNotIn('verification failed', record['error'])

    def test_pytest_log_without_summary_is_interrupted(self):
        started = '===== test session starts =====\ncollected 2 items\ntests/a.py::t PASSED [ 50%]'
        self.assertTrue(verify.interruption(1, started))
        self.assertTrue(verify.interruption(-9, 'anything'))
        self.assertIsNone(verify.interruption(1, started + '\n===== 1 failed, 1 passed in 0.10s =====\n'))
        self.assertIsNone(verify.interruption(7, 'plain script failure'))
        self.assertIsNone(verify.interruption(0, started))

    def test_rebind_points_closeout_at_rerun_receipt(self):
        done = self.passed()
        self.killed_rerun(done)
        rerun = final_verification.run(self.root, done, 'arch', fresh=True)
        self.assertEqual(rerun['status'], 'EXECUTED PASS')
        with self.assertRaisesRegex(ValueError, 'invalidated by a later attempt'):
            final_verification.check_receipt(self.root, done)
        result = loop_lifecycle.rebind_receipt(self.root)
        self.assertEqual((result['status'], result['receipt']), ('rebound', rerun['receipt']))
        self.assertEqual(result['previous'], done['verification']['receipt'])
        rebound = json.loads((self.root / project.STATE / 'issue-done.json').read_text())
        self.assertEqual(rebound['verification']['receipt'], rerun['receipt'])
        self.assertEqual(rebound['verification']['scientific'], rerun['scientific'])
        self.assertEqual(final_verification.check_receipt(self.root, rebound)['status'], 'PASS')
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')

    def test_rebind_refuses_a_receipt_for_another_review_signature(self):
        done = self.passed()
        final_verification.run(self.root, done, 'arch', fresh=True)
        changed = dict(done, scope_decisions=[{'note': 'edited after qualification'}])
        self.fixture.save_done(changed)
        before = (self.root / project.STATE / 'issue-done.json').read_text()
        with self.assertRaisesRegex(ValueError, 'review_signature .* does not match'):
            loop_lifecycle.rebind_receipt(self.root)
        self.assertEqual((self.root / project.STATE / 'issue-done.json').read_text(), before)

    def test_rebind_refuses_without_a_current_receipt(self):
        done = self.passed()
        self.killed_rerun(done)
        before = (self.root / project.STATE / 'issue-done.json').read_text()
        with self.assertRaisesRegex(ValueError, 'INTERRUPTED'):
            loop_lifecycle.rebind_receipt(self.root)
        self.assertEqual((self.root / project.STATE / 'issue-done.json').read_text(), before)


if __name__ == '__main__':
    unittest.main()
