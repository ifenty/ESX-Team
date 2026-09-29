"""Regression witnesses for TEAM-ARCH-REORIENT-001: `navigate --reuse-args`.

A commissioned edit to a declared target stales Arch's orientation. The shortcut
reloads the recorded map, targets and documents, still prints every current
excerpt, and demands a freshly written use. It refuses when the slice moved
beyond the declared targets and documents, and accepts no refusal-echoed hash.
"""
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'template/tools/esx'))
import doc_contract as dc
spec = importlib.util.spec_from_file_location('reorient_deploy', KIT / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

ISSUE = 'REORIENT-001'
MAP = 'docs/code_map.md#pipeline'
TARGETS = ['src/model.py::step', 'src/model.py::consumer']
DOCS = ['docs/model_contract.md']
USE = 'Inspect the scalar owner, its consumer and the configured scientific contract before editing.'
FRESH = 'After the commissioned factor edit, step still owns scaling and consumer delegates unchanged.'


class ReuseNavigateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='esx reorient ')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / 'project'
        deploy.deploy(self.root, apply=True)
        example = KIT / 'examples/periodic_diffusion'
        for directory in ('src', 'tests'):
            shutil.copytree(example / directory, self.root / directory)
        for source, target in [('project.json', 'esx/project.json'),
                               ('project_profile.md', 'esx/project_profile.md'),
                               ('code_map.md', 'docs/code_map.md')]:
            shutil.copyfile(example / source, self.root / target)
        self.model = self.root / 'src/model.py'
        self.model.write_text('"""Scalar update and its dependent mapping."""\nFACTOR = 1\n'
                              'def step(x):\n    """Scale a scalar tracer by the configured factor."""\n'
                              '    return FACTOR*x\ndef consumer(x):\n    """Apply the scalar tracer update."""\n'
                              '    return step(x)\n')
        self.base = dc.baseline(self.root, ISSUE)
        with redirect_stderr(io.StringIO()):
            self.original = dc.navigate(self.root, ISSUE, self.base, 'arch', MAP, TARGETS, DOCS, USE)

    def commissioned_edit(self):
        self.model.write_text(self.model.read_text().replace('return FACTOR*x', 'return FACTOR*x*2'))

    def stale_message(self):
        with self.assertRaisesRegex(ValueError, 'stale arch orientation') as caught:
            dc.validate_orientation(self.root, self.original, ISSUE, self.base, 'arch')
        return str(caught.exception)

    def reuse(self, use, **kwargs):
        err = io.StringIO()
        with redirect_stderr(err):
            ref = dc.reuse_navigate(self.root, ISSUE, self.original, use, **kwargs)
        return ref, err.getvalue()

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', 'tools/esx/doc_contract.py', *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_reuse_reloads_prints_every_excerpt_and_records_valid_orientation(self):
        self.commissioned_edit()
        message = self.stale_message()
        self.assertIn('--reuse-args', message)
        ref, printed = self.reuse(FRESH)
        for reference in [MAP, *TARGETS, *DOCS]:
            self.assertIn(f'--- {reference} (', printed)
        self.assertIn('return FACTOR*x*2', printed)
        record = dc.validate_orientation(self.root, ref, ISSUE, self.base, 'arch')
        self.assertEqual((record['map'], record['targets'], record['documents'], record['role'], record['use']),
                         (MAP, TARGETS, DOCS, 'arch', FRESH))
        self.assertEqual(record['reused_from'], self.original)
        self.assertNotEqual(ref, self.original)

    def test_reuse_requires_freshly_written_use(self):
        self.commissioned_edit()
        for use in (None, '', '   '):
            with self.assertRaisesRegex(ValueError, 'freshly written --use'):
                self.reuse(use)
        with self.assertRaisesRegex(ValueError, 'repeats the original'):
            self.reuse('  ' + USE.upper().replace(' ', '   ') + ' ')
        with self.assertRaisesRegex(ValueError, 'explain how these references'):
            self.reuse('too short to explain')
        run = self.cli('navigate', '--issue', ISSUE, '--reuse-args', json.dumps(self.original))
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('--use', run.stderr)
        with self.assertRaises(ValueError):
            dc.validate_orientation(self.root, self.original, ISSUE, self.base, 'arch')

    def test_refusal_echoed_values_cannot_clear_stale_orientation(self):
        self.commissioned_edit()
        message = self.stale_message()
        with self.assertRaisesRegex(ValueError, 'cites orientation hashes'):
            self.reuse(message)
        after = json.loads(message.split('changes=')[1].split('; resume')[0])[0]['after']
        with self.assertRaisesRegex(ValueError, 'cites orientation hashes'):
            self.reuse(f'Acknowledged the commissioned change to step; new hash {after}.')

    def test_refused_when_changed_target_outside_declared_targets_and_documents(self):
        self.commissioned_edit()
        code_map = self.root / 'docs/code_map.md'
        code_map.write_text(code_map.read_text().replace('The update lives at', 'The update moved to'))
        with self.assertRaises(ValueError) as caught:
            self.reuse(FRESH)
        text = str(caught.exception)
        self.assertIn(json.dumps([MAP]), text)
        self.assertIn('run full navigate', text)
        self.assertNotIn('src/model.py::step', text)

    def test_refused_when_declared_target_no_longer_resolves(self):
        self.model.write_text(self.model.read_text().replace('def consumer(x)', 'def apply(x)'))
        with self.assertRaisesRegex(ValueError, 'no longer resolve.*src/model.py::consumer'):
            self.reuse(FRESH)

    def test_reuse_role_and_baseline_must_match_when_supplied(self):
        with self.assertRaisesRegex(ValueError, 'another role'):
            self.reuse(FRESH, role='bob')
        with self.assertRaisesRegex(ValueError, 'belongs to another issue'):
            dc.reuse_navigate(self.root, 'OTHER-001', self.original, FRESH)

    def test_cli_reuse_with_bare_digest_and_full_navigate_unchanged(self):
        self.commissioned_edit()
        run = self.cli('navigate', '--issue', ISSUE, '--reuse-args', self.original['sha256'], '--use', FRESH)
        self.assertEqual(run.returncode, 0, run.stderr)
        ref = json.loads(run.stdout)
        dc.validate_orientation(self.root, ref, ISSUE, self.base, 'arch')
        mixed = self.cli('navigate', '--issue', ISSUE, '--reuse-args', self.original['sha256'],
                         '--map', MAP, '--use', FRESH)
        self.assertNotEqual(mixed.returncode, 0)
        full_args = ['navigate', '--issue', ISSUE, '--baseline', json.dumps(self.base), '--role', 'arch',
                     '--map', MAP, *[a for t in TARGETS for a in ('--target', t)], '--doc', DOCS[0]]
        partial = self.cli(*full_args[:-2], '--use', USE)
        self.assertEqual(partial.returncode, 2)
        self.assertIn('required: --doc', partial.stderr)
        full = self.cli(*full_args, '--use', USE)
        self.assertEqual(full.returncode, 0, full.stderr)
        full_ref = json.loads(full.stdout)
        record = dc.validate_orientation(self.root, full_ref, ISSUE, self.base, 'arch')
        self.assertNotIn('reused_from', record)
        for reference in [MAP, *TARGETS, *DOCS]:
            self.assertIn(f'--- {reference} (', full.stderr)


if __name__ == '__main__':
    unittest.main()
