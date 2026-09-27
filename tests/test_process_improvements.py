"""Fault, restart and contract tests for the second ESX-team improvement cycle."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'template/tools/esx'), str(ROOT)]
import doc_inventory as inventory

import ledger_transaction as transaction
import loop_iteration
import loop_gate
import process_evidence
import self_improvement as si
import team_budget as budget
import test_self_improvement as ledger_tests


class EvidenceTests(unittest.TestCase):

    def setUp(self):
        self.fixture = ledger_tests.SelfImprovementTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def close(self):
        (self.root / si.OPEN).write_text('# Open\n')
        (self.root / si.CLOSED).write_text(self.fixture.closed_text())
        self.fixture.refresh_index()

    def test_bad_validation_and_effectiveness_cannot_claim_success(self):
        self.close()
        self.assertEqual(si.validate(self.root), [])
        receipt_path = self.root / 'evidence/receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['checks'][0]['exit'] = 1
        receipt_path.write_text(json.dumps(receipt))
        self.close()
        self.assertIn('successfully', str(si.validate(self.root)))
        receipt['checks'][0]['exit'] = 0
        receipt_path.write_text(json.dumps(receipt))
        effect = self.root / 'evidence/effectiveness.json'
        value = json.loads(effect.read_text())
        value['after'] = 10
        effect.write_text(json.dumps(value))
        self.close()
        self.assertIn('direction', str(si.validate(self.root)))

    def test_missing_wrong_hash_directory_and_external_paths_fail(self):
        name = 'evidence/validation.log'
        for ref in (name, name + '#' + '0' * 64, 'evidence', '../outside'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                process_evidence.reference(self.root, ref)
        with tempfile.TemporaryDirectory() as external:
            path = Path(external) / 'log'
            path.write_text('PASS')
            (self.root / 'external').symlink_to(path)
            with self.assertRaises(ValueError):
                process_evidence.reference(self.root, 'external#' + hashlib.sha256(b'PASS').hexdigest())

    def test_unpublished_object_and_unmatched_source_are_rejected(self):
        tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=self.root, text=True).strip()
        orphan = subprocess.check_output(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'commit-tree', tree], input='orphan\n', cwd=self.root, text=True).strip()
        self.assertFalse(process_evidence.landed(self.root, orphan))
        receipt = self.fixture.receipt.copy()
        receipt['source_sha256'] = {'tools/brief.py': '0' * 64}
        (self.root / 'evidence/receipt.json').write_text(json.dumps(receipt))
        self.close()
        self.assertIn('source differs', str(si.validate(self.root)))

    def test_malformed_record_and_forged_legacy_are_rejected(self):
        path = self.root / si.OPEN
        original = path.read_text()
        path.write_text(original.replace('**UUID**: TEAM-FOOTER-CONTRACT-001\n', ''))
        self.assertIn('without UUID', str(si.validate(self.root)))
        path.write_text(original + '\n**Record-Version**: 1 (migrated)\n**Migration-Source**: invented\n')
        self.assertIn('unverified migration', str(si.validate(self.root)))

    def test_command_receipt_detects_changed_output_and_failed_process(self):
        (ref, result) = process_evidence.record(self.root, 'evidence/real.json', ['tools/brief.py'], [sys.executable, '-c', 'print("measured PASS")'])
        self.assertEqual(process_evidence.validation_errors(self.root, ref, self.fixture.commit), [])
        (self.root / result['checks'][0]['output']['path']).write_text('changed')
        self.assertTrue(process_evidence.validation_errors(self.root, ref, self.fixture.commit))
        (_, failed) = process_evidence.record(self.root, 'evidence/failure.json', ['tools/brief.py'], [sys.executable, '-c', 'raise SystemExit(2)'])
        self.assertEqual(failed['status'], 'FAIL')

class PromotionTests(unittest.TestCase):
    setUp = EvidenceTests.setUp

    def request(self):
        issue = si.parse(self.root / si.OPEN)[0]
        closed = si.parse(self.root / si.CLOSED, text=self.fixture.closed_text())[0]
        closure = {'fields': {k: closed.fields[k] for k in ('Status', 'Date Resolved', 'Implementation-Commit', 'Validation-Evidence', 'Effectiveness-Evidence')}, 'sections': {k: closed.sections[k] for k in ('Implementation', 'Validation', 'Remaining Limitations')}}
        return (issue, closure, transaction.digest(issue.text))

    def test_promotion_preserves_original_and_retry_is_idempotent(self):
        (issue, closure, sha) = self.request()
        before = (self.root / si.OPEN).read_bytes()
        self.assertEqual(transaction.promote(self.root, 'team', issue.uuid, closure, sha)['status'], 'preview')
        self.assertEqual((self.root / si.OPEN).read_bytes(), before)
        self.assertEqual(transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)['status'], 'applied')
        self.assertEqual(si.validate(self.root), [])
        self.assertEqual((self.root / si.BASE / 'records' / (sha + '.md')).read_text(), issue.text)
        self.assertEqual(transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)['status'], 'already_promoted')
        self.assertEqual(len(si.parse(self.root / si.CLOSED)), 1)
        different = json.loads(json.dumps(closure))
        different['fields']['Date Resolved'] = '2026-09-24  09:00'
        with self.assertRaisesRegex(ValueError, 'different closure'):
            transaction.promote(self.root, 'team', issue.uuid, different, sha, True)

    def test_concurrent_promotions_have_one_winner_without_duplicate_records(self):
        import concurrent.futures
        import threading
        (issue, closure, sha) = self.request()
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            try:
                return transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)['status']
            except ValueError:
                return 'refused_stale_request'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(results.count('applied'), 1, results)
        self.assertEqual(si.validate(self.root), [])
        self.assertEqual(len(si.parse(self.root / si.CLOSED)), 1)

    def test_edit_between_preparation_and_lock_is_not_overwritten(self):
        (issue, closure, sha) = self.request()
        original = transaction.transact
        path = self.root / si.OPEN

        def edit_then_transact(*args, **kwargs):
            path.write_text(path.read_text() + '\nConcurrent owner note\n')
            return original(*args, **kwargs)
        with patch.object(transaction, 'transact', side_effect=edit_then_transact), self.assertRaisesRegex(ValueError, 'changed'):
            transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)
        self.assertIn('Concurrent owner note', path.read_text())
        self.assertEqual(len(si.parse(self.root / si.CLOSED)), 0)

    def test_failed_validation_and_stale_source_leave_originals_unchanged(self):
        (issue, closure, sha) = self.request()
        before = {p: (self.root / p).read_bytes() for p in (si.OPEN, si.CLOSED, si.INDEX)}
        closure['fields']['Implementation-Commit'] = '0000000'
        with self.assertRaises(ValueError):
            transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)
        for (p, data) in before.items():
            self.assertEqual((self.root / p).read_bytes(), data)
        with self.assertRaisesRegex(ValueError, 'changed'):
            transaction.promote(self.root, 'team', issue.uuid, closure, '0' * 64, True)

    def interrupted(self, exception=KeyboardInterrupt):
        (issue, closure, sha) = self.request()
        original = transaction.replace
        failed = False

        def replace(root, name, text):
            nonlocal failed
            if name == str(si.CLOSED) and (not failed):
                failed = True
                raise exception('injected write failure')
            return original(root, name, text)
        with patch.object(transaction, 'replace', side_effect=replace), self.assertRaises(exception):
            transaction.promote(self.root, 'team', issue.uuid, closure, sha, True)

    def test_ordinary_failure_rolls_back_and_hard_interruption_recovers(self):
        before = {p: (self.root / p).read_bytes() for p in (si.OPEN, si.CLOSED, si.INDEX)}
        self.interrupted(OSError)
        for (p, data) in before.items():
            self.assertEqual((self.root / p).read_bytes(), data)
        self.assertFalse(transaction.pending(self.root))
        self.interrupted()
        self.assertTrue(transaction.pending(self.root))
        self.assertIn('pending', str(si.validate(self.root)))
        self.assertEqual(transaction.recover(self.root)['status'], 'completed')
        self.assertEqual(si.validate(self.root), [])
        self.assertEqual(transaction.recover(self.root)['status'], 'no_pending_transaction')

    def test_recovery_preserves_concurrent_edits(self):
        self.interrupted()
        path = self.root / si.CLOSED
        path.write_text(path.read_text() + '\nConcurrent owner note\n')
        for rollback in (True, False):
            with self.assertRaisesRegex(ValueError, 'concurrent edit'):
                transaction.recover(self.root, rollback=rollback)
        self.assertIn('Concurrent owner note', path.read_text())

    def test_explicit_rollback_restores_originals(self):
        before = {p: (self.root / p).read_bytes() for p in (si.OPEN, si.CLOSED, si.INDEX)}
        self.interrupted()
        self.assertEqual(transaction.recover(self.root, rollback=True)['status'], 'rolled_back')
        for (p, data) in before.items():
            self.assertEqual((self.root / p).read_bytes(), data)
if __name__ == '__main__':
    unittest.main()
