"""TEAM-LEDGER-AHEAD-001: the permanent ledger records only a resolution the gate accepted.

--check-done moves a completed issue's open entry into closed_issues.md as the
consequence of acceptance; a refused closeout leaves both ledgers untouched.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_framework
import loop_gate
import project
import records

OPEN = '''# Open issues

Preamble text that must survive the move byte for byte.

## 🔴 UNRESOLVED: Diffusion qualification

**Date Identified**: 2026-09-01T00:00:00Z
**Status**: Unresolved
**UUID**: SAMPLE-001
**Anchors**: src/diffusion.py::step; tests/check_diffusion.py::<module>

### Evidence
Measured Fourier decay before the change.

## UNRESOLVED: Unrelated follow-up

**Status**: Unresolved
**UUID**: OTHER-002
**Anchors**: src/diffusion.py::step
'''
CLOSED = '# Closed issues\n'


class LedgerAheadTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.done = self.fixture.complete()
        # The fixture pre-moves the entry (the legacy manual procedure); restore
        # the realistic state in which Arch has not touched the ledgers.
        (self.root / 'open_issues.md').write_text(OPEN)
        (self.root / 'closed_issues.md').write_text(CLOSED)

    def ledgers(self):
        return (self.root / 'open_issues.md').read_text(), (self.root / 'closed_issues.md').read_text()

    def cli(self):
        return subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/loop_gate.py'), '--check-done'],
                              cwd=self.root.parent, capture_output=True, text=True)

    def assert_still_open(self):
        self.assertEqual(self.ledgers(), (OPEN, CLOSED))
        self.assertIn('SAMPLE-001', records.issues(self.root))
        self.assertNotIn('SAMPLE-001', records.issues(self.root, closed=True))
        self.assertFalse((self.root / 'devel-loop/loop_state/ledger-transactions/pending.json').exists())

    def test_void_receipt_is_refused_and_nothing_is_moved(self):
        done = json.loads(json.dumps(self.done))
        done['verification']['receipt'] = 'f' * 64
        self.fixture.save_done(done)
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.fixture.gate.check_done()
        self.assert_still_open()
        run = self.cli()
        self.assertEqual(run.returncode, 1, run.stdout)
        self.assertIn('receipt', run.stderr)
        self.assert_still_open()
        self.assertEqual(records.json_lines(self.root / project.STATE / 'loop_history.jsonl'), [])

    def test_accepted_closeout_moves_the_entry_exactly(self):
        run = self.cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        done = json.loads(run.stdout)
        self.assertEqual(done['outcome'], 'completed')
        self.assertTrue(done['open_issues_md_updated'])
        opened, closed = self.ledgers()
        self.assertNotIn('SAMPLE-001', records.issues(self.root))
        self.assertIn('OTHER-002', records.issues(self.root))
        entry = records.issues(self.root, closed=True)['SAMPLE-001']
        self.assertEqual(entry['state'], 'resolved')
        self.assertIn('**Date Resolved**: ' + done['closed_at'] + '\n', closed)
        # Everything outside the moved entry, and the entry's own body, is preserved.
        self.assertEqual(opened, OPEN.replace(OPEN[OPEN.index('## 🔴'):OPEN.index('## UNRESOLVED: Unrelated')], ''))
        for line in ('**Date Identified**: 2026-09-01T00:00:00Z\n**Date Resolved**', '**UUID**: SAMPLE-001\n',
                     '**Anchors**: src/diffusion.py::step; tests/check_diffusion.py::<module>\n',
                     '### Evidence\nMeasured Fourier decay before the change.\n'):
            self.assertIn(line, closed)
        self.assertTrue(closed.startswith(CLOSED.rstrip() + '\n\n## 🟢 RESOLVED: Diffusion qualification\n'))
        history = records.json_lines(self.root / project.STATE / 'loop_history.jsonl')
        self.assertEqual([row['closed_at'] for row in history], [done['closed_at']])
        # Re-running on the already-moved entry is idempotent.
        again = self.cli()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)['closed_at'], done['closed_at'])
        self.assertEqual(self.ledgers(), (opened, closed))

    def test_late_failure_after_the_staged_move_restores_both_ledgers(self):
        original = loop_gate.Gate._check_done

        def fail_unstaged(gate):
            if gate.ledger_overrides is None:
                raise ValueError('simulated failure after the staged move passed')
            return original(gate)

        with patch.object(loop_gate.Gate, '_check_done', fail_unstaged):
            with self.assertRaisesRegex(ValueError, 'simulated failure'):
                self.fixture.gate.check_done()
        self.assert_still_open()

    def test_premoved_entry_remains_accepted_for_compatibility(self):
        self.fixture.write_issue()
        (self.root / 'open_issues.md').write_text('# Open issues\n')
        (self.root / 'closed_issues.md').write_text(
            '# Closed issues\n\n## RESOLVED: Diffusion qualification\n**Status**: Resolved\n**UUID**: SAMPLE-001\n')
        before = self.ledgers()
        self.assertEqual(self.fixture.gate.check_done()['outcome'], 'completed')
        self.assertEqual(self.ledgers(), before)

    def test_entry_in_both_ledgers_is_never_accepted(self):
        (self.root / 'closed_issues.md').write_text(
            '# Closed issues\n\n## RESOLVED: Diffusion qualification\n**Status**: Resolved\n**UUID**: SAMPLE-001\n')
        before = self.ledgers()
        with self.assertRaisesRegex(ValueError, 'both open and closed'):
            self.fixture.gate.check_done()
        self.assertEqual(self.ledgers(), before)

    def test_incomplete_outcomes_never_move_the_entry(self):
        done = json.loads(json.dumps(self.done))
        done.update(outcome='partial', next_step='Rerun the Fourier check at a finer grid before closing.')
        self.fixture.save_done(done)
        self.fixture.gate.check_done()
        self.assertEqual(self.ledgers(), (OPEN, CLOSED))


if __name__ == '__main__':
    unittest.main()
