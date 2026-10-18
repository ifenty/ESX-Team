"""1.8.0: all text that a person reads follows ASD-STE100.

The rule lives in framework-owned files so that an upgrade delivers it to an existing project. The root
CLAUDE.md and the record files are project-owned and change for new installations only.
"""
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_framework import KIT  # noqa: F401  (puts template/tools/esx on sys.path)
import esx_manager

TEMPLATE = KIT / 'template'
RULE = 'devel-loop/writing_standard.md'


class WritingStandardTests(unittest.TestCase):
    def test_rule_file_exists_and_names_the_standard_and_the_records(self):
        text = (TEMPLATE / RULE).read_text()
        self.assertIn('ASD-STE100', text)
        for record in ('open issues', 'lessons learned', 'long-term goals', 'closeout summaries', 'messages'):
            self.assertIn(record, text.lower(), record)

    def test_rule_file_is_framework_owned_so_an_upgrade_delivers_it(self):
        self.assertEqual(esx_manager.ownership(RULE), 'framework')
        for name in ('.claude/ESX-team/ARCHITECT.md', '.claude/skills/esx-common/SKILL.md',
                     'devel-loop/communication.md'):
            self.assertEqual(esx_manager.ownership(name), 'framework', name)

    def test_framework_contracts_point_to_the_rule(self):
        for name in ('.claude/ESX-team/ARCHITECT.md', '.claude/skills/esx-common/SKILL.md'):
            text = (TEMPLATE / name).read_text()
            self.assertIn('ASD-STE100', text, name)
            self.assertIn('writing_standard.md', text, name)
        self.assertIn('writing_standard.md', (TEMPLATE / 'devel-loop/communication.md').read_text())

    def test_new_installations_carry_the_instruction_in_root_files(self):
        for name in ('CLAUDE.md', 'open_issues.md', 'closed_issues.md', 'lessons_learned.md',
                     'long_term_goals.md', 'current_status.md'):
            self.assertIn('ASD-STE100', (TEMPLATE / name).read_text(), name)

    def test_kit_documents_carry_the_standard_and_the_master_location(self):
        self.assertIn('ASD-STE100', (KIT / 'CLAUDE.md').read_text())
        self.assertTrue((KIT / 'WRITING_STANDARD.md').is_file())
        guide = (KIT / 'INSTALL_UPGRADE.md').read_text()
        self.assertIn('https://github.com/ifenty/ESX-Team', guide)
        self.assertNotIn('/Users/', guide)

    def test_rule_sentences_stay_short(self):
        """The rule file must follow its own limit: no sentence over 25 words."""
        text = re.sub(r'```.*?```', '', (TEMPLATE / RULE).read_text(), flags=re.S)
        for line in text.splitlines():
            if line.startswith(('|', '#')) or not line.strip():
                continue
            line = re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', line)
            for sentence in re.split(r'(?<=[.!?])\s+', line):
                self.assertLessEqual(len(sentence.split()), 25, sentence)


LINTER = TEMPLATE / 'tools/esx/ste_lint.py'
DOCUMENTS = ('README.md', 'INSTALL_UPGRADE.md', 'VALIDATION.md', 'PROVENANCE.md', 'WRITING_STANDARD.md',
             'THIRD_PARTY_NOTICES.md', 'template/devel-loop/writing_standard.md')
UPSTREAM = 'https://github.com/danyuchn/asd-ste100-skill'


class LinterAndCreditTests(unittest.TestCase):
    def lint(self, *paths):
        return subprocess.run([sys.executable, str(LINTER), '--json', *map(str, paths)],
                              capture_output=True, text=True)

    def test_the_vendored_linter_passes_its_own_selftest(self):
        run = subprocess.run([sys.executable, str(LINTER), '--selftest'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('selftest OK', run.stdout)

    def test_kit_documents_have_no_hard_violation(self):
        for name in DOCUMENTS:
            run = self.lint(KIT / name)
            self.assertEqual(run.returncode, 0, f'{name}: {run.stdout[:600]}')

    def test_the_new_changelog_entry_has_no_hard_violation(self):
        text = (KIT / 'CHANGELOG.md').read_text()
        entry = text[text.index('## Version 1.8.0'):text.index('## Version 1.7.4:')]
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'entry.md'
            path.write_text(entry)
            run = self.lint(path)
        self.assertEqual(run.returncode, 0, run.stdout[:600])

    def test_the_linter_does_not_flag_a_hedge(self):
        run = subprocess.run([sys.executable, str(LINTER)], input='The request may have failed.\n',
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout)

    def test_the_linter_catches_a_semicolon_and_a_long_sentence(self):
        run = subprocess.run([sys.executable, str(LINTER)], capture_output=True, text=True,
                             input='Open the file; read line 3.\n')
        self.assertEqual(run.returncode, 1, run.stdout)

    def test_the_origin_repository_is_credited_with_its_license(self):
        origin = 'https://github.com/russelleNVy/three-man-team'
        for name in ('THIRD_PARTY_NOTICES.md', 'README.md', 'PROVENANCE.md', 'CHANGELOG.md'):
            self.assertIn(origin, (KIT / name).read_text(), name)
        notices = (KIT / 'THIRD_PARTY_NOTICES.md').read_text()
        self.assertIn('Copyright (c) 2026 Russell Aaron', notices)
        self.assertIn('Copyright (c) 2026 Dustin Yuchen Teng', notices)

    def test_the_upstream_repository_is_credited_where_the_work_is_used(self):
        for name in ('THIRD_PARTY_NOTICES.md', 'README.md', 'WRITING_STANDARD.md', 'template/devel-loop/writing_standard.md',
                     'CHANGELOG.md'):
            self.assertIn(UPSTREAM, (KIT / name).read_text(), name)
        header = LINTER.read_text().split('"""', 1)[0]
        self.assertIn(UPSTREAM, header)
        self.assertIn('MIT', header)
        self.assertIn('Dustin Yuchen Teng', header)
        notices = (KIT / 'THIRD_PARTY_NOTICES.md').read_text()
        self.assertIn('Permission is hereby granted', notices)


if __name__ == '__main__':
    unittest.main()
