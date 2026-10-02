"""Exercise evidence provenance and reproducibility in disposable deployed projects."""
import contextlib
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
TOOLS = KIT / 'template/tools/esx'
sys.path.insert(0, str(TOOLS))
import issue_candidates as ic
import workflow_records as records
import doc_contract as dc
import doc_inventory as di
spec = importlib.util.spec_from_file_location('evidence_deploy', KIT / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='esx evidence ')
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name).resolve()
        self.root = self.parent / 'project with spaces'
        deploy.deploy(self.root, apply=True)
        example = KIT / 'examples/periodic_diffusion'
        for directory in ('src', 'tests'):
            shutil.copytree(example / directory, self.root / directory)
        for source, target in [('project.json', 'esx/project.json'),
                               ('project_profile.md', 'esx/project_profile.md'),
                               ('code_map.md', 'docs/code_map.md')]:
            shutil.copyfile(example / source, self.root / target)
        self.issue = 'SNAPSHOT-001'

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

class CandidateTests(DeploymentFixture):
    def capture(self, **kwargs):
        return ic.capture(self.root, self.issue, **kwargs)

    def test_untracked_bytes_survive_edits_and_extract_with_modes(self):
        script = self.write('tools/esx/run.sh', b'#!/bin/sh\necho original\n')
        script.chmod(0o751)
        before = self.capture()
        script.write_bytes(b'#!/bin/sh\necho changed\n')
        self.write('src/new.py', b'# Added witness\n')
        after = self.capture()
        result = ic.compare(self.root, before, after, self.issue)
        self.assertEqual([r['path'] for r in result['changes']], ['src/new.py', 'tools/esx/run.sh'])
        self.assertIn('echo original', result['diff'])
        self.assertIn('echo changed', result['diff'])
        dest = self.parent / 'scratch'
        ic.extract(self.root, before, self.issue, dest)
        self.assertEqual((dest / 'tools/esx/run.sh').read_bytes(), b'#!/bin/sh\necho original\n')
        self.assertEqual((dest / 'tools/esx/run.sh').stat().st_mode & 0o777, 0o751)
        self.assertFalse((dest / 'src/new.py').exists())

    def test_identical_capture_reuses_reference_and_tracks_mode_change(self):
        before = self.capture()
        self.assertEqual(before, self.capture())
        path = self.root / 'src/diffusion.py'
        path.chmod(path.stat().st_mode ^ 0o100)
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, before, self.issue)
        self.assertNotEqual(before, self.capture())

    def test_additions_and_deletions_invalidate_candidate(self):
        before = self.capture()
        self.write('tools/esx/witness.py', b'# Witness\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, before, self.issue)
        after = self.capture()
        (self.root / 'tools/esx/witness.py').unlink()
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, after, self.issue)
        self.assertTrue(ic.check_current(self.root, before, self.issue))

    def test_ignored_extra_input_is_preserved_and_measured(self):
        self.write('.gitignore', b'witness.bin\n')
        witness = self.write('witness.bin', b'\0\xfffinite inputs')
        normal = self.capture()
        explicit = self.capture(paths=['witness.bin'])
        self.assertNotIn('witness.bin', ic.load(self.root, normal, self.issue)['files'])
        self.assertIn('witness.bin', ic.load(self.root, explicit, self.issue)['files'])
        witness.write_bytes(b'\0new inputs')
        self.assertTrue(ic.check_current(self.root, normal, self.issue))
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, explicit, self.issue)

    def test_relative_symlink_round_trip_and_target_change(self):
        link = self.root / 'src/link.py'
        link.symlink_to('diffusion.py')
        before = self.capture()
        dest = self.parent / 'links'
        ic.extract(self.root, before, self.issue, dest)
        self.assertEqual(os.readlink(dest / 'src/link.py'), 'diffusion.py')
        self.assertEqual((dest / 'src/link.py').read_bytes(), (self.root / 'src/diffusion.py').read_bytes())
        link.unlink()
        link.symlink_to('../docs/code_map.md')
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, before, self.issue)

    def test_external_symlink_and_parent_symlink_are_rejected(self):
        link = self.root / 'src/external.py'
        link.symlink_to(self.parent / 'outside')
        with self.assertRaisesRegex(ValueError, 'symlink|leaves project'):
            self.capture()
        link.unlink()
        (self.root / 'shortcut').symlink_to('src', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink parent'):
            self.capture(paths=['shortcut/model.py'])

    def test_traversal_in_explicit_input_and_reference_are_rejected(self):
        for name in ('../outside', '/tmp/outside', 'src/../model.py', './src/diffusion.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.capture(paths=[name])
        ref = self.capture()
        ref['path'] = '../outside'
        with self.assertRaisesRegex(ValueError, 'reference'):
            ic.load(self.root, ref, self.issue)

    def test_manifest_and_blob_tampering_are_rejected(self):
        ref = self.capture()
        record = ic.load(self.root, ref, self.issue)
        data = record['files']['src/diffusion.py']
        blob = self.root / ic.STORE / 'blobs' / data['sha256']
        original = blob.read_bytes()
        blob.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'blob hash'):
            ic.load(self.root, ref, self.issue)
        blob.write_bytes(original)
        path = self.root / ref['path']
        record['issue_id'] = 'another issue'
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            ic.load(self.root, ref, self.issue)

    def test_blob_symlink_is_rejected_even_with_correct_bytes(self):
        ref = self.capture()
        record = ic.load(self.root, ref, self.issue)
        blob = self.root / ic.STORE / 'blobs' / record['files']['src/diffusion.py']['sha256']
        blob.unlink()
        blob.symlink_to(self.root / 'src/diffusion.py')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            ic.load(self.root, ref, self.issue)

    def test_extraction_cannot_overwrite_or_write_repository(self):
        ref = self.capture()
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            ic.extract(self.root, ref, self.issue, self.root / 'scratch')
        dest = self.parent / 'occupied'
        dest.mkdir()
        (dest / 'existing').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'empty directory'):
            ic.extract(self.root, ref, self.issue, dest)
        self.assertEqual((dest / 'existing').read_text(), 'preserve')
        alias = self.parent / 'alias'
        alias.symlink_to(dest, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            ic.extract(self.root, ref, self.issue, alias / 'child')

    def test_rehashed_manifest_cannot_create_traversal_or_link_parent(self):
        ref = self.capture()
        original = ic.load(self.root, ref, self.issue)
        for name, entry in [('src/../escape', {'kind': 'symlink', 'target': 'x'}),
                            ('src', {'kind': 'symlink', 'target': 'docs'}),
                            ('src/link.py', {'kind': 'symlink', 'target': '../../escape'})]:
            with self.subTest(name=name):
                record = json.loads(json.dumps(original))
                record['files'][name] = entry
                record['signature'] = ic.digest(record['files'])
                sha = ic.digest(record)
                bad_ref = {'path': f'{ic.STORE}/{sha}.json', 'sha256': sha}
                self.write(bad_ref['path'], json.dumps(record).encode())
                with self.assertRaises(ValueError):
                    ic.extract(self.root, bad_ref, self.issue, self.parent / 'scratch')

    def test_symlink_chain_escape_and_cycles_are_rejected(self):
        for files in [
            {'src/link': {'kind': 'symlink', 'target': 'dir/../../escape'},
             'src/dir': {'kind': 'symlink', 'target': '..'}},
            {'src/a': {'kind': 'symlink', 'target': 'b'},
             'src/b': {'kind': 'symlink', 'target': 'a'}},
        ]:
            with self.subTest(files=files), self.assertRaises(ValueError):
                ic.validate_links(files)

    def test_cli_check_fails_on_wrong_issue_and_changed_candidate(self):
        ref = self.capture()
        self.write('src/diffusion.py', b'# Changed\n')
        result = subprocess.run([sys.executable, '-B', str(TOOLS / 'issue_candidates.py'),
                                 '--root', str(self.root), 'check', '--issue', self.issue,
                                 '--candidate', json.dumps(ref)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('stale', result.stderr)
        with self.assertRaisesRegex(ValueError, 'identity'):
            ic.load(self.root, ref, 'another issue')



def start():
    return {'id': 'TEST-1', 'title': 'Bounded repair', 'timestamp': '2026-09-15T10:00:00Z',
            'workflow': {'final_verify_owner': 'arch'},
            'maintenance': {'baseline': {'path': 'base.json', 'sha256': 'a' * 64}},
            'agent_continuity': {'correction_round': 1, 'bob': {'agent_id': 'b1'}}}


def completion(role='richard', event='r-event', round_number=1):
    return {'agent_id': role + '-1', 'agent_type': role, 'event_id': event,
            'ts': '2026-09-15T10:15:00Z', 'footer': {
                'agent': role, 'issue_id': 'TEST-1', 'correction_round': round_number,
                'iteration_timestamp': start()['timestamp'],
                'skills_used': ['esx-common'],
                'orientation': {'path': 'orientation.json', 'sha256': 'b' * 64},
                'files_touched': [], 'candidate_signature': 'c' * 64,
                'verdict': 'REJECT', 'must_fix': ['Aliased output loses the previous value.'],
                'independent_check': {'cmd': 'python witness.py', 'exit': 1, 'executed': True},
                'documentation_review': {'status': 'pending', 'notes': 'A source correction is required.'}}}


def select(record):
    return {'agent': record['agent_type'], 'dispatch_id': record['agent_id'],
            'dispatch_event_id': record['event_id'],
            'correction_round': record['footer']['correction_round']}


class CompletionTests(unittest.TestCase):
    def test_exact_footer_is_preserved_and_no_success_is_invented(self):
        r = completion()
        original = deepcopy(r)
        d = records.prepare_done(start(), [r], [select(r)])
        imported = d['subagents']['richard'][0]
        for key, value in r['footer'].items():
            self.assertEqual(imported[key], value)
        self.assertIsNone(d['outcome'])
        self.assertIsNone(d['tests_status'])
        self.assertEqual(d['verification']['status'], 'pending')
        self.assertNotIn('ran', imported)
        self.assertEqual(r, original)
        self.assertEqual(json.loads(imported['report_digest']), r['footer'])

    def test_missing_footer_is_rejected(self):
        r = completion()
        chosen = select(r)
        r['footer'] = None
        with self.assertRaisesRegex(ValueError, 'missing structured footer'):
            records.prepare_done(start(), [r], [chosen])

    def test_identity_issue_role_and_round_must_all_match(self):
        for field, value in [('agent', 'bob'), ('issue_id', 'OTHER'), ('correction_round', 0)]:
            with self.subTest(field=field):
                r = completion()
                chosen = select(r)
                r['footer'][field] = value
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    records.prepare_done(start(), [r], [chosen])
        r = completion()
        chosen = select(r)
        chosen['dispatch_id'] = 'other-agent'
        with self.assertRaisesRegex(ValueError, 'identity/role mismatch'):
            records.prepare_done(start(), [r], [chosen])

    def test_unknown_and_duplicate_event_ids_are_rejected(self):
        r = completion()
        for logged in ([], [r, deepcopy(r)]):
            with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
                records.prepare_done(start(), logged, [select(r)])

    def test_stale_completion_requires_explicit_historical_provenance(self):
        r = completion()
        r['ts'] = '2026-09-14T10:00:00Z'
        with self.assertRaisesRegex(ValueError, 'predates this iteration'):
            records.prepare_done(start(), [r], [select(r)])

    def test_runtime_incomplete_and_failed_turns_are_not_imported(self):
        for status in ('incomplete', 'failed', 'running'):
            r = completion()
            r['status'] = status
            with self.assertRaisesRegex(ValueError, 'correction round mismatch or absent'):
                records.prepare_done(start(), [r], [select(r)])

    def test_incomplete_skill_fields_stay_pending_without_fabrication(self):
        r = completion(role='bob')
        r['footer'].pop('skills_used')
        r['footer'].pop('orientation')
        d = records.prepare_done(start(), [r], [select(r)])
        self.assertNotIn('skills_used', d['subagents']['bob'][0])
        self.assertIn('orientation', ' '.join(d['preparation']['pending']))

    def test_resumed_agent_completions_remain_distinct(self):
        r1, r2 = completion(event='r1', round_number=0), completion(event='r2')
        r1['ts'] = '2026-09-14T10:00:00Z'
        prior_start = start()
        prior_start['timestamp'] = '2026-09-14T09:00:00Z'
        r1['footer']['iteration_timestamp'] = prior_start['timestamp']
        prior = records.prepare_done(prior_start, [r1], [select(r1)])
        prior.update(outcome='partial', verification={'status': 'executed', 'result': 'PASS'})
        prior['subagents']['richard'][0]['report_digest'] = 'Measured earlier review. ' * 15
        d = records.prepare_done(start(), [r1, r2], [select(r2)], prior)
        self.assertEqual([r['dispatch_event_id'] for r in d['subagents']['richard']], ['r1', 'r2'])
        self.assertEqual(d['subagents']['richard'][0]['report_digest'],
                         prior['subagents']['richard'][0]['report_digest'])
        self.assertEqual(d['verification']['status'], 'pending')

    def test_historical_failed_turns_retain_only_exact_status_and_identity(self):
        for status in ('failed', 'incomplete'):
            with self.subTest(status=status):
                failed = {'agent_id': 'bob-1', 'agent_type': 'bob', 'event_id': 'failed-turn',
                          'issue_id': 'TEST-1', 'correction_round': 0, 'status': status,
                          'footer': {'issue_id': 'TEST-1', 'verdict': 'APPROVE'},
                          'ts': '2026-09-14T10:00:00Z'}
                entry = {'agent': 'bob', 'issue_id': 'TEST-1', 'correction_round': 0,
                         'dispatch_id': 'bob-1', 'dispatch_event_id': 'failed-turn', 'status': status}
                prior = {**start(), 'subagents': {'bob': [entry]}}
                final = completion(role='bob', event='successful-continuation')
                draft = records.prepare_done(start(), [failed, final], [select(final)], prior)
                self.assertEqual(draft['subagents']['bob'][0], dict(entry, attempt={'ts': failed['ts']}))
                self.assertNotIn('verdict', draft['subagents']['bob'][0])
                self.assertFalse(any(item.startswith('failed-turn:') for item in draft['preparation']['pending']))

    def test_historical_failure_cannot_borrow_issue_round_or_status(self):
        failed = {'agent_id': 'bob-1', 'agent_type': 'bob', 'event_id': 'failed-turn',
                  'issue_id': 'TEST-1', 'correction_round': 0, 'status': 'failed', 'footer': None}
        entry = {'agent': 'bob', 'dispatch_id': 'bob-1', 'dispatch_event_id': 'failed-turn',
                 'correction_round': 0, 'status': 'failed'}
        prior = {**start(), 'subagents': {'bob': [entry]}}
        for field, value in [('issue_id', 'OTHER'), ('correction_round', 1), ('status', 'incomplete')]:
            with self.subTest(field=field):
                tampered = {**failed, field: value}
                with self.assertRaises(ValueError):
                    records.prepare_done(start(), [tampered], [], prior)

    def test_tampered_historical_footer_and_replaced_baseline_are_rejected(self):
        r = completion()
        prior = records.prepare_done(start(), [r], [select(r)])
        prior['subagents']['richard'][0]['verdict'] = 'APPROVE'
        with self.assertRaisesRegex(ValueError, 'disagrees with captured verdict'):
            records.prepare_done(start(), [r], [], prior)
        prior = records.prepare_done(start(), [r], [select(r)])
        prior['maintenance']['baseline']['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'different issue baseline'):
            records.prepare_done(start(), [r], [], prior)

    def test_packet_keeps_all_current_blockers_and_precise_history_references(self):
        r1, r2 = completion(event='r1', round_number=0), completion(event='r2')
        r2['footer']['must_fix'] = ['Corner alias loss', 'Unknown boundary mode']
        history = [{'id': 'OTHER', 'summary': 'unrelated'},
                   {'id': 'TEST-1', 'timestamp': 'old', 'outcome': 'partial',
                    'summary': 'Long report ' * 1000, 'next_step': 'Bound the interface.'}]
        packet = records.continuation_packet(start(), history, [r1, r2])
        self.assertEqual(len(packet['latest_completions']), 1)
        self.assertEqual(packet['latest_completions'][0]['must_fix'], r2['footer']['must_fix'])
        self.assertEqual(packet['next_step'], 'Bound the interface.')
        self.assertNotIn('summary', packet)
        self.assertEqual(packet['history_refs'], [{'id': 'TEST-1', 'timestamp': 'old'}])

    def test_packet_keeps_replaced_agent_evidence_without_repeating_report_bodies(self):
        old, current = completion(event='old', round_number=0), completion(event='new')
        old['agent_id'] = 'replaced-reviewer'
        old['footer']['must_fix'] = ['Large earlier diagnosis ' * 1000]
        packet = records.continuation_packet(start(), [], [old, current])
        self.assertEqual(len(packet['latest_completions']), 1)
        self.assertEqual(packet['historical_completions'][0]['dispatch_event_id'], 'old')
        self.assertTrue(packet['historical_completions'][0]['had_blocking_findings'])
        self.assertNotIn('Large earlier diagnosis', json.dumps(packet))


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_buried_milestone_survives_unrelated_appends(self):
        status = self.root / 'current_status.md'
        status.write_text('# Status\n## 2026-09-14 Completed harness\nCaptured TEST-1 evidence.\n'
                          '## Later events\n' + 'more work\n' * 100)
        ref = records.milestone_reference(self.root, 'current_status.md', '2026-09-14 Completed harness')
        done = {'milestone': {'logged': True, 'reference': ref}}
        self.assertEqual(records.check_milestone(self.root, done), [])
        status.write_text(status.read_text() + 'An unrelated event\n')
        self.assertEqual(records.check_milestone(self.root, done), [])
        status.write_text(status.read_text().replace('Captured TEST-1', 'Changed TEST-1'))
        self.assertIn('hash mismatch', records.check_milestone(self.root, done)[0])

    def test_repeated_headings_require_explicit_occurrence(self):
        (self.root / 'current_status.md').write_text('# Status\n## Result\nfirst\n## Result\nsecond\n')
        with self.assertRaisesRegex(ValueError, 'unique'):
            records.milestone_reference(self.root, 'current_status.md', 'Result')
        ref = records.milestone_reference(self.root, 'current_status.md', 'Result', 2)
        self.assertEqual(records.check_milestone(self.root, {'milestone': {'logged': True, **ref}}), [])
        with self.assertRaisesRegex(ValueError, 'occurrence'):
            records.milestone_reference(self.root, 'current_status.md', 'Result', 3)

    def test_headings_inside_fences_are_ignored_and_children_are_hashed(self):
        status = self.root / 'current_status.md'
        status.write_text('# Status\n```md\n## Result\n```\n## Result\n### Evidence\nactual\n## End\n')
        ref = records.milestone_reference(self.root, 'current_status.md', 'Result')
        self.assertEqual(records.check_milestone(self.root, {'milestone': {'logged': True, **ref}}), [])
        status.write_text(status.read_text().replace('actual', 'changed'))
        self.assertTrue(records.check_milestone(self.root, {'milestone': {'logged': True, **ref}}))

    def test_malformed_explicit_reference_cannot_fall_back_to_today(self):
        (self.root / 'current_status.md').write_text('2026-09-15\n')
        done = {'milestone': {'logged': True, 'reference': {'path': 'current_status.md'}}}
        self.assertTrue(records.check_milestone(self.root, done, '2026-09-15'))
        done['milestone']['reference'] = None
        self.assertTrue(records.check_milestone(self.root, done))

    def test_legacy_milestone_can_be_explicitly_disabled(self):
        (self.root / 'current_status.md').write_text('## 2026-09-15 A result\n')
        done = {'milestone': {'logged': True}}
        self.assertEqual(records.check_milestone(self.root, done, '2026-09-15'), [])
        self.assertTrue(records.check_milestone(self.root, done, allow_legacy=False))
        self.assertTrue(records.check_milestone(self.root, done, '2026-09-16'))

    def test_output_rejects_existing_inputs_active_state_and_escape(self):
        (self.root / 'input.json').write_text('{"original":true}')
        for name in ('input.json', '../escape.json', '/tmp/escape.json',
                     '.git/object.json', f'{records.STATE}/issue-start.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                records.write_output(self.root, name, {'new': True}, [self.root / 'input.json'])
        self.assertEqual(json.loads((self.root / 'input.json').read_text()), {'original': True})
        records.write_output(self.root, f'{records.STATE}/done-draft.json', {'draft': True})
        self.assertTrue((self.root / records.STATE / 'done-draft.json').exists())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            records.write_output(self.root, f'{records.STATE}/done-draft.json', {})

    def test_output_and_evidence_reject_symlink_parents(self):
        real = self.root / 'real'
        real.mkdir()
        (self.root / 'linked').symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            records.write_output(self.root, 'linked/file.json', {})
        with self.assertRaisesRegex(ValueError, 'symlink'):
            records.evidence_reference(self.root, 'linked/file.json')

    def test_cli_default_has_no_side_effect_and_explicit_draft_is_create_only(self):
        state = self.root / records.STATE
        state.mkdir(parents=True)
        r = completion()
        (state / 'issue-start.json').write_text(json.dumps(start()))
        (state / 'dispatch_log.jsonl').write_text(json.dumps(r) + '\n')
        (self.root / 'selection.json').write_text(json.dumps([select(r)]))
        args = ['--root', str(self.root), 'prepare-done', '--select', 'selection.json']
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(records.main(args), 0)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertEqual(json.loads(out.getvalue())['preparation']['status'], 'draft')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(records.main(args + ['--output', 'draft.json']), 0)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(records.main(args + ['--output', 'draft.json']), 1)

    def test_malformed_evidence_log_fails_visibly(self):
        log = self.root / 'log.jsonl'
        log.write_text('{"event_id":"first"}\n{"truncated":\n')
        with self.assertRaisesRegex(ValueError, ':2: malformed'):
            records.read_jsonl(log)

    def test_diagnosis_requires_observed_evidence_and_bounded_agreement(self):
        witness = self.root / 'witness.txt'
        witness.write_text('The original source produces a bounds violation.\n')
        checkpoint = {'issue_id': 'TEST-1', 'after_round': 2, 'status': 'agreed',
                      'premise': 'The original forward source was assumed to have valid array bounds.',
                      'next_change': 'Replace the witness with a source having checked valid bounds.',
                      'acceptance': 'A forward bounds check and the revised focused derivative oracle pass.',
                      'decision': 'revise_design',
                      'reproduction': {'cmd': './witness', 'executed': True, 'exit': 1,
                                       'result': 'The forward program raises a bounds error.'},
                      'evidence_refs': [records.evidence_reference(self.root, 'witness.txt')]}
        self.assertEqual(records.validate_checkpoint(self.root, checkpoint, 'TEST-1', 2), [])
        for key, value in [('premise', ''), ('after_round', 1), ('status', 'pending'),
                           ('evidence_refs', []), ('reproduction', {'cmd': 'not run'})]:
            invalid = {**checkpoint, key: value}
            with self.subTest(key=key):
                self.assertTrue(records.validate_checkpoint(self.root, invalid, 'TEST-1', 2))
        witness.write_text('The evidence has changed.\n')
        self.assertTrue(records.validate_checkpoint(self.root, checkpoint, 'TEST-1', 2))


class TimingTests(unittest.TestCase):
    def test_parallel_review_union_and_unknown_legacy_start(self):
        r1, r2, old = completion(event='r1'), completion(event='r2'), completion(role='bob', event='old')
        r1.update(started_at='2026-09-15T10:00:00Z', finished_at='2026-09-15T10:10:00Z',
                  duration_seconds=600.2)
        r2.update(started_at='2026-09-15T10:05:00Z', finished_at='2026-09-15T10:15:00Z',
                  duration_seconds=600.3)
        summary = records.summarize_timings([r1, r2, old], 'TEST-1')
        self.assertEqual(summary['observed_elapsed_seconds'], 900)
        self.assertEqual(summary['by_role']['richard']['measured_seconds'], 1200.5)
        self.assertEqual(summary['by_role']['bob']['unmeasured_turns'], 1)
        self.assertIsNone(summary['turns'][-1]['seconds'])

    def test_negative_spans_and_duplicate_events_are_errors(self):
        r = completion()
        r.update(started_at='2026-09-15T11:00:00Z', finished_at='2026-09-15T10:00:00Z')
        with self.assertRaisesRegex(ValueError, 'finish predates start'):
            records.summarize_timings([r])
        r = completion()
        with self.assertRaisesRegex(ValueError, 'unique completion'):
            records.summarize_timings([r, r])


class CorrectionTests(unittest.TestCase):
    def partial(self, number, verdict='REJECT'):
        return {'id': 'TEST-1', 'outcome': 'partial',
                'agent_continuity': {'correction_round': number},
                'subagents': {'richard': [{'correction_round': number, 'verdict': verdict,
                                          'must_fix': []}]}}

    def test_initial_round_and_duplicate_history_do_not_inflate_failures(self):
        history = [self.partial(0), self.partial(1), self.partial(1), self.partial(2)]
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), [1, 2])
        self.assertEqual(records.unsuccessful_corrections(history, 'TEST-1'), 2)

    def test_another_issue_does_not_erase_the_streak_but_success_does(self):
        history = [self.partial(1), {'id': 'OTHER', 'outcome': 'completed'}, self.partial(2)]
        self.assertEqual(records.unsuccessful_corrections(history, 'TEST-1'), 2)
        history.append(self.partial(3, 'APPROVE'))
        self.assertEqual(records.unsuccessful_corrections(history, 'TEST-1'), 0)
        history.append(self.partial(4))
        self.assertEqual(records.unsuccessful_corrections(history, 'TEST-1'), 1)

    def test_old_review_is_history_and_build_failure_is_a_failed_correction(self):
        current = self.partial(2, 'APPROVE')
        current['subagents']['richard'].insert(0, self.partial(1)['subagents']['richard'][0])
        self.assertEqual(records.unsuccessful_corrections([self.partial(1), current], 'TEST-1'), 0)
        current['tests_status'] = 'failing'
        self.assertEqual(records.unsuccessful_corrections([self.partial(1), current], 'TEST-1'), 2)

    def test_completed_issue_and_resolved_scope_do_not_count_as_failures(self):
        current = self.partial(2, 'APPROVE')
        current['scope_decisions'] = [{'classification': 'dependency', 'status': 'resolved'}]
        self.assertEqual(records.unsuccessful_corrections([self.partial(1), current], 'TEST-1'), 0)
        current['scope_decisions'][0]['status'] = 'open'
        self.assertEqual(records.unsuccessful_corrections([self.partial(1), current], 'TEST-1'), 2)
        current['outcome'] = 'completed'
        self.assertEqual(records.unsuccessful_corrections([self.partial(1), current], 'TEST-1'), 0)

    def test_esx_list_assignments_without_round_metadata_are_safe(self):
        history = [{'id': 'TEST-1', 'outcome': 'partial',
                    'agent_continuity': {'richard': ['reviewer-id']}, 'subagents': {}}]
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), [])

    def test_explicit_legacy_reviewer_round_count_survives_upgrade(self):
        history = [{'id': 'TEST-1', 'outcome': 'partial',
                    'agent_continuity': {'richard': {'rounds': n}},
                    'subagents': {'richard': [{'verdict': 'REJECT'}]}} for n in range(1, 8)]
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), list(range(1, 8)))

    def test_recorded_checkpoint_resets_count_without_erasing_new_failures(self):
        history = [self.partial(1), self.partial(2), self.partial(3)]
        history[-1]['diagnosis_checkpoint'] = {
            'issue_id': 'TEST-1', 'status': 'agreed', 'after_round': 2}
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), [3])
        history.append(self.partial(4))
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), [3, 4])
        history[-1]['diagnosis_checkpoint'] = {
            'issue_id': 'TEST-1', 'status': 'agreed', 'after_round': 900}
        self.assertEqual(records.rejected_correction_rounds(history, 'TEST-1'), [3, 4])



