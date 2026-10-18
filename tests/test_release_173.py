"""1.7.3: retained roles run in permission mode `auto`; /esx-loop --permissions chooses bypassPermissions or inherit.

A headless `claude --print` ignores permissions.defaultMode from settings, so a role ran in `default` mode and
most compound commands were denied. Offline: no CLI is started here; the launcher's command line is checked
at the source and the mode decision is checked on synthetic settings and loop state.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_framework import KIT  # noqa: F401  (puts template/tools/esx on sys.path)
import agent_runtime
import loop_control


def settings(path, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'permissions': {'defaultMode': mode}}))


class RolePermissionModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__('shutil').rmtree, self.tmp, True)
        self.home = self.tmp / 'home'
        self.root = self.tmp / 'proj'
        self.old = __import__('os').environ.get('CLAUDE_CONFIG_DIR')
        __import__('os').environ['CLAUDE_CONFIG_DIR'] = str(self.home)
        self.addCleanup(self.restore)

    def restore(self):
        env = __import__('os').environ
        if self.old is None:
            env.pop('CLAUDE_CONFIG_DIR', None)
        else:
            env['CLAUDE_CONFIG_DIR'] = self.old

    def loop(self, extra=''):
        (self.root / '.claude').mkdir(parents=True, exist_ok=True)
        (self.root / '.claude/esx-loop.local.md').write_text(
            '---\nactive: true\niteration: 1\nmax_iterations: 3\n' + extra + '---\nprompt\n')

    def test_default_is_auto_whatever_the_settings_say(self):
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto')
        settings(self.root / '.claude/settings.local.json', 'bypassPermissions')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto')
        self.loop()
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto')

    def test_loop_can_choose_bypass(self):
        self.loop('permission_mode: bypassPermissions\n')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'bypassPermissions')

    def test_inherit_follows_settings_local_over_project_over_user(self):
        self.loop('permission_mode: inherit\n')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto')
        settings(self.home / 'settings.json', 'bypassPermissions')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'bypassPermissions')
        settings(self.root / '.claude/settings.json', 'auto')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto')
        settings(self.root / '.claude/settings.local.json', 'bypassPermissions')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'bypassPermissions')

    def test_modes_that_cannot_run_the_shell_headless_fall_back_to_auto(self):
        for mode in ('acceptEdits', 'dontAsk', 'plan', 'manual', 'default', 'nonsense'):
            self.loop(f'permission_mode: {mode}\n')
            self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto', mode)
            self.loop('permission_mode: inherit\n')
            settings(self.root / '.claude/settings.local.json', mode)
            self.assertEqual(agent_runtime.role_permission_mode(self.root), 'auto', mode)

    def test_loop_control_validates_and_stores_the_mode(self):
        self.loop()
        loop_control.set_permissions(self.root, 'bypassPermissions')
        self.assertEqual(loop_control.permissions_of(self.root), 'bypassPermissions')
        self.assertEqual(agent_runtime.role_permission_mode(self.root), 'bypassPermissions')
        loop_control.set_permissions(self.root, 'inherit')
        self.assertEqual(loop_control.permissions_of(self.root), 'inherit')
        loop_control.set_permissions(self.root, 'auto')
        self.assertEqual(loop_control.permissions_of(self.root), 'auto')
        self.assertNotIn('permission_mode', (self.root / '.claude/esx-loop.local.md').read_text())
        for bad in ('plan', 'dontAsk', 'yolo'):
            with self.assertRaises(ValueError):
                loop_control.set_permissions(self.root, bad)

    def test_launcher_always_passes_the_mode_and_the_command_documents_it(self):
        source = Path(agent_runtime.__file__).read_text()
        self.assertIn('command += ["--permission-mode", role_permission_mode(root)]', source)
        command = (KIT / 'template/.claude/commands/esx-loop.md').read_text()
        self.assertIn('--permissions MODE', command)
        for mode in ('auto', 'bypassPermissions', 'inherit'):
            self.assertIn(mode, command)


if __name__ == '__main__':
    unittest.main()
