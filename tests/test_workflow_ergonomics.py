"""Regression witnesses for the 2026-09-23 self-improvement fixes.

See self-improvement/improvements_2026-09-23_from_1D_Mixing_Experiment.md for
the full evidence and rationale behind each fix exercised here. The
candidate_signature and documentation_review.status message-content fixes are
exercised against a real, fully-deployed fixture in test_framework.py instead
of here, since project.py::source_signature/config() need a fully "ready"
esx/project.json that test_framework.py's deployment fixture already builds.
"""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('esx_deploy', KIT / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
sys.path.insert(0, str(KIT / 'template/tools/esx'))
import loop_gate
import project
import workflow_records as records
import verify


def deployed_project():
    """A minimal, fully-"ready" project -- mirrors test_framework.py's own fixture."""
    tmp = tempfile.TemporaryDirectory(prefix='esx ergonomics ')
    root = Path(tmp.name) / 'project'
    deploy.deploy(root, apply=True)
    example = KIT / 'examples/periodic_diffusion'
    for directory in ('src', 'tests'):
        shutil.copytree(example / directory, root / directory)
    for source, target in [('project.json', 'esx/project.json'), ('project_profile.md', 'esx/project_profile.md'),
                            ('code_map.md', 'docs/code_map.md')]:
        shutil.copyfile(example / source, root / target)
    return tmp, root


class ProjectSignatureCLITests(unittest.TestCase):
    """Fix 3a: a discoverable command for the exact candidate_signature scheme."""

    def setUp(self):
        self.tmp, self.root = deployed_project()
        self.addCleanup(self.tmp.cleanup)

    def test_signature_subcommand_matches_source_signature_function(self):
        expected_default = project.source_signature(self.root)
        expected_scientific = project.source_signature(self.root, scientific=True)
        run = subprocess.run([sys.executable, str(KIT / 'template/tools/esx/project.py'),
                             '--root', str(self.root), 'signature'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['signature'], expected_default)
        run = subprocess.run([sys.executable, str(KIT / 'template/tools/esx/project.py'),
                             '--root', str(self.root), 'signature', '--scientific'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['signature'], expected_scientific)
        self.assertNotEqual(expected_default, expected_scientific)

    def test_signature_differs_from_issue_candidates_own_scheme(self):
        # The exact confusion Problem 3 documents: these two signature schemes
        # must never be interchangeable, or the distinction has no meaning.
        import issue_candidates
        candidate_ref = issue_candidates.capture(self.root, 'X-001')
        project_sig = project.source_signature(self.root)
        candidate_own_signature = json.loads((self.root / candidate_ref['path']).read_text())['signature']
        self.assertNotEqual(candidate_own_signature, project_sig)


class PrepareDoneDefaultsTests(unittest.TestCase):
    """Fix 1a: a draft with nothing unusual to report should already validate."""

    def test_milestone_and_git_defaults_are_schema_valid(self):
        start = {'id': 'X', 'title': 'test', 'timestamp': '2026-09-23T00:00:00Z',
                 'workflow': {'kind': 'investigation'}, 'maintenance': {'baseline': {}}}
        draft = records.prepare_done(start, [], [])
        # Fix target: milestone.logged and git.committed used to default to
        # None, which fails check_milestone()/check_done()'s `is bool` checks.
        self.assertIs(draft['milestone']['logged'], False)
        self.assertIs(draft['git']['committed'], False)
        self.assertGreaterEqual(len(draft['git']['reason'].strip()), 20)
        # A caller with a real decision still overrides the default.
        draft['git'] = {'committed': True, 'sha': 'a' * 40}
        self.assertTrue(draft['git']['committed'])

    def test_defaulted_fields_are_absent_from_pending_as_soon_as_still_valid(self):
        start = {'id': 'X', 'title': 'test', 'timestamp': '2026-09-23T00:00:00Z',
                 'workflow': {'kind': 'investigation'}, 'maintenance': {'baseline': {}}}
        draft = records.prepare_done(start, [], [])
        pending_text = ' '.join(draft['preparation']['pending'])
        self.assertIn('outcome, summary', pending_text)
        # scope_decisions/milestone/git are flagged as overridable defaults,
        # not as entirely-missing required fields.
        self.assertIn('defaulted', pending_text)


class IndependentCheckEvidenceMessageTests(unittest.TestCase):
    """Fix 3c: an empty independent_check.evidence should explain the fix, not just fail."""

    def test_empty_independent_check_evidence_explains_the_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'verify.py'):
                verify.load_evidence(Path(tmp), {'path': '', 'sha256': ''})


class SelfAssessmentNoticeTests(unittest.TestCase):
    """Fix 7: a periodic, un-skippable reminder once the lessons mechanism goes stale."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'devel-loop/loop_state').mkdir(parents=True)

    def write_history(self, rows):
        path = self.root / 'devel-loop/loop_state/loop_history.jsonl'
        path.write_text('\n'.join(json.dumps(r) for r in rows) + ('\n' if rows else ''))

    def bare_gate(self):
        gate = loop_gate.Gate.__new__(loop_gate.Gate)
        gate.root = self.root
        return gate

    def test_no_notice_below_threshold_and_when_lessons_file_absent(self):
        gate = self.bare_gate()
        self.write_history([])
        self.assertIsNone(gate.self_assessment_notice())  # lessons_learned.md absent
        (self.root / 'lessons_learned.md').write_text('# Active lessons\n')
        self.write_history([{'id': f'I-{i}', 'start_timestamp': dt.datetime.now(dt.timezone.utc).isoformat()}
                            for i in range(3)])
        self.assertIsNone(gate.self_assessment_notice(window=10))

    def test_notice_fires_once_enough_iterations_postdate_the_lessons_file(self):
        gate = self.bare_gate()
        (self.root / 'lessons_learned.md').write_text('# Active lessons\n')
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat()
        self.write_history([{'id': f'I-{i}', 'start_timestamp': future} for i in range(10)])
        notice = gate.self_assessment_notice(window=10)
        self.assertIsNotNone(notice)
        self.assertIn('SELF-ASSESSMENT', notice)
        self.assertIn('10', notice)

    def test_updating_lessons_file_resets_the_count(self):
        gate = self.bare_gate()
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)).isoformat()
        self.write_history([{'id': f'I-{i}', 'start_timestamp': future} for i in range(10)])
        (self.root / 'lessons_learned.md').write_text('# Active lessons\n')
        import os, time
        # Ensure the lessons file's mtime is strictly after every history row.
        os.utime(self.root / 'lessons_learned.md', (time.time() + 10, time.time() + 10))
        self.assertIsNone(gate.self_assessment_notice(window=10))


if __name__ == '__main__':
    unittest.main()