class BaselineTests(DeploymentFixture):
    def setUp(self):
        super().setUp()
        self.model = self.write('src/model.py', b'"""Scalar update and its dependent mapping."""\nFACTOR = 1\ndef step(x):\n    """Scale a scalar tracer by the configured factor."""\n    return FACTOR*x\ndef consumer(x):\n    """Apply the scalar tracer update."""\n    return step(x)\n')

    def nav(self, baseline):
        with redirect_stderr(io.StringIO()):
            return dc.navigate(self.root, self.issue, baseline, 'arch', 'docs/code_map.md#pipeline',
                ['src/model.py::step', 'src/model.py::consumer'], ['docs/model_contract.md'],
                'Inspect the scalar owner, its consumer and the configured scientific contract before editing.')

    def changed_plan(self, baseline, dependencies=True):
        self.model.write_text(self.model.read_text().replace('return FACTOR*x', 'return FACTOR*x*2'))
        plan = dc.draft(self.root, self.issue, baseline)
        for row in plan['dispositions']:
            row.update(action='reviewed_unchanged', reason='The scalar interface and ownership remain accurately described by the inspected declaration.',
                       references=[row['target']])
            if dependencies:
                row['dependencies'] = ['src/model.py::consumer']
        plan['map_delta'] = {'status': 'MAP-OK', 'reason': 'The mapped source and its scientific acceptance routes remain accurate for this local scalar edit.',
                             'references': ['docs/code_map.md#pipeline']}
        return plan

    def test_baseline_is_pinned_and_contains_original_bytes_without_git(self):
        base = dc.baseline(self.root, self.issue)
        original = self.model.read_bytes()
        self.model.write_text(self.model.read_text()+'# New working change\n')
        self.assertEqual(base, dc.baseline(self.root, self.issue))
        payload = dc.load(self.root, base, 'baseline', self.issue)
        candidate = ic.load(self.root, payload['source_snapshot'], self.issue)
        self.assertEqual(ic.blob(self.root, candidate['files']['src/model.py']['sha256']), original)
        self.assertTrue(dc.draft(self.root, self.issue, base)['changes'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            dc.baseline(self.root, self.issue, 'HEAD', 'A requested recovery must preserve the original immutable issue evidence.')

    def test_earliest_metadata_history_is_adopted_without_inventing_bytes(self):
        old = dc.envelope('baseline', self.issue)
        old.update(files=di.snapshot(self.root), recovery={})
        ref = dc.save(self.root, old)
        self.model.write_text(self.model.read_text()+'# A later change\n')
        later = dc.save(self.root, {**old, 'files': di.snapshot(self.root)})
        self.write(f'{records.STATE}/loop_history.jsonl', ('\n'.join(json.dumps({'id': self.issue,
            'maintenance': {'baseline': value}}) for value in (ref, later))+'\n').encode())
        self.assertEqual(dc.baseline(self.root, self.issue), ref)
        self.assertNotIn('source_snapshot', dc.load(self.root, ref, 'baseline', self.issue))

    def test_partial_round_and_new_start_cannot_reset_original(self):
        base = dc.baseline(self.root, self.issue)
        start = {'id': self.issue, 'maintenance': {'baseline': base, 'orientation': self.nav(base)}}
        self.model.write_text(self.model.read_text()+'# Round one implementation\n')
        changed = dc.save(self.root, {**dc.envelope('baseline', self.issue), 'files': di.snapshot(self.root)})
        alternate = {'id': self.issue, 'maintenance': {'baseline': changed, 'orientation': self.nav(changed)}}
        self.assertIn('original maintenance baseline', ' '.join(dc.check_start(self.root, alternate)))
        done = {'id': self.issue, 'outcome': 'partial', 'maintenance': {'baseline': changed}}
        self.assertIn('original maintenance baseline', ' '.join(dc.check_done(self.root, start, done, [], 'a'*64)))

    def test_sealed_dependency_slice_survives_unrelated_new_test(self):
        base = dc.baseline(self.root, self.issue)
        report = dc.seal(self.root, self.changed_plan(base))
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        draft = dc.draft(self.root, self.issue, base, report)
        rows = {r['target']:r for r in draft['dispositions']}
        self.assertEqual(rows['src/model.py::step']['reused_from'], report)
        self.assertEqual(rows['tests/new_oracle.py::<module>']['action'], '')
        self.assertEqual(draft['map_delta']['status'], '')

    MAP_OK = {'status': 'MAP-OK', 'references': ['docs/code_map.md#pipeline'],
              'reason': 'The mapped source and its scientific acceptance routes remain accurate for this local scalar edit.'}

    def updated_plan(self, baseline, doc_dependencies=()):
        """A code unit and a document both edited, each with a real documentation change."""
        self.model.write_text(self.model.read_text().replace(
            '"""Scale a scalar tracer by the configured factor."""\n    return FACTOR*x',
            '"""Scale a scalar tracer by twice the configured factor."""\n    return FACTOR*x*2'))
        contract = self.root / 'docs/model_contract.md'
        contract.write_text(contract.read_text() + '\nThe scalar update doubles the configured factor.\n')
        plan = dc.draft(self.root, self.issue, baseline)
        for row in plan['dispositions']:
            code = row['target'] == 'src/model.py::step'
            document = row['target'].startswith('docs/model_contract.md')
            row.update(action='updated' if code or document else 'reviewed_unchanged', references=[row['target']],
                       reason='The description states the doubled scalar factor that the changed update now applies.')
            if document and doc_dependencies:
                row['dependencies'] = list(doc_dependencies)
        plan['map_delta'] = dict(self.MAP_OK)
        return plan

    def test_updated_code_judgment_is_bound_to_its_own_file_and_cited_references(self):
        """A change in another file keeps it; a sibling edit in the same file does not."""
        base = dc.baseline(self.root, self.issue)
        report = dc.seal(self.root, self.updated_plan(base))
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        draft = dc.draft(self.root, self.issue, base, report)
        rows = {r['target']: r for r in draft['dispositions']}
        self.assertEqual(rows['src/model.py::step']['reused_from'], report)
        self.assertEqual(draft['reused'], 1)
        # The carried judgment seals again against the new candidate once the rest is judged.
        for row in draft['dispositions']:
            if not row.get('reused_from'):
                document = row['target'].startswith('docs/model_contract.md')
                row.update(action='updated' if document else 'reviewed_unchanged', references=[row['target']],
                           reason='The description states the doubled scalar factor that the changed update now applies.')
        draft['map_delta'] = dict(self.MAP_OK)
        dc.seal(self.root, draft)
        self.model.write_text(self.model.read_text().replace('return step(x)', 'return step(x)+1'))
        again = dc.draft(self.root, self.issue, base, report)
        self.assertEqual(again['reused'], 0)

    def test_judgments_about_other_files_never_carry_forward_undeclared(self):
        """reviewed_unchanged and document judgments keep the whole-inventory rule."""
        base = dc.baseline(self.root, self.issue)
        plan = self.updated_plan(base)
        targets = {r['target']: r['action'] for r in plan['dispositions']}
        self.assertIn('docs/model_contract.md::<module>', targets)
        report = dc.seal(self.root, plan)
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        rows = {r['target']: r for r in dc.draft(self.root, self.issue, base, report)['dispositions']}
        self.assertEqual(rows['docs/model_contract.md::<module>']['action'], '')
        for target, action in targets.items():
            if action == 'reviewed_unchanged':
                self.assertEqual(rows[target]['action'], '', target)
        self.assertFalse(dc.file_bound({'target': 'src/model.py::step', 'action': 'reviewed_unchanged'}))
        self.assertFalse(dc.file_bound({'target': 'docs/model_contract.md::<module>', 'action': 'updated'}))
        self.assertFalse(dc.file_bound({'target': 'esx/project.json::<module>', 'action': 'updated'}))
        self.assertTrue(dc.file_bound({'target': 'src/model.py::step', 'action': 'updated'}))
        self.assertTrue(dc.file_bound({'target': 'src/solver.F90::<module>', 'action': 'removed'}))

    def test_reviewed_unchanged_without_dependencies_is_blanked_by_any_change_elsewhere(self):
        base = dc.baseline(self.root, self.issue)
        plan = self.changed_plan(base, dependencies=False)
        self.assertTrue(all(row['action'] == 'reviewed_unchanged' for row in plan['dispositions']))
        report = dc.seal(self.root, plan)
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        draft = dc.draft(self.root, self.issue, base, report)
        self.assertTrue(all(row['action'] == '' for row in draft['dispositions']))
        self.assertEqual(draft['reused'], 0)

    def test_document_judgment_with_a_declared_code_dependency_is_reused_while_that_code_is_unchanged(self):
        base = dc.baseline(self.root, self.issue)
        report = dc.seal(self.root, self.updated_plan(base, doc_dependencies=['src/model.py::step']))
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        rows = {r['target']: r for r in dc.draft(self.root, self.issue, base, report)['dispositions']}
        self.assertEqual(rows['docs/model_contract.md::<module>']['reused_from'], report)
        self.model.write_text(self.model.read_text().replace('return FACTOR*x*2', 'return FACTOR*x*3'))
        rows = {r['target']: r for r in dc.draft(self.root, self.issue, base, report)['dispositions']}
        self.assertEqual(rows['docs/model_contract.md::<module>']['action'], '')

    def test_report_sealed_before_file_state_was_measured_keeps_the_whole_inventory_rule(self):
        base = dc.baseline(self.root, self.issue)
        ref = dc.seal(self.root, self.updated_plan(base))
        old = dc.load(self.root, ref, 'documentation', self.issue)
        for row in old['dispositions']:
            row['judgment_inputs'].pop('file_sha256')
        legacy = dc.save(self.root, old)
        dc.validate_report(self.root, dc.load(self.root, legacy, 'documentation', self.issue), self.issue, base)
        self.write('tests/new_oracle.py', b'"""Additional independent test oracle."""\n')
        draft = dc.draft(self.root, self.issue, base, legacy)
        self.assertEqual(draft['reused'], 0)

    def test_module_context_and_referenced_dependency_invalidate_reuse(self):
        for change in [('FACTOR = 1', 'FACTOR = 3'), ('return step(x)', 'return step(x)+1')]:
            with self.subTest(change=change):
                base = dc.baseline(self.root, self.issue)
                report = dc.seal(self.root, self.changed_plan(base))
                before = self.model.read_text()
                self.model.write_text(before.replace(*change))
                draft = dc.draft(self.root, self.issue, base, report)
                row = next(r for r in draft['dispositions'] if r['target'] == 'src/model.py::step')
                self.assertEqual(row['action'], '')
                self.model.write_text(before)

    def test_unsealed_report_and_modified_reused_explanation_are_rejected(self):
        base = dc.baseline(self.root, self.issue)
        plan = self.changed_plan(base)
        unsealed = dc.save(self.root, plan)
        with self.assertRaisesRegex(ValueError, 'sealed'):
            dc.draft(self.root, self.issue, base, unsealed)
        sealed = dc.seal(self.root, plan)
        reused = dc.draft(self.root, self.issue, base, sealed)
        reused['dispositions'][0]['reason'] = 'A substituted explanation must receive an explicit fresh review before it can supply evidence.'
        with self.assertRaisesRegex(ValueError, 'reused judgment text differs'):
            dc.seal(self.root, reused)

    def test_maintenance_store_cannot_follow_symlink_parent(self):
        store = self.root / records.STATE
        store.mkdir(parents=True, exist_ok=True)
        (self.root/'linked').mkdir()
        (store/'maintenance').symlink_to(self.root/'linked', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            dc.baseline(self.root, self.issue)


class AdditionalEvidenceTests(DeploymentFixture):
    def test_configured_untracked_and_ignored_source_are_kept_outputs_are_excluded(self):
        self.write('.gitignore', b'src/ignored.py\nresults/\n')
        self.write('src/ignored.py', b'"""Configured source remains evidence even if ignored by Git."""\n')
        self.write('results/output.txt', b'Excluded generated output\n')
        ref = ic.capture(self.root, self.issue)
        files = ic.load(self.root, ref, self.issue)['files']
        self.assertIn('src/ignored.py', files)
        self.assertNotIn('results/output.txt', files)
        explicit = ic.capture(self.root, self.issue, paths=['results/output.txt'])
        self.assertIn('results/output.txt', ic.load(self.root, explicit, self.issue)['files'])

    def test_symlink_destination_bytes_are_retained_even_outside_configured_roots(self):
        target = self.write('results/lookup.bin', b'physical input value')
        link = self.root / 'src/lookup.bin'
        link.symlink_to('../results/lookup.bin')
        ref = ic.capture(self.root, self.issue)
        ic.extract(self.root, ref, self.issue, self.parent/'extracted')
        self.assertEqual((self.parent/'extracted/src/lookup.bin').read_bytes(), b'physical input value')
        target.write_bytes(b'changed physical input')
        with self.assertRaisesRegex(ValueError, 'stale'):
            ic.check_current(self.root, ref, self.issue)

    def test_failed_footerless_dispatch_remains_visible_in_handoff(self):
        failed = {'issue_id':'TEST-1', 'agent_type':'bob', 'agent_id':'bob-1', 'event_id':'failed-turn',
                  'correction_round':1, 'status':'failed', 'footer':None}
        packet = records.continuation_packet(start(), [], [failed])
        self.assertEqual(packet['latest_completions'][0]['status'], 'failed')
        self.assertEqual(packet['latest_completions'][0]['dispatch_event_id'], 'failed-turn')

    def test_prepare_done_preserves_esx_iteration_identity(self):
        event = completion()
        draft = records.prepare_done(start(), [event], [select(event)])
        self.assertEqual(draft['timestamp'], start()['timestamp'])
        self.assertEqual(draft['communication']['status'], 'pending')
        self.assertEqual(draft['verification']['final_owner'], 'arch')
        event['footer']['iteration_timestamp'] = '2026-09-15T09:00:00Z'
        with self.assertRaisesRegex(ValueError, 'another iteration'):
            records.prepare_done(start(), [event], [select(event)])


if __name__ == "__main__":
    unittest.main()
