"""Schema-3 retrospective confirmations (TEAM-RETRO-SUCCESS-001).

A confirmation records an approach that worked and should be repeated. It needs
category, summary and evidence, but no minutes_lost and no solution owner. An
empty problems list is explained by a no_problem_reason or by one confirmation
whose evidence meets the same 60-character floor. Recurrence stays problems-only.
Offline: synthetic deployment fixture, no provider calls.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
import records
import team_accounting as accounting
import team_retrospective as retro

REASON = ('The synthetic workflow completed successfully; simulated native reports have '
          'unknown provider costs and therefore cannot establish a zero cost live run.')
CONFIRMATION = {
    'category': 'restated_rules_prevented_rework',
    'summary': 'Restating the grid rules in the Bob packet avoided a correction round.',
    'evidence': 'Zero correction rounds this iteration against one 59-tool-call round in the prior '
                'iteration where the same rule was left unstated; accounting receipt attached.'}


class RetroSuccessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def closed_draft(self):
        self.fixture.complete()
        records.save_history(self.root, self.fixture.gate.check_done())
        return retro.draft(self.root)

    def variant(self, draft, **changes):
        value = json.loads(json.dumps(draft))
        value.update(changes)
        return value

    def test_draft_emits_schema_3_with_both_arrays(self):
        draft = self.closed_draft()
        self.assertEqual(draft['schema_version'], 3)
        self.assertEqual(draft['problems'], [])
        self.assertEqual(draft['confirmations'], [])
        self.assertEqual(retro.validate_measurements(self.root, draft, retro.pending(self.root)), [])

    def test_confirmations_alone_explain_empty_problems(self):
        draft = self.closed_draft()
        record = self.variant(draft, confirmations=[CONFIRMATION])
        self.assertEqual(record['no_problem_reason'], '')
        self.assertNotIn('minutes_lost', CONFIRMATION)
        self.assertEqual(retro.accept(self.root, record)['status'], 'accepted')
        self.assertIsNone(retro.pending(self.root))
        saved = accounting.rows(self.root / accounting.STATE / 'retrospective_history.jsonl')[-1]
        self.assertEqual(saved['confirmations'], [CONFIRMATION])

    def test_confirmation_without_substantive_evidence_rejected(self):
        draft = self.closed_draft()
        for bad in (dict(CONFIRMATION, evidence='worked'), dict(CONFIRMATION, evidence=' ' * 80),
                    {k: v for k, v in CONFIRMATION.items() if k != 'evidence'},
                    dict(CONFIRMATION, category=''), 'worked well'):
            record = self.variant(draft, confirmations=[bad], no_problem_reason=REASON)
            with self.assertRaisesRegex(ValueError, 'confirmation 0 needs'):
                retro.accept(self.root, record)
        with self.assertRaisesRegex(ValueError, 'confirmations must be a list'):
            retro.accept(self.root, self.variant(draft, confirmations=None, no_problem_reason=REASON))
        self.assertIsNotNone(retro.pending(self.root))

    def test_content_free_confirmation_cannot_replace_explanation(self):
        draft = self.closed_draft()
        short = dict(CONFIRMATION, evidence='One correction round fewer than before.')
        self.assertTrue(20 <= len(short['evidence']) < 60)
        for confirmations in ([], [short], [short, short]):
            with self.assertRaisesRegex(ValueError, 'explain a no-problem result'):
                retro.accept(self.root, self.variant(draft, confirmations=confirmations))
        # The shorter confirmation is valid once the explanation comes from elsewhere.
        record = self.variant(draft, confirmations=[short], no_problem_reason=REASON)
        self.assertEqual(retro.accept(self.root, record)['status'], 'accepted')

    def test_version_2_submission_unchanged(self):
        draft = self.closed_draft()
        legacy = self.variant(draft, schema_version=2, no_problem_reason=REASON)
        legacy.pop('confirmations')
        with self.assertRaisesRegex(ValueError, 'confirmations require schema_version 3'):
            retro.accept(self.root, dict(legacy, confirmations=[CONFIRMATION]))
        with self.assertRaisesRegex(ValueError, 'explain a no-problem result'):
            retro.accept(self.root, dict(legacy, no_problem_reason=''))
        self.assertEqual(retro.accept(self.root, legacy)['status'], 'accepted')
        with self.assertRaisesRegex(ValueError, 'schema_version 2 or 3'):
            retro.accept(self.root, self.variant(draft, schema_version=4, no_problem_reason=REASON))


class RecurrenceStaysProblemsOnly(unittest.TestCase):
    def setUp(self):
        import tempfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.history = self.root / accounting.STATE / 'retrospective_history.jsonl'
        self.history.parent.mkdir(parents=True)

    def test_version_2_history_recurrence_unchanged(self):
        for i in range(2):
            accounting.append(self.history, {'schema_version': 2, 'id': str(i), 'problems': [{'category': 'footer_shape'}],
                                             'solutions': [{'problem': 0, 'action': 'deferred', 'issue': 'FIX'}]})
        self.assertEqual(retro.recurring_issues(self.root, {'FIX'}), ['FIX'])
        current = {'problems': [{'category': 'footer_shape'}], 'solutions': []}
        self.assertTrue(retro.recurrence_errors(self.root, current, {'FIX'}))

    def test_confirmations_never_schedule_or_trigger_recurrence(self):
        for i in range(3):
            accounting.append(self.history, {'schema_version': 3, 'id': str(i), 'problems': [], 'solutions': [
                {'problem': 0, 'action': 'deferred', 'issue': 'FIX'}],
                'confirmations': [dict(CONFIRMATION, category='footer_shape')]})
        self.assertEqual(retro.recurring_issues(self.root, {'FIX'}), [])
        current = {'schema_version': 3, 'problems': [{'category': 'footer_shape'}], 'solutions': [],
                   'confirmations': [dict(CONFIRMATION, category='footer_shape')]}
        self.assertEqual(retro.recurrence_errors(self.root, current, {'FIX'}), [])
        # A confirmation repeating a prior problem category is not itself a recurrence.
        accounting.append(self.history, {'schema_version': 3, 'problems': [{'category': 'footer_shape'}]})
        self.assertEqual(retro.recurrence_errors(self.root, {'schema_version': 3, 'problems': [],
                         'confirmations': [dict(CONFIRMATION, category='footer_shape')]}, {'FIX'}), [])


if __name__ == '__main__':
    unittest.main()
