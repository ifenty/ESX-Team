"""TEAM-SEAL-CITATION-001: reviewers see and must cite the current documentation seal.

Every implementer correction re-seals the documentation report, so a confirming
reviewer can carry a superseded reference from an earlier round. The brief names
the current seal in a standalone section, and report capture rejects a stale
citation, naming both hashes, before the round is spent. Real sealed artifacts,
verifier receipts and the offline CLI bridge are used; no provider calls.
"""
import contextlib
import io
import json
import sys
import unittest
import test_framework
import agent_runtime
import brief
import doc_contract
import footer_contract
import project
import verify

REVIEWER = '''
import contextlib, io, json, pathlib, sys
args = sys.argv[1:]
if '--version' in args:
    print('offline-reviewer-1'); raise SystemExit(0)
sys.stdin.read()
root = pathlib.Path.cwd()
sys.path.insert(0, str(root/'tools/esx'))
import doc_contract, footer_contract, project, verify
assignment = json.loads(pathlib.Path(args[args.index('--append-system-prompt-file')+1]).read_text().split('ESX dispatcher assignment: ',1)[1].split('\\n',1)[0])
sid = assignment['agent_id']
fixture = json.loads((root/project.STATE/'seal-citation-fixture.json').read_text())
packet = fixture['packet']
with contextlib.redirect_stderr(io.StringIO()):
    orientation = doc_contract.navigate(root, packet['id'], packet['maintenance']['baseline'], 'richard',
        'docs/code_map.md#pipeline', ['src/diffusion.py::step','tests/check_diffusion.py::<module>'],
        ['docs/model_contract.md'], 'Independently inspect the exact periodic stencil and Fourier conservation oracle.')
evidence = verify.run(root, 'focused', sid, fresh=True)['evidence']
footer = footer_contract.example(root, 'richard')
footer.update(issue_id=packet['id'], iteration_timestamp=packet['timestamp'], correction_round=0,
    orientation=orientation, summary='Executed independent Fourier and conservation checks.',
    evidence=[evidence], candidate_signature=project.source_signature(root), verdict='APPROVE',
    independent_check={'cmd':'python tests/check_diffusion.py','exit':0,'executed':True,'evidence':evidence,'coverage':'Fourier decay and conservation'},
    documentation_review={'report':fixture['cite'],'status':'confirmed','notes':'Confirmed the sealed map and scientific contract against the unchanged candidate and executed oracle.'})
print(json.dumps({'type':'system','subtype':'init','session_id':sid}))
print(json.dumps({'type':'result','subtype':'success','is_error':False,'session_id':sid,'stop_reason':'end_turn',
    'result':'```json\\n'+json.dumps(footer)+'\\n```','total_cost_usd':0,'usage':{'input_tokens':0,'output_tokens':0}}))
'''


class SealCitationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.done = self.fixture.complete(qualify=False)
        self.old = self.done['maintenance']['documentation']
        # A correction round re-seals: same candidate, revised judgment, new hash.
        plan = doc_contract.draft(self.root, self.fixture.issue, self.done['maintenance']['baseline'])
        plan['map_delta'] = {'status': 'MAP-OK', 'reason': 'The corrected qualification still leaves the mapped periodic update and oracle routes unchanged.',
                             'references': ['docs/code_map.md#pipeline']}
        self.new = doc_contract.seal(self.root, plan)
        self.assertNotEqual(self.old['sha256'], self.new['sha256'])
        self.packet = dict(self.done, maintenance=dict(self.done['maintenance'], documentation=self.new))

    def footer(self, cite, agent_id='offline-reviewer'):
        with contextlib.redirect_stderr(io.StringIO()):
            orientation = doc_contract.navigate(self.root, self.fixture.issue, self.done['maintenance']['baseline'], 'richard',
                'docs/code_map.md#pipeline', ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'],
                ['docs/model_contract.md'], 'Independently inspect the exact periodic stencil and Fourier conservation oracle.')
        evidence = verify.run(self.root, 'focused', agent_id, fresh=True)['evidence']
        footer = footer_contract.example(self.root, 'richard')
        footer.update(issue_id=self.fixture.issue, iteration_timestamp=self.done['timestamp'], correction_round=0,
            orientation=orientation, summary='Executed independent checks.', evidence=[evidence],
            candidate_signature=project.source_signature(self.root), verdict='APPROVE',
            independent_check={'cmd': 'python tests/check_diffusion.py', 'exit': 0, 'executed': True,
                               'evidence': evidence, 'coverage': 'Fourier decay and conservation'},
            documentation_review={'report': cite, 'status': 'confirmed',
                                  'notes': 'Confirmed the sealed map and scientific contract against the unchanged candidate.'})
        return footer

    def validate(self, footer, expected):
        return footer_contract.validate(self.root, 'richard', footer, self.fixture.issue, 0,
                                        self.fixture.start, 'offline-reviewer', expected)

    def test_reviewer_brief_names_current_seal_standalone(self):
        text = brief.build(self.root, 'richard', self.fixture.issue, 'Confirm the corrected candidate.',
                           'Does the oracle support this exact candidate?', self.packet)
        section = text.split('# Current sealed documentation report (required footer input)\n', 1)[1].split('\n# ', 1)[0]
        current = self.packet['maintenance']['documentation']
        self.assertIn('path: ' + current['path'], section)
        self.assertIn('sha256: ' + current['sha256'], section)
        self.assertIn('Read that exact file', section)
        self.assertNotIn(self.old['sha256'], section)
        example = json.loads(text.rsplit('```json\n', 1)[1].split('\n```', 1)[0])
        self.assertEqual(example['documentation_review']['report'], current)
        # Implementers are not handed a reviewer citation.
        self.assertNotIn('Current sealed documentation report', brief.build(self.root, 'bob', self.fixture.issue, 'Implement.'))

    def test_stale_citation_rejected_at_capture_naming_both_hashes(self):
        errors = self.validate(self.footer(self.old), self.new)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(self.old['sha256'], errors[0])
        self.assertIn(self.new['sha256'], errors[0])
        self.assertIn('superseded', errors[0])
        self.assertEqual(self.validate(self.footer(self.new), self.new), [])

    def test_missing_or_altered_report_still_fails(self):
        missing = {'path': self.new['path'].replace(self.new['sha256'], '0' * 64), 'sha256': '0' * 64}
        self.assertTrue(self.validate(self.footer(missing), None))
        self.assertTrue(self.validate(self.footer(missing), missing))
        footer = self.footer(self.new)
        stored = self.root / self.new['path']
        payload = json.loads(stored.read_text())
        payload['map_delta']['reason'] += ' Altered after sealing.'
        stored.write_text(json.dumps(payload))
        errors = self.validate(footer, self.new)
        self.assertTrue(any('hash mismatch' in e for e in errors), errors)

    def run_reviewer(self, cite):
        project.atomic_json(self.root / project.STATE / 'seal-citation-fixture.json', {'packet': self.packet, 'cite': cite})
        binary = self.root / 'fake-reviewer'
        binary.write_text('#!' + sys.executable + '\n' + REVIEWER)
        binary.chmod(0o755)
        prompt = brief.build(self.root, 'richard', self.fixture.issue, 'Confirm the corrected candidate.',
                             'Does the oracle support this exact candidate?', self.packet)
        return agent_runtime.run_turn(self.root, role='richard', issue=self.fixture.issue, prompt=prompt,
                                      review_packet=self.packet, executable=str(binary), timeout=20)

    def test_captured_turn_rejects_stale_and_accepts_current(self):
        stale = self.run_reviewer(self.old)
        self.assertEqual(stale['status'], 'incomplete', stale)
        self.assertIn(self.old['sha256'], stale['error'])
        self.assertIn(self.new['sha256'], stale['error'])
        current = self.run_reviewer(self.new)
        self.assertEqual(current['status'], 'completed', current)


if __name__ == '__main__':
    unittest.main()
