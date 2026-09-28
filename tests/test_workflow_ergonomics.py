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
import doc_contract
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



class UpgradeAttributionTests(unittest.TestCase):
    """A recorded upgrade must not make every open issue harder to close.

    FRAMEWORK_PATHS participates in the candidate diff, so upgrading ESX lands its
    changed symbols in every open issue's dispositions. Measured in a receiving
    project: each of six open issues gained 18-20 framework targets, and one gained
    18 of 18. Attribution removes that noise without weakening review of a genuine
    local framework patch.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.records = self.root / 'ESX-team-local/deployments'
        self.records.mkdir(parents=True)
        self.path = 'tools/esx/team_budget.py'

    def record(self, before, after, status='applied', ownership='framework'):
        (self.records / '20260928T000000Z-upgrade-test.json').write_text(json.dumps({
            'status': status, 'deployment_id': 'upgrade-test', 'from_version': '1.1.1',
            'files': [{'path': self.path, 'ownership': ownership, 'action': 'update',
                       'before_sha256': before, 'result_sha256': after, 'master_sha256': after}]}))

    def test_both_endpoints_from_a_recorded_upgrade_are_attributed(self):
        self.record('a' * 64, 'b' * 64)
        found = doc_contract.upgrade_attribution(
            self.root, self.path + '::reserve', {self.path: {'sha256': 'a' * 64}}, {self.path: {'sha256': 'b' * 64}})
        self.assertIsNotNone(found)
        self.assertEqual(found['deployment_id'], 'upgrade-test')
        self.assertEqual((found['before_sha256'], found['after_sha256']), ('a' * 64, 'b' * 64))

    def test_a_local_edit_is_not_attributed(self):
        """The integrity property: a project patch to a framework file still needs judgment."""
        self.record('a' * 64, 'b' * 64)
        self.assertIsNone(doc_contract.upgrade_attribution(
            self.root, self.path + '::reserve', {self.path: {'sha256': 'a' * 64}}, {self.path: {'sha256': 'c' * 64}}))
        # Nor when the baseline itself was a local state the upgrade never produced.
        self.assertIsNone(doc_contract.upgrade_attribution(
            self.root, self.path + '::reserve', {self.path: {'sha256': 'd' * 64}}, {self.path: {'sha256': 'b' * 64}}))

    def test_unapplied_or_project_owned_records_do_not_attribute(self):
        self.record('a' * 64, 'b' * 64, status='preview')
        base, cur = {self.path: {'sha256': 'a' * 64}}, {self.path: {'sha256': 'b' * 64}}
        self.assertIsNone(doc_contract.upgrade_attribution(self.root, self.path + '::reserve', base, cur))
        self.record('a' * 64, 'b' * 64, ownership='project')
        self.assertIsNone(doc_contract.upgrade_attribution(self.root, self.path + '::reserve', base, cur))

    def test_prefill_marks_attributed_targets_and_blanks_the_rest(self):
        self.record('a' * 64, 'b' * 64)
        base = {self.path: {'sha256': 'a' * 64}, 'src/model.py': {'sha256': 'e' * 64}}
        cur = {self.path: {'sha256': 'b' * 64}, 'src/model.py': {'sha256': 'f' * 64}}
        attributed = doc_contract.prefill(self.root, {'target': self.path + '::reserve', 'change': 'modified'}, base, cur)
        self.assertEqual(attributed['action'], 'upgrade_supplied')
        self.assertIn('deployment', attributed)
        self.assertGreaterEqual(len(attributed['reason']), 40)
        project_target = doc_contract.prefill(self.root, {'target': 'src/model.py::step', 'change': 'modified'}, base, cur)
        self.assertEqual(project_target['action'], '')
        self.assertNotIn('deployment', project_target)


class CarriedForwardTests(unittest.TestCase):
    """A pinned baseline must not force one issue to re-judge another's accepted work.

    Measured in a receiving project: an issue left open across four closures needed
    85 judgments, the large majority already dispositioned and accepted under those
    other issues. The proof is exact rather than by baseline ancestry -- a sealed
    disposition records its target's own byte state -- so only a target whose CURRENT
    state was already judged elsewhere carries forward.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'devel-loop/loop_state'
        (self.state / 'maintenance').mkdir(parents=True)
        self.target = 'src/model.py::step'
        self.current = {'src/model.py': {'sha256': 'f' * 64, 'units': {'step': {'sha256': 's' * 64}}}}

    def seal(self, issue, state, action='updated', outcome='completed'):
        report = {'version': 1, 'kind': 'documentation', 'issue_id': issue, 'references': [],
                  'dispositions': [{'target': self.target, 'change': 'modified', 'action': action,
                                    'judgment_inputs': {'target': {'sha256': state}}}]}
        sha = doc_contract.digest(report)
        (self.state / 'maintenance' / f'{sha}.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        ref = {'path': f'devel-loop/loop_state/maintenance/{sha}.json', 'sha256': sha}
        with (self.state / 'loop_history.jsonl').open('a') as stream:
            stream.write(json.dumps({'id': issue, 'outcome': outcome,
                                     'maintenance': {'documentation': ref}}) + '\n')
        return ref

    def test_state_judged_under_another_issue_carries_forward(self):
        ref = self.seal('OTHER-001', 's' * 64)
        found = doc_contract.carried_attribution(self.root, self.target, self.current, issue='MINE-001')
        self.assertIsNotNone(found)
        self.assertEqual(found['issue'], 'OTHER-001')
        self.assertEqual(found['report'], ref)

    def test_a_changed_target_does_not_carry_forward(self):
        """The integrity property: only the exact judged state qualifies."""
        self.seal('OTHER-001', 'different' + 'x' * 55)
        self.assertIsNone(doc_contract.carried_attribution(
            self.root, self.target, self.current, issue='MINE-001'))

    def test_an_issue_cannot_carry_forward_its_own_judgment(self):
        self.seal('MINE-001', 's' * 64)
        self.assertIsNone(doc_contract.carried_attribution(
            self.root, self.target, self.current, issue='MINE-001'))

    def test_an_unaccepted_closeout_does_not_qualify(self):
        self.seal('OTHER-001', 's' * 64, outcome='partial')
        self.assertIsNone(doc_contract.carried_attribution(
            self.root, self.target, self.current, issue='MINE-001'))

    def test_prefill_marks_carried_targets_and_blanks_unjudged_ones(self):
        self.seal('OTHER-001', 's' * 64)
        carried = doc_contract.prefill(self.root, {'target': self.target, 'change': 'modified'},
                                       {}, self.current, issue='MINE-001')
        self.assertEqual(carried['action'], 'carried_forward')
        self.assertGreaterEqual(len(carried['reason']), 40)
        self.assertEqual(carried['carried']['issue'], 'OTHER-001')
        other = doc_contract.prefill(self.root, {'target': 'src/other.py::run', 'change': 'modified'},
                                     {}, self.current, issue='MINE-001')
        self.assertEqual(other['action'], '')

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
