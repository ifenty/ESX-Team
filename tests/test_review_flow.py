"""1.6.0 review flow: retrospective vocabulary, early checkpoint notice, brief rules.

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
import brief
import doc_contract
import loop_gate
import project
import records
import team_retrospective as retro

PROBLEM = {'category': 'reference_convention', 'minutes_lost': 15,
           'summary': 'The implementer re-derived a reference quantity with a wrong factor.',
           'evidence': 'Reviewer round-1 REJECT must_fix; corrected figures in round 2.'}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root


class RetrospectiveVocabularyTests(Fixture):
    def closed_draft(self):
        self.fixture.complete()
        records.save_history(self.root, self.fixture.gate.check_done())
        return retro.draft(self.root)

    def with_solution(self, draft, **solution):
        value = json.loads(json.dumps(draft))
        value.update(problems=[PROBLEM], solutions=[dict({'problem': 0}, **solution)])
        return value

    def test_draft_carries_the_vocabulary_and_accept_ignores_it(self):
        draft = self.closed_draft()
        for word in ('"filed"', '"deferred"', '"fixed"', '"implemented"'):
            self.assertIn(word, draft['guide']['actions'])
        record = self.with_solution(draft, action='fixed', reference='commit 39d1194',
                                    reason='Corrected inside the issue in correction round 2 and confirmed by the reviewer.')
        self.assertEqual(retro.accept(self.root, record)['status'], 'accepted')
        saved = records.json_lines(self.root / project.STATE / 'retrospective_history.jsonl')[-1]
        self.assertNotIn('guide', saved)

    def test_fixed_needs_what_fixed_it_and_why_no_owner_is_needed(self):
        draft = self.closed_draft()
        for bad in ({'action': 'fixed'}, {'action': 'fixed', 'reference': 'v1.5.8'},
                    {'action': 'fixed', 'reference': '', 'reason': 'x' * 50},
                    {'action': 'fixed', 'reference': 'v1.5.8', 'reason': 'too short'}):
            with self.assertRaisesRegex(ValueError, 'fixed solution needs'):
                retro.accept(self.root, self.with_solution(draft, **bad))

    def test_unknown_action_and_missing_owner_name_the_choices(self):
        draft = self.closed_draft()
        with self.assertRaisesRegex(ValueError, r'unknown solution action \'resolved\'; solution actions are: "filed"'):
            retro.accept(self.root, self.with_solution(draft, action='resolved'))
        with self.assertRaisesRegex(ValueError, 'open process-ledger id.*uses action "fixed"'):
            retro.accept(self.root, self.with_solution(draft, action='filed', issue='NOT-AN-ISSUE'))


class CheckpointNoticeTests(Fixture):
    def review(self, round_number, verdict, must_fix=()):
        start = self.fixture.start
        footer = {'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                  'correction_round': round_number, 'verdict': verdict, 'must_fix': list(must_fix)}
        with (self.root / project.STATE / 'dispatch_log.jsonl').open('a') as handle:
            handle.write(json.dumps({'event_id': f'e{round_number}{verdict}', 'agent_id': 'r1', 'agent_type': 'richard',
                                     'status': 'completed', 'footer': footer}) + '\n')

    def next(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            loop_gate.Gate(self.root).next()
        return out.getvalue()

    def test_two_rejected_rounds_in_a_row_announce_the_checkpoint(self):
        self.fixture.prepare('investigation')
        self.review(0, 'REJECT', ['first finding'])
        self.assertNotIn('CHECKPOINT', self.next())
        self.review(1, 'APPROVE_WITH_FIXES', ['a different finding'])
        text = self.next()
        self.assertIn('CHECKPOINT: review rejected SAMPLE-001 in rounds 0, 1 in a row', text)
        self.assertIn('finish active iteration', text)

    def test_an_approval_ends_the_streak(self):
        self.fixture.prepare('investigation')
        self.review(0, 'REJECT', ['first finding'])
        self.review(1, 'REJECT', ['second finding'])
        self.review(2, 'APPROVE')
        self.assertNotIn('CHECKPOINT', self.next())
        self.assertEqual(loop_gate.Gate(self.root).rejection_streak(self.fixture.start), [])


class BriefRuleTests(Fixture):
    def test_implementer_brief_states_the_working_rules_and_how_to_find_its_id(self):
        self.fixture.prepare('investigation')
        text = brief.build(self.root, 'bob', 'SAMPLE-001', 'Qualify the periodic update against its Fourier oracle.')
        for phrase in ('# Working rules', 'calls or cites the function and line', 'statements your change makes stale',
                       'You draft and seal the documentation plan', 'hooks.py whoami --role bob',
                       'YOUR_RUNTIME_AGENT_ID'):
            self.assertIn(phrase, text)
        self.assertNotIn('DISPATCHER_AGENT_ID', text)

    def test_template_brief_asks_for_supported_classes_and_sizing(self):
        template = (self.root / 'esx/templates/brief.md').read_text()
        for phrase in ('Supported input classes', 'never re-derived', 'Expected turn size', 'drafts and seals'):
            self.assertIn(phrase, template)
        self.assertIn('supported input classes', brief.WORKING_RULES[True])
        self.assertIn('is a note', brief.WORKING_RULES[True])


class SupersededTurnTests(Fixture):
    def test_a_resolved_incomplete_turn_with_a_bad_orientation_does_not_block_closeout(self):
        done = self.fixture.complete()
        start = self.fixture.start
        log = records.json_lines(self.root / project.STATE / 'dispatch_log.jsonl')
        completed = next(r for r in log if r.get('agent_type') == 'richard')
        failed = {'event_id': 'superseded-attempt', 'agent_id': completed['agent_id'], 'agent_type': 'richard',
                  'status': 'incomplete', 'correction_round': 0,
                  'footer': {'agent': 'richard', 'issue_id': done['id'], 'iteration_timestamp': done['timestamp'],
                             'orientation': {'path': 'notes/not-a-maintenance-artifact.json', 'sha256': 'x'}}}
        ordered = [r for r in log if r is not completed] + [failed, completed]
        done['subagents']['richard'] = [{'dispatch_id': failed['agent_id'], 'dispatch_event_id': failed['event_id']},
                                        *done['subagents']['richard']]
        errors = doc_contract.check_done(self.root, start, done, ordered, project.source_signature(self.root))
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
