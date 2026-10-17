"""1.7.0: grouped scientific verification.

A long scientific suite is split into independently runnable, independently
reusable groups. One aggregate record, which closeout and the receipt cite like
today's single suite record, is valid only while every group is intact, passing,
current, owned by the same owner and equal to the configured suite. Offline,
synthetic deployment fixtures.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
import final_verification
import loop_lifecycle
import project
import ralph_stop
import verify
from project import STATE, atomic_json, digest

# Group "a" records each execution and takes a moment; group "b" fails on demand.
RAN_A = "from pathlib import Path; import time; time.sleep(1.0); Path('results/ran_a').open('a').write('x')"
RAN_B = ("from pathlib import Path; import sys; Path('results/ran_b').open('a').write('x'); "
         "sys.exit(1 if Path('results/fail_b').exists() else 0)")
GROUPS = [{'name': 'alpha', 'commands': [['{python}', '-c', RAN_A], ['{python}', 'tests/check_diffusion.py']]},
          {'name': 'beta', 'commands': [['{python}', '-c', RAN_B]]}]


def count(root, name):
    path = Path(root) / 'results' / name
    return len(path.read_text()) if path.exists() else 0


class GroupFixture(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.configure(GROUPS)
        (self.root / 'results').mkdir(exist_ok=True)

    def configure(self, groups):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg['verification'].pop('scientific', None)
        cfg['verification']['scientific_groups'] = copy.deepcopy(groups)
        atomic_json(path, cfg)

    def passed(self):
        done = self.fixture.complete(qualify=False)
        result = final_verification.run(self.root, done, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        done['verification'].update(scientific=result['scientific'], receipt=result['receipt'])
        self.fixture.save_done(done)
        return done, result

    def reseal(self, aggregate):
        sha = digest(aggregate)
        ref = {'path': f'{STATE}/verification/{sha}.json', 'sha256': sha}
        atomic_json(self.root / ref['path'], aggregate)
        return ref

    def aggregate_of(self, ref):
        return json.loads((self.root / ref['path']).read_text())

    def current(self):
        return self.root / STATE / 'final-verification/current.json'


class ConfigTests(GroupFixture):
    def write(self, verification):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg['verification'] = dict(cfg['verification'], **verification)
        for key in [k for k, v in verification.items() if v is None]:
            cfg['verification'].pop(key)
        path.write_text(json.dumps(cfg))

    def test_groups_flatten_into_the_scientific_suite_in_order(self):
        cfg = project.config(self.root)
        self.assertEqual(cfg['verification']['scientific'], GROUPS[0]['commands'] + GROUPS[1]['commands'])
        self.assertEqual([g['name'] for g in cfg['verification']['scientific_groups']], ['alpha', 'beta'])

    def test_invalid_group_configurations_are_refused(self):
        cmd = [['{python}', 'tests/check_diffusion.py']]
        for groups, message in [
                ([{'name': 'a', 'commands': cmd}, {'name': 'a', 'commands': cmd}], 'duplicate'),
                ([{'name': 'a', 'commands': []}], 'non-empty commands'),
                ([{'name': 'A b', 'commands': cmd}], 'must match'),
                ([{'name': 'a', 'commands': [[]]}], 'invalid command'),
                ([{'name': 'a', 'commands': cmd, 'extra': 1}], 'exactly a name'),
                ([], 'non-empty list')]:
            self.write({'scientific_groups': groups})
            with self.assertRaisesRegex(ValueError, message):
                project.config(self.root)

    def test_groups_and_a_nonempty_scientific_list_are_mutually_exclusive(self):
        self.write({'scientific': [['{python}', 'tests/check_diffusion.py']]})
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            project.config(self.root)
        self.write({'scientific': []})  # the template's empty default may stay beside groups
        self.assertEqual(len(project.config(self.root)['verification']['scientific']), 3)

    def test_single_suite_config_is_unchanged(self):
        self.write({'scientific_groups': None, 'scientific': [['{python}', 'tests/check_diffusion.py']]})
        cfg = project.config(self.root)
        self.assertNotIn('scientific_groups', cfg['verification'])
        self.assertEqual(cfg['verification']['scientific'], [['{python}', 'tests/check_diffusion.py']])
        self.assertIsNone(verify.groups_of(cfg))
        self.assertEqual(verify.run(self.root, 'scientific', 'arch')['status'], 'EXECUTED PASS')


class GroupedRunTests(GroupFixture):
    def test_full_grouped_pass_is_accepted_by_every_validator(self):
        done, result = self.passed()
        aggregate = verify.load_evidence(self.root, result['scientific'])
        self.assertEqual([g['name'] for g in aggregate['groups']], ['alpha', 'beta'])
        self.assertEqual(aggregate['commands'], project.config(self.root)['verification']['scientific'])
        self.assertEqual(aggregate['command_digest'], digest(aggregate['commands']))
        self.assertEqual((count(self.root, 'ran_a'), count(self.root, 'ran_b')), (1, 1))
        final_verification.check_receipt(self.root, done)
        self.fixture.gate.check_done()
        # The receipt is rebound to the closeout without running anything.
        self.assertEqual(loop_lifecycle.rebind_receipt(self.root)['executed'], False)
        self.assertEqual(count(self.root, 'ran_a'), 1)

    def test_a_group_record_cannot_stand_for_the_suite(self):
        _, result = self.passed()
        group = self.aggregate_of(result['scientific'])['groups'][0]['evidence']
        with self.assertRaisesRegex(ValueError, 'scientific group alpha'):
            verify.load_evidence(self.root, group)

    def test_a_failed_group_is_resumed_at_group_granularity(self):
        done = self.fixture.complete(qualify=False)
        (self.root / 'results/fail_b').touch()
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            final_verification.run(self.root, done, 'arch')
        self.assertEqual((count(self.root, 'ran_a'), count(self.root, 'ran_b')), (1, 1))
        self.assertEqual([r['status'] for r in verify.group_status(self.root, 'arch')], ['current', 'missing'])
        self.assertFalse(self.current().exists())
        _, record = final_verification.latest_attempt(self.root)
        self.assertEqual(record['status'], 'FAILED')
        (self.root / 'results/fail_b').unlink()
        result = final_verification.run(self.root, done, 'arch')
        self.assertEqual(result['status'], 'EXECUTED PASS')
        self.assertEqual({g['name']: g['status'] for g in result['groups']},
                         {'alpha': 'REUSED EVIDENCE', 'beta': 'EXECUTED PASS'})
        self.assertEqual((count(self.root, 'ran_a'), count(self.root, 'ran_b')), (1, 2))

    def test_source_edit_makes_the_aggregate_and_every_group_stale(self):
        _, result = self.passed()
        source = self.root / 'src/diffusion.py'
        source.write_text(source.read_text() + '\n# edit\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            verify.load_evidence(self.root, result['scientific'])
        self.assertEqual([r['status'] for r in verify.group_status(self.root, 'arch')], ['stale', 'stale'])

    def test_edited_group_record_invalidates_the_aggregate(self):
        _, result = self.passed()
        group = self.aggregate_of(result['scientific'])['groups'][1]['evidence']
        path = self.root / group['path']
        record = json.loads(path.read_text())
        record['elapsed_seconds'] = 0.0
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'modified'):
            verify.load_evidence(self.root, result['scientific'])

    def test_a_modified_group_log_invalidates_the_aggregate(self):
        _, result = self.passed()
        group = self.aggregate_of(result['scientific'])['groups'][0]['evidence']
        log = self.root / json.loads((self.root / group['path']).read_text())['log']
        log.write_text(log.read_text() + 'tampered\n')
        with self.assertRaisesRegex(ValueError, 'log'):
            verify.load_evidence(self.root, result['scientific'])

    def test_resealed_aggregates_that_differ_from_the_configuration_are_refused(self):
        _, result = self.passed()
        original = self.aggregate_of(result['scientific'])
        reordered = dict(original, groups=list(reversed(original['groups'])))
        missing = dict(original, groups=original['groups'][:1])
        short = dict(original, commands=original['commands'][:-1])
        short['command_digest'] = digest(short['commands'])
        for forged, message in [(reordered, 'missing, reordered'), (missing, 'missing, reordered'),
                                (short, 'aggregate commands differ|stale')]:
            forged = dict(forged)
            forged['signature'] = verify.fingerprint(self.root, 'scientific', forged['commands'])
            with self.assertRaisesRegex(ValueError, message):
                verify.load_evidence(self.root, self.reseal(forged))

    def test_configuration_reorder_or_command_removal_invalidates_the_aggregate(self):
        _, result = self.passed()
        self.configure(list(reversed(GROUPS)))
        with self.assertRaises(ValueError):
            verify.load_evidence(self.root, result['scientific'])
        self.configure([GROUPS[0], {'name': 'beta', 'commands': []}][:1])
        with self.assertRaises(ValueError):
            verify.load_evidence(self.root, result['scientific'])

    def test_group_edit_of_the_command_list_invalidates_its_record(self):
        _, result = self.passed()
        edited = copy.deepcopy(GROUPS)
        edited[0]['commands'] = edited[0]['commands'][:1]
        self.configure(edited)
        with self.assertRaises(ValueError):
            verify.load_evidence(self.root, result['scientific'])

    def test_owner_mismatch_is_refused_and_groups_are_not_borrowed(self):
        theirs = verify.run(self.root, 'scientific', 'other')
        self.assertEqual(theirs['status'], 'EXECUTED PASS')
        verify.load_evidence(self.root, theirs['evidence'])
        mine = verify.run(self.root, 'scientific', 'arch')
        self.assertEqual({g['status'] for g in mine['groups']}, {'EXECUTED PASS'})
        forged = dict(self.aggregate_of(mine['evidence']))
        forged['groups'] = self.aggregate_of(theirs['evidence'])['groups']
        with self.assertRaisesRegex(ValueError, 'owned by other'):
            verify.load_evidence(self.root, self.reseal(forged))

    def test_failed_group_voids_the_receipt_and_the_aggregate_pointer(self):
        done, result = self.passed()
        pointer = verify.aggregate_pointer(self.root, project.config(self.root))
        self.assertTrue(pointer.exists() and self.current().exists())
        (self.root / 'results/fail_b').touch()
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            final_verification.run(self.root, done, 'arch', fresh=True, group='beta')
        self.assertFalse(pointer.exists() or self.current().exists())
        with self.assertRaisesRegex(ValueError, 'no current final verification receipt'):
            final_verification.check_receipt(self.root, done)
        # The second full run reuses nothing it should not: alpha reruns only with --fresh.
        (self.root / 'results/fail_b').unlink()
        again = final_verification.run(self.root, done, 'arch')
        self.assertEqual({g['name']: g['status'] for g in again['groups']},
                         {'alpha': 'REUSED EVIDENCE', 'beta': 'EXECUTED PASS'})

    def test_run_group_runs_exactly_one_group_and_seals_no_receipt(self):
        done = self.fixture.complete(qualify=False)
        result = final_verification.run(self.root, done, 'arch', group='beta')
        self.assertEqual((result['group'], result['status']), ('beta', 'EXECUTED PASS'))
        self.assertEqual((count(self.root, 'ran_a'), count(self.root, 'ran_b')), (0, 1))
        self.assertFalse(self.current().exists())
        self.assertEqual([r['status'] for r in result['groups']], ['missing', 'current'])
        self.assertIn('remaining groups: alpha', result['next'])
        again = final_verification.run(self.root, done, 'arch', group='beta')
        self.assertEqual(again['status'], 'REUSED EVIDENCE')
        self.assertEqual(count(self.root, 'ran_b'), 1)
        with self.assertRaisesRegex(ValueError, 'unknown scientific group'):
            final_verification.run(self.root, done, 'arch', group='gamma')
        # The remaining group, then the sealing run, which executes nothing.
        final_verification.run(self.root, done, 'arch', group='alpha')
        sealed = final_verification.run(self.root, done, 'arch')
        self.assertEqual(sealed['status'], 'REUSED EVIDENCE')
        self.assertEqual((count(self.root, 'ran_a'), count(self.root, 'ran_b')), (1, 1))
        final_verification.check_receipt(self.root, dict(done, verification=dict(
            done['verification'], scientific=sealed['scientific'], receipt=sealed['receipt'])))

    def test_group_flag_is_refused_for_a_single_suite_project(self):
        path = self.root / 'esx/project.json'
        cfg = json.loads(path.read_text())
        cfg['verification'].pop('scientific_groups')
        cfg['verification']['scientific'] = [['{python}', 'tests/check_diffusion.py']]
        atomic_json(path, cfg)
        with self.assertRaisesRegex(ValueError, 'configures scientific_groups'):
            verify.run(self.root, 'scientific', 'arch', group='alpha')

    def test_flat_scientific_run_of_a_grouped_project_cannot_bypass_groups(self):
        with self.assertRaisesRegex(ValueError, 'restricted to focused'):
            verify.run(self.root, 'scientific', 'arch', override=['true'])

    def test_reuse_does_not_double_count_accounting(self):
        verify.run(self.root, 'scientific', 'arch')
        events = lambda: [json.loads(line) for line in (self.root / STATE / 'phase_events.jsonl').read_text().splitlines()
                          if json.loads(line)['phase'] == 'verification']
        first = events()
        self.assertEqual(len(first), 2)
        self.assertGreater(sum(e['seconds'] for e in first), 1.0)
        # Drop the aggregate pointer so the second run goes through every group again.
        verify.aggregate_pointer(self.root, project.config(self.root)).unlink()
        again = verify.run(self.root, 'scientific', 'arch')
        self.assertEqual({g['status'] for g in again['groups']}, {'REUSED EVIDENCE'})
        added = events()[len(first):]
        self.assertLess(sum(e['seconds'] for e in added), 0.5)
        self.assertEqual(again['elapsed_seconds'], 0)


class HoldTests(GroupFixture):
    def test_next_and_stop_name_the_remaining_groups_between_groups(self):
        done = self.fixture.complete(qualify=False)
        self.assertEqual(final_verification.pending_notice(self.root), '')  # nothing started: no noise
        final_verification.run(self.root, done, 'arch', group='alpha')
        notice = final_verification.pending_notice(self.root)
        self.assertIn('not finished', notice)
        self.assertIn('current groups: alpha; remaining groups: beta', notice)
        self.assertIn('python3 tools/esx/final_verification.py run --review', notice)
        self.assertIn('--owner arch', notice)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.fixture.gate.next()
        self.assertIn('VERIFICATION: grouped scientific verification is incomplete', out.getvalue())
        self.assertIn('remaining groups: beta', ralph_stop.group_notice(self.root))
        final_verification.run(self.root, done, 'arch')  # completes: the notice disappears
        self.assertEqual(final_verification.pending_notice(self.root), '')
        self.assertEqual(ralph_stop.group_notice(self.root), '')

    def test_a_group_run_is_detected_as_running_verification(self):
        (self.root / 'tools/esx').mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'tools/esx/final_verification.py',
                                    'run', '--group', 'alpha'], cwd=self.root)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        deadline = time.monotonic() + 10
        found = []
        while not found and time.monotonic() < deadline:
            found = ralph_stop.verification_running(self.root)
            time.sleep(0.05)
        self.assertEqual([r['script'] for r in found], ['tools/esx/final_verification.py'])


if __name__ == '__main__':
    unittest.main()
