"""Checks for the separate ESX-team self-improvement ledgers and generated index."""

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / 'template/tools/esx'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("self_improvement", TOOLS / "self_improvement.py")
S = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = S
SPEC.loader.exec_module(S)


OPEN = """# Open

## 🔴 PROPOSED: Paid reviewer receives an incomplete footer contract

**Date Identified**: 2026-09-23  07:00
**Status**: Proposed
**UUID**: TEAM-FOOTER-CONTRACT-001
**Category**: report_contract
**Severity**: Medium
**Assessment**: assessments/2026-09-23-test/assessment.md
**Anchors**: tools/brief.py; tools/footer_contract.py

### Issue
The generated prompt omits fields required by the validator, causing a paid repair turn.

### Evidence
The retained trial records one incomplete turn followed by a footer-only correction.

### Potential Impact
Every affected review pays for an avoidable correction and delays candidate acceptance.

### Proposed Fix
Generate every role footer example from one typed schema and validate it before completion.

### Acceptance Criteria
A generated brief validates unchanged, and removing a required field fails the focused test.

### Expected Effect
Footer-only correction turns for this category fall from one per review to zero.
"""

CLOSED = """# Closed

## 🟢 VERIFIED: Paid reviewer receives a complete footer contract

**Date Identified**: 2026-09-23  07:00
**Date Resolved**: 2026-09-23  08:00
**Status**: Verified effective
**UUID**: TEAM-FOOTER-CONTRACT-001
**Category**: report_contract
**Severity**: Medium
**Assessment**: assessments/2026-09-23-test/assessment.md
**Anchors**: tools/brief.py; tools/footer_contract.py
**Implementation-Commit**: {commit}
**Validation-Evidence**: evidence/validation.log
**Effectiveness-Evidence**: evidence/effectiveness.json

### Issue
The generated prompt omitted fields required by the validator, causing a paid repair turn.

### Evidence
The retained trial recorded one incomplete turn followed by a footer-only correction.

### Potential Impact
Every affected review paid for an avoidable correction and delayed candidate acceptance.

### Proposed Fix
Generate every role footer example from one typed schema and validate it before completion.

### Implementation
The brief generator and validator now consume the same role-specific typed footer schema.

### Validation
The focused test validates a generated example and rejects a deliberately deleted field.

### Remaining Limitations
Effectiveness evidence covers the bounded fixture workload, not every future provider response.
"""


class SelfImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / S.BASE).mkdir(parents=True)
        (self.root / "open_issues.md").write_text("# ESX open\n")
        (self.root / "closed_issues.md").write_text("# ESX closed\n")
        for name in ('tools/brief.py', 'tools/footer_contract.py', 'assessments/2026-09-23-test/assessment.md'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture evidence source\n')
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        subprocess.run(
            [
                "git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "fixture",
            ],
            cwd=self.root,
            check=True,
        )
        self.commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        (self.root / "evidence").mkdir()
        (self.root / "evidence/validation.log").write_text("PASS\n")
        (self.root / "evidence/effectiveness.json").write_text(json.dumps(
            {'metric': 'cost', 'unit': 'USD', 'method': 'matched fixture', 'before': 1, 'after': 0, 'direction': 'lower'}))
        self.receipt = {'version': 1, 'status': 'PASS', 'source_sha256': {
            'tools/brief.py': hashlib.sha256((self.root / 'tools/brief.py').read_bytes()).hexdigest()},
            'checks': [{'command': ['fixture'], 'executed': True, 'exit': 0,
                        'output': S.process_evidence.ref(self.root, self.root / 'evidence/validation.log')}]}
        (self.root / 'evidence/receipt.json').write_text(json.dumps(self.receipt))
        (self.root / S.OPEN).write_text(OPEN)
        (self.root / S.CLOSED).write_text("# Closed\n")
        self.refresh_index()

    def refresh_index(self):
        (self.root / S.INDEX).write_text(S.index_text(S.parse(self.root / S.CLOSED)))

    def closed_text(self):
        def ref(name):
            return name + '#' + hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        return CLOSED.format(commit=self.commit).replace('evidence/validation.log', ref('evidence/receipt.json')).replace(
            'evidence/effectiveness.json', ref('evidence/effectiveness.json'))

    def freeze_legacy(self):
        rows = {r.uuid: {'sha256': hashlib.sha256(r.text.encode()).hexdigest(),
                        'source': r.fields['Migration-Source'], 'ledger': str(p)}
                for p in (S.OPEN, S.CLOSED) for r in S.parse(self.root / p) if r.legacy}
        (self.root / S.BASE / 'migration_manifest.json').write_text(json.dumps({'version': 1, 'records': rows}))

    def test_valid_open_and_generated_index(self):
        self.assertEqual(S.validate(self.root), [])
        parsed = S.parse(self.root / S.OPEN)
        self.assertEqual(parsed[0].uuid, "TEAM-FOOTER-CONTRACT-001")

    def test_duplicate_across_esx_and_team_ledgers_is_rejected(self):
        (self.root / "open_issues.md").write_text(OPEN)
        errors = S.validate(self.root)
        self.assertTrue(any("both ESX-team and ESX ledgers" in error for error in errors))

    def test_closed_requires_real_commit_evidence_and_effectiveness(self):
        (self.root / S.OPEN).write_text("# Open\n")
        (self.root / S.CLOSED).write_text(self.closed_text())
        self.refresh_index()
        self.freeze_legacy()
        self.assertEqual(S.validate(self.root), [])
        (self.root / "evidence/effectiveness.json").unlink()
        self.assertTrue(any("Effectiveness-Evidence" in error for error in S.validate(self.root)))

    def test_stale_index_is_rejected(self):
        (self.root / S.INDEX).write_text("stale\n")
        self.assertTrue(any("is stale" in error for error in S.validate(self.root)))

    def test_legacy_migration_preserves_incomplete_historical_evidence(self):
        (self.root / S.OPEN).write_text(
            "# Open\n\n## 🔴 LEGACY: old process issue\n\n"
            "**UUID**: LOOP-OLD-PROBLEM-001\n"
            "**Record-Version**: 1 (migrated)\n"
            "**Migration-Source**: open_issues.md:10\n"
        )
        self.refresh_index()
        self.freeze_legacy()
        self.assertEqual(S.validate(self.root), [])

    def test_classification_prefers_process_consequence(self):
        (self.root / "open_issues.md").write_text(
            "# ESX\n\n## 🔴 UNRESOLVED: review dispatch loses its footer\n\n"
            "**UUID**: GATE-REVIEW-FOOTER-001\n\n"
            "The loop dispatch and reviewer workflow need a stable report contract.\n"
        )
        rows = S.classify(self.root)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
