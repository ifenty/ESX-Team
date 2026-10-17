"""1.6.5: signal handlers before the child starts, clearer pause and refusal messages, owner reported with
staleness, provider limits on any unfinished turn, bare small figures, the local permission file outside the
acceptance signature, and early help for stale evidence. Offline, synthetic deployment fixtures."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_framework
from test_framework import KIT
from test_limits_and_footers import LIMIT, USER, say, Transcripts
from test_loop_drain_cadence import LoopFixture
import doc_contract
import footer_contract
import hooks
import loop_control
import project
import ralph_stop
import verify

TOOLS = KIT / 'template/tools/esx'

# A runner that executes a focused verification. With "window" it delivers SIGTERM to itself right after the
# child process is created, the interval in which the handlers used to be missing.
RUNNER = '''
import os, signal, subprocess, sys
from pathlib import Path
sys.path.insert(0, %(tools)r)
import verify
if sys.argv[3] == "window":
    # A signal arrives 0.2 s after the child is created. Handlers installed after the child starts would
    # be reached only after the first signal.signal call, which is held up here for 0.6 s.
    import threading, time
    state = {"child": False, "slept": False}
    real_popen, real_signal = subprocess.Popen, signal.signal
    def popen(*a, **k):
        child = real_popen(*a, **k)
        if "time.sleep(60)" not in " ".join(map(str, a[0])):
            return child  # fingerprint probes and the like
        state["child"] = True
        threading.Thread(target=lambda: (time.sleep(0.2), os.kill(os.getpid(), signal.SIGTERM))).start()
        return child
    def hold(*a, **k):
        if state["child"] and not state["slept"]:
            state["slept"] = True
            time.sleep(0.6)
        return real_signal(*a, **k)
    subprocess.Popen, signal.signal = popen, hold
try:
    verify.run(Path(sys.argv[1]), "focused", "runner", fresh=True,
               override=["{python}", "-c", "import os, time; "
                         "open(os.environ.get('PIDFILE', os.devnull), 'w').write(str(os.getpid())); time.sleep(60)"])
except InterruptedError as exc:
    print("INTERRUPTED", exc)
    sys.exit(0)
print("NOT INTERRUPTED")
sys.exit(3)
'''


class SignalBeforePopenTests(LoopFixture):
    def runner(self):
        path = Path(tempfile.mkdtemp()) / 'runner.py'
        path.write_text(RUNNER % {'tools': str(TOOLS)})
        return path

    def records(self):
        folder = self.root / project.STATE / 'verification'
        found = [json.loads(p.read_text()) for p in folder.glob('*.json')
                 if len(p.stem) == 64] if folder.is_dir() else []
        return [r for r in found if r.get('owner') == 'runner']

    def wait(self, process, deadline=60):
        try:
            return process.communicate(timeout=deadline)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            self.fail('runner did not finish within the deadline')

    def test_a_signal_right_after_the_child_starts_leaves_an_interrupted_record(self):
        runner = self.runner()
        for attempt in range(1, 5):
            process = subprocess.Popen([sys.executable, '-B', str(runner), str(self.root), '-', 'window'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = self.wait(process)
            self.assertEqual(process.returncode, 0, out + err)
            self.assertIn('INTERRUPTED', out)
            self.assertEqual(len(self.records()), attempt)
            self.assertEqual({r['exit'] for r in self.records()}, {130})

    def test_a_signal_while_the_command_runs_leaves_an_interrupted_record(self):
        runner = self.runner()
        for attempt in range(1, 4):
            pid_file = self.root / f'child{attempt}.pid'
            process = subprocess.Popen([sys.executable, '-B', str(runner), str(self.root), '-', 'plain'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       env=dict(os.environ, PIDFILE=str(pid_file)))
            deadline = time.monotonic() + 30
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(pid_file.exists(), 'the command never started')
            process.send_signal(signal.SIGTERM)
            out, err = self.wait(process)
            self.assertEqual(process.returncode, 0, out + err)
            self.assertEqual(len(self.records()), attempt)
        self.assertEqual({r['exit'] for r in self.records()}, {130})


class PauseMessageTests(LoopFixture, Transcripts):
    def write(self, *records):
        return Transcripts.write(self, *records)

    def test_a_provider_pause_says_it_resumes_by_itself(self):
        self.begin_issue()
        message = self.stop(transcript_path=self.write(USER, LIMIT))['systemMessage']
        self.assertIn('usage limit resets', message)
        self.assertIn('resumes by itself', message)
        self.assertIn('/esx-loop', message)
        self.assertNotIn('until /esx-loop resumes it', message)

    def test_an_owner_pause_message_is_unchanged(self):
        self.begin_issue()
        loop_control.pause(self.root, 'owner wants a break')
        message = self.stop(transcript_path=self.write(USER, say('working')))['systemMessage']
        self.assertIn('until /esx-loop resumes it', message)


class MistypedReferenceTests(LoopFixture):
    def test_verification_evidence_names_both_hashes(self):
        self.begin_issue()
        ref = verify.run(self.root, 'focused', 'r1', fresh=True)['evidence']
        other = '5' * 64 if ref['sha256'][0] != '5' else '4' * 64
        with self.assertRaises(ValueError) as caught:
            verify.load_evidence(self.root, dict(ref, sha256=other))
        text = str(caught.exception)
        self.assertIn('invalid verification artifact path', text)
        self.assertIn(f'the path names {ref["sha256"]} but sha256 is {other}', text)

    def test_documentation_reference_names_both_hashes(self):
        a, b = 'a' * 64, 'b' * 64
        ref = {'path': f'{doc_contract.STORE}/{a}.json', 'sha256': b}
        with self.assertRaises(ValueError) as caught:
            doc_contract.load(self.root, ref, 'documentation', 'SAMPLE-001')
        self.assertIn('content-addressed maintenance artifact', str(caught.exception))
        self.assertIn(f'the path names {a} but sha256 is {b}', str(caught.exception))

    def test_the_agent_stop_surfaces_both_hashes(self):
        start = self.begin_issue()
        a, b = 'a' * 64, 'b' * 64
        footer = {'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                  'correction_round': 0, 'verdict': 'REJECT', 'must_fix': ['x'],
                  'orientation': {'path': f'{doc_contract.STORE}/{a}.json', 'sha256': b}}
        errors = footer_contract.reference_errors(self.root, 'richard', footer, start, 'r1')
        self.assertTrue(any(f'the path names {a} but sha256 is {b}' in e for e in errors), errors)


class OwnerWithStalenessTests(LoopFixture):
    def edit_source(self):
        path = self.root / 'src/diffusion.py'
        path.write_text(path.read_text() + '\n# edited after sealing\n')

    def footer(self, start, evidence):
        return {'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                'correction_round': 0, 'verdict': 'APPROVE', 'must_fix': [],
                'independent_check': {'evidence': evidence}}

    def test_stale_evidence_of_another_agent_reports_both(self):
        start = self.begin_issue()
        evidence = verify.run(self.root, 'focused', 'someone-else', fresh=True)['evidence']
        self.edit_source()
        errors = footer_contract.reference_errors(self.root, 'richard', self.footer(start, evidence), start, 'r1')
        self.assertTrue(any('verification evidence is stale' in e for e in errors), errors)
        self.assertTrue(any('owned by someone-else, not by the reporting agent r1' in e for e in errors), errors)

    def test_stale_evidence_of_the_reporter_reports_only_staleness(self):
        start = self.begin_issue()
        evidence = verify.run(self.root, 'focused', 'r1', fresh=True)['evidence']
        self.edit_source()
        errors = footer_contract.reference_errors(self.root, 'richard', self.footer(start, evidence), start, 'r1')
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('stale', errors[0])


class PartialFooterLimitTests(LoopFixture, Transcripts):
    def write(self, *records):
        return Transcripts.write(self, *records)

    def test_a_partial_footer_followed_by_the_limit_record_is_a_provider_limit(self):
        start = self.begin_issue()
        partial = '```json\n' + json.dumps({'agent': 'bob', 'issue_id': start['id']}) + '\n```'
        record = hooks.capture(self.root, {'agent_type': 'bob', 'agent_id': 'b1', 'session_id': 's',
                                           'last_assistant_message': partial,
                                           'agent_transcript_path': self.write(USER, say(partial), LIMIT)})
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['provider_limit'], {'limit_type': None, 'reset_at': None})
        self.assertEqual(loop_control.status(self.root)['pause_source'], 'provider_limit')


class BareFigureTests(LoopFixture):
    def test_a_bare_small_figure_warns_and_prose_figures_do_not(self):
        (self.root / 'docs/notes.md').write_text('There are 46 rules.\nnamelist value 46 here\n')
        bare = doc_contract.stale_lines(self.root, [{'old': '46', 'new': '', 'note': ''}])
        self.assertEqual(len(bare['warnings']), 1)
        self.assertIn("'46'", bare['warnings'][0])
        self.assertGreaterEqual(bare['lines'], 2)  # existing hits are still found
        prose = doc_contract.stale_lines(self.root, [{'old': '46 rules', 'new': '', 'note': ''},
                                                     {'old': '26-41 m', 'new': '', 'note': ''},
                                                     {'old': '17934', 'new': '', 'note': ''}])
        self.assertEqual(prose['warnings'], [])
        self.assertEqual(prose['lines'], 1)

    def test_the_brief_rule_asks_for_prose_figures(self):
        import brief
        self.assertIn('"46 rules"', brief.WORKING_RULES[False])


class SettingsLocalSignatureTests(LoopFixture):
    def test_local_permissions_leave_the_signature_unchanged_but_settings_json_does_not(self):
        before = project.source_signature(self.root)
        local = self.root / '.claude/settings.local.json'
        local.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)']}}))
        self.assertEqual(project.source_signature(self.root), before)
        local.write_text(json.dumps({'permissions': {'allow': ['Bash(ls)', 'Bash(pwd)']}}))
        self.assertEqual(project.source_signature(self.root), before)
        shared = self.root / '.claude/settings.json'
        self.assertTrue(shared.exists())
        shared.write_text(shared.read_text() + '\n')
        self.assertNotEqual(project.source_signature(self.root), before)

    def test_an_explicit_configuration_root_keeps_the_file_in(self):
        cfg = project.config(self.root)
        cfg['configuration_paths'] = cfg['configuration_paths'] + ['.claude/settings.local.json']
        project.atomic_json(self.root / 'esx/project.json', cfg)
        (self.root / '.claude/settings.local.json').write_text('{}')
        before = project.source_signature(self.root)
        (self.root / '.claude/settings.local.json').write_text('{"a": 1}')
        self.assertNotEqual(project.source_signature(self.root), before)


class StaleEvidenceHelpTests(LoopFixture):
    def test_stale_evidence_is_listed_with_its_rerun_command(self):
        start = self.begin_issue()
        evidence = verify.run(self.root, 'focused', 'r1', fresh=True)['evidence']
        self.assertEqual(verify.stale_evidence(self.root, 'r1'), [])
        path = self.root / 'src/diffusion.py'
        path.write_text(path.read_text() + '\n# edited after sealing\n')
        found = verify.stale_evidence(self.root, 'r1')
        self.assertEqual([f['evidence'] for f in found], [evidence])
        self.assertEqual(found[0]['suite'], 'focused')
        self.assertIn('verify.py --suite focused --owner r1 --fresh', found[0]['rerun'])
        self.assertEqual(verify.stale_evidence(self.root, 'other'), [])
        footer = {'agent': 'richard', 'issue_id': start['id'], 'iteration_timestamp': start['timestamp'],
                  'correction_round': 0, 'verdict': 'APPROVE', 'must_fix': [],
                  'independent_check': {'evidence': evidence}}
        record = hooks.capture(self.root, {'agent_type': 'richard', 'agent_id': 'r1', 'session_id': 's',
                                           'last_assistant_message': '```json\n' + json.dumps(footer) + '\n```'})
        self.assertEqual(record['status'], 'incomplete')
        self.assertIn('verification evidence is stale', record['error'])
        self.assertIn(evidence['path'], record['error'])
        self.assertIn(found[0]['rerun'], record['error'])


if __name__ == '__main__':
    unittest.main()
