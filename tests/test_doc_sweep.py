"""Declared-symbol documentation sweep in generated briefs (TEAM-DOC-SWEEP-001).

A brief for a change to a named default must enumerate every document that
currently mentions the name, including documents the change never touches.
"""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
import test_framework
import brief
import project


class DocSweepTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_framework.FrameworkTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.prepare()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_declared_symbol_lists_every_mentioning_document_with_lines(self):
        # Two in-inventory files and one report outside every configured root,
        # none of which the change itself touches.
        self.write('src/params.py', 'x = 1\nkeep_mitgcm_bugs = True\n# keep_mitgcm_bugs: see contract\n')
        self.write('docs/model_contract.md', '# Contract\n\nThe default `keep_mitgcm_bugs=True` matches MITgcm.\n')
        self.write('validation/reports/lessons.md', 'a\nb\nc\nWe recommend keep_mitgcm_bugs False.\n')
        # Neither a partial word, loop state, nor a binary file is a mention.
        self.write('notes/other.md', 'keep_mitgcm_bugs_extra and xkeep_mitgcm_bugs are different names.\n')
        self.write(project.STATE + '/old-brief.txt', 'keep_mitgcm_bugs\n')
        (self.root / 'validation/data.bin').write_bytes(b'\0keep_mitgcm_bugs\n')
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Flip the default.', sweep_symbols=['keep_mitgcm_bugs'])
        self.assertIn('# Documents mentioning `keep_mitgcm_bugs`', text)
        self.assertIn('explicit target', text)
        for entry in ('src/params.py:2,3\n', 'docs/model_contract.md:3\n', 'validation/reports/lessons.md:4\n'):
            self.assertIn(entry, text)
        for absent in ('notes/other.md', 'old-brief.txt', 'data.bin'):
            self.assertNotIn(absent, text)
        self.assertNotIn('omitted', text)

    def test_no_section_without_declared_symbol(self):
        self.write('docs/model_contract.md', 'keep_mitgcm_bugs\n')
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Flip the default.')
        self.assertNotIn('Documents mentioning', text)
        self.assertEqual(text, brief.build(self.root, 'bob', self.fixture.issue, 'Flip the default.', sweep_symbols=[]))

    def test_output_is_capped_with_omitted_count(self):
        for i in range(brief.SWEEP_LIMIT + 7):
            self.write('docs/many/%03d.md' % i, 'THE_SYMBOL\n')
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Change it.', sweep_symbols=['THE_SYMBOL'])
        self.assertEqual(text.count('docs/many/'), brief.SWEEP_LIMIT)
        self.assertIn('7 further mentioning file(s) omitted at the %d-file cap' % brief.SWEEP_LIMIT, text)

    def test_verbose_file_cannot_crowd_out_another_file(self):
        count = brief.SWEEP_LINES_PER_FILE + 100
        self.write('A_first/verbose.md', 'THE_SYMBOL\n' * count)
        self.write('z_last/stale.md', 'intro\nTHE_SYMBOL\n')
        text = brief.build(self.root, 'bob', self.fixture.issue, 'Change it.', sweep_symbols=['THE_SYMBOL'])
        self.assertIn('(+100 more line(s) in this file)', text)
        self.assertIn('z_last/stale.md:2\n', text)

    def test_cli_repeatable_option(self):
        self.write('docs/a.md', 'ALPHA\n')
        self.write('docs/b.md', 'beta_default\n')
        self.write('design.md', 'Change both.\n')
        run = subprocess.run([sys.executable, '-B', str(self.root / 'tools/esx/brief.py'), '--root', str(self.root),
                              '--role', 'bob', '--issue', self.fixture.issue, '--design', 'design.md',
                              '--sweep-symbol', 'ALPHA', '--sweep-symbol', 'beta_default'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('# Documents mentioning `ALPHA`, `beta_default`', run.stdout)
        self.assertIn('docs/a.md:1\n', run.stdout)
        self.assertIn('docs/b.md:1\n', run.stdout)


if __name__ == '__main__':
    unittest.main()
