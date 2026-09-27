"""Versioned installation, migration, three-way upgrade and failure tests."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("esx_manager_test", ROOT / "esx_manager.py")
manager = importlib.util.module_from_spec(spec); spec.loader.exec_module(manager)


class InstallUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="esx-manager-"); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.master = self.root / "master"; self.project = self.root / "project"
        (self.master / "template/tools/esx").mkdir(parents=True); (self.master / "template/esx").mkdir()
        (self.master / "template/docs").mkdir(); self.project.mkdir()
        (self.master / "VERSION").write_text("1.0.0\n")
        (self.master / "template/tools/esx/engine.py").write_text("alpha = 1\n\n# independent section\n\n\nbeta = 1\n")
        (self.master / "template/esx/project.json").write_text(json.dumps({"project_id":"blank","project_name":"Blank"}))
        (self.master / "template/docs/code_map.md").write_text("blank map\n")

    def install(self):
        cfg = {"project_id":"sample","project_name":"Sample"}
        return manager.apply_plan(manager.install_plan(self.project, self.master, cfg))

    def bump(self, value="1.1.0"):
        (self.master / "VERSION").write_text(value + "\n")

    def test_install_creates_only_active_files_and_local_metadata(self):
        record = self.install()
        self.assertEqual((self.project / "ESX-team-local/version").read_text(), "1.0.0\n")
        self.assertFalse((self.project / "ESX-Team").exists())
        self.assertIn("no framework copy", (self.project / "ESX-team-local/README.md").read_text())
        cfg = json.loads((self.project / "ESX-team-local/config.json").read_text())
        self.assertEqual(cfg["project_id"], "sample")
        self.assertEqual(cfg["master_repository"], "supplied-by-installer-or-upgrader")
        self.assertTrue((self.project / "ESX-team-local/deployments" / (record["deployment_id"] + ".json")).is_file())
        self.assertEqual(json.loads((self.project / "esx/project.json").read_text())["project_id"], "sample")

    def test_plan_is_read_only_and_second_install_routes_to_upgrade(self):
        plan = manager.install_plan(self.project, self.master)
        self.assertFalse((self.project / "ESX-team-local").exists())
        manager.apply_plan(plan)
        with self.assertRaisesRegex(ValueError, "use esx_upgrade"):
            manager.install_plan(self.project, self.master)
        self.assertFalse(manager.upgrade_plan(self.project, self.master)["conflicts"])

    def test_unchanged_framework_updates_and_project_files_are_preserved(self):
        self.install(); engine = self.project / "tools/esx/engine.py"; project_map = self.project / "docs/code_map.md"
        project_map.write_text("project science map\n"); self.bump()
        (self.master / "template/tools/esx/engine.py").write_text("alpha = 2\n\n# independent section\n\n\nbeta = 1\n")
        (self.master / "template/docs/code_map.md").write_text("new blank map\n")
        plan = manager.upgrade_plan(self.project, self.master)
        self.assertFalse(plan["conflicts"]); manager.apply_plan(plan)
        self.assertIn("alpha = 2", engine.read_text())
        self.assertEqual(project_map.read_text(), "project science map\n")

    def test_nonoverlapping_framework_customization_three_way_merges(self):
        self.install(); engine = self.project / "tools/esx/engine.py"
        engine.write_text("alpha = 1\n\n# independent section\n\n\nbeta = 9\n"); self.bump()
        (self.master / "template/tools/esx/engine.py").write_text("alpha = 2\n\n# independent section\n\n\nbeta = 1\n")
        plan = manager.upgrade_plan(self.project, self.master)
        row = next(r for r in plan["files"] if r["path"] == "tools/esx/engine.py")
        self.assertEqual(row["action"], "three-way-merge"); manager.apply_plan(plan)
        self.assertIn("alpha = 2", engine.read_text()); self.assertIn("beta = 9", engine.read_text())
        self.bump("1.2.0")
        (self.master / "template/tools/esx/engine.py").write_text("alpha = 3\n\n# independent section\n\n\nbeta = 1\n")
        manager.apply_plan(manager.upgrade_plan(self.project, self.master))
        self.assertIn("alpha = 3", engine.read_text()); self.assertIn("beta = 9", engine.read_text())

    def test_overlap_refuses_whole_upgrade_without_writes(self):
        self.install(); engine = self.project / "tools/esx/engine.py"; before = engine.read_bytes()
        engine.write_text("alpha = project\n\n# independent section\n\n\nbeta = 1\n"); local = engine.read_bytes(); self.bump()
        (self.master / "template/tools/esx/engine.py").write_text("alpha = master\n\n# independent section\n\n\nbeta = 1\n")
        plan = manager.upgrade_plan(self.project, self.master)
        self.assertEqual(plan["conflicts"][0]["path"], "tools/esx/engine.py")
        with self.assertRaisesRegex(ValueError, "unresolved conflict"): manager.apply_plan(plan)
        self.assertEqual(engine.read_bytes(), local); self.assertNotEqual(engine.read_bytes(), before)

    def test_upgrade_preserves_process_findings_and_original_archives(self):
        names = ['devel-loop/loop_rules.md',
                 'devel-loop/self-improvement/open-ESX-team-issues.md',
                 'devel-loop/self-improvement/closed-ESX-team-issues.md',
                 'devel-loop/self-improvement/process_changelog.md',
                 'devel-loop/self-improvement/records/original.md',
                 'devel-loop/self-improvement/assessments/trial/assessment.json']
        for name in names:
            path = self.master/'template'/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original template\n')
        self.install()
        for name in names:
            (self.project/name).write_text('project-owned evidence\n')
            (self.master/'template'/name).write_text('new blank form\n')
        self.bump()
        plan = manager.upgrade_plan(self.project, self.master)
        self.assertEqual(plan['conflicts'], [])
        manager.apply_plan(plan)
        for name in names:
            self.assertEqual((self.project/name).read_text(), 'project-owned evidence\n')

    def test_missing_baseline_and_unversioned_master_changes_are_refused(self):
        self.install(); manifest_path = self.project / "ESX-team-local/manifest.json"
        manifest = json.loads(manifest_path.read_text()); digest = manifest["files"]["tools/esx/engine.py"]["baseline_sha256"]
        manager.object_path(self.project, digest).unlink(); self.bump()
        self.assertTrue(manager.upgrade_plan(self.project, self.master)["conflicts"])
        # Reinstall in a clean sibling and mutate the master without a version bump.
        self.project = self.root / "other"; self.project.mkdir(); self.install()
        (self.master / "template/tools/esx/engine.py").write_text("changed without version bump\n")
        with self.assertRaisesRegex(ValueError, "VERSION increment"): manager.upgrade_plan(self.project, self.master)

    def test_adopt_existing_registers_without_replacing_customized_files(self):
        (self.project / "tools/esx").mkdir(parents=True); target = self.project / "tools/esx/engine.py"
        target.write_text("custom deployed engine\n")
        plan = manager.adopt_plan(self.project, self.master); manager.apply_plan(plan)
        self.assertEqual(target.read_text(), "custom deployed engine\n")
        self.assertEqual((self.project / "ESX-team-local/version").read_text(), "1.0.0\n")
        self.assertEqual(json.loads((self.project / "ESX-team-local/manifest.json").read_text())["files"]["tools/esx/engine.py"]["installed_sha256"], manager.sha(target.read_bytes()))
        plan = manager.upgrade_plan(self.project, self.master)
        row = next(r for r in plan["files"] if r["path"] == "tools/esx/engine.py")
        self.assertEqual(row["action"], "preserve")
        self.assertEqual(row["content"], target.read_bytes())

    def test_agent_request_file_and_cli_conflict_exit(self):
        request = self.root / "request.json"
        request.write_text(json.dumps({"action":"install","project":str(self.project),"apply":True}))
        copied = self.master / "esx_install.py"; copied.write_text((ROOT / "esx_install.py").read_text())
        shutil.copyfile(ROOT / "esx_manager.py", self.master / "esx_manager.py")
        run = subprocess.run([sys.executable, str(copied), "--request", str(request)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "applied")

    def test_project_change_after_plan_is_refused(self):
        self.install(); self.bump(); (self.master / "template/tools/esx/engine.py").write_text("alpha = 2\n\n# independent section\n\n\nbeta = 1\n")
        plan = manager.upgrade_plan(self.project, self.master)
        (self.project / "tools/esx/engine.py").write_text("changed after plan\n")
        with self.assertRaisesRegex(ValueError, "changed after planning"): manager.apply_plan(plan)

    def test_local_metadata_symlink_is_refused(self):
        outside = self.root / "outside"; outside.mkdir()
        (self.project / "ESX-team-local").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
            manager.apply_plan(manager.install_plan(self.project, self.master))


if __name__ == "__main__":
    unittest.main()
