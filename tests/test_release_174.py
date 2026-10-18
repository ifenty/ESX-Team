"""1.7.4: every slash-command file in the template has frontmatter that parses.

1.7.3 shipped `argument-hint: [--max-iterations N] [--permissions MODE] | status | ...` in esx-loop.md: a YAML flow
list followed by stray text, so Claude Code reported "failed to parse" at the top of the command. This test parses the
frontmatter of every command file, with PyYAML when it is installed and with a strict structural check otherwise.
"""
import re
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_framework import KIT

COMMANDS = sorted((KIT / 'template/.claude/commands').glob('*.md'))


def frontmatter(path):
    match = re.match(r'---\r?\n(.*?)\r?\n---\r?\n', path.read_text(), re.S)
    return match[1] if match else None


class CommandFrontmatterTests(unittest.TestCase):
    def test_there_are_command_files(self):
        self.assertTrue(COMMANDS)

    def test_each_has_frontmatter(self):
        for path in COMMANDS:
            self.assertIsNotNone(frontmatter(path), path.name)

    def test_each_parses(self):
        try:
            import yaml
        except ImportError:
            yaml = None
        for path in COMMANDS:
            text = frontmatter(path)
            if yaml:
                data = yaml.safe_load(text)
                self.assertIsInstance(data, dict, path.name)
                self.assertTrue(all(isinstance(k, str) for k in data), path.name)
                continue
            for line in text.splitlines():
                key, sep, value = line.partition(':')
                self.assertTrue(sep and key.strip(), f'{path.name}: not a "key: value" line: {line!r}')
                value = value.strip()
                if value.startswith('['):
                    # a plain flow list must be one complete list; anything after the closing bracket is a parse error
                    self.assertTrue(value.endswith(']') and value.count('[') == value.count(']'),
                                    f'{path.name}: unquoted value starts a flow list but is not one: {value!r}')

    def test_esx_loop_hint_is_quoted_and_names_the_permissions_option(self):
        text = frontmatter(KIT / 'template/.claude/commands/esx-loop.md')
        hint = next(l for l in text.splitlines() if l.startswith('argument-hint:'))
        self.assertRegex(hint, r'argument-hint: ".*--permissions MODE.*"$')


if __name__ == '__main__':
    unittest.main()
