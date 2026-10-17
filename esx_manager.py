#!/usr/bin/env python3
"""Versioned ESX installation and safe three-way upgrades.

One master repository supplies the template. A receiving project contains only
the active installation and ``ESX-team-local`` metadata: version, configuration,
deployment records, content-addressed baselines and rollback backups.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

MASTER = Path(__file__).resolve().parent
LOCAL = "ESX-team-local"
SCHEMA = 1
PROJECT_OWNED = {
    "CLAUDE.md", ".gitignore", ".claude/settings.json",
    "esx/project.json", "esx/project_profile.md",
    "docs/code_map.md", "docs/model_contract.md", "docs/doc_format_guide.md",
    "open_issues.md", "closed_issues.md", "current_status.md", "long_term_goals.md",
    "lessons_learned.md", "lessons_learned_evidence.md", "old_lessons_learned.md",
    "devel-loop/loop_rules.md",
    "devel-loop/self-improvement/open-ESX-team-issues.md",
    "devel-loop/self-improvement/closed-ESX-team-issues.md",
    "devel-loop/self-improvement/process_changelog.md",
    "devel-loop/self-improvement/migration_manifest.json",
}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary: temporary.unlink(missing_ok=True)

def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()

def version(master=MASTER):
    value = (Path(master) / "VERSION").read_text().strip()
    if not value or any(c not in "0123456789." for c in value):
        raise ValueError("VERSION must contain a dotted numeric version")
    return value

def inside(root, name):
    root = Path(root).resolve(); candidate = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError(f"path leaves project: {name}")
    for path in [candidate, *candidate.parents]:
        if path == root.parent: break
        if path.is_symlink(): raise ValueError(f"deployment refuses symlink destination: {path}")
    if not candidate.resolve().is_relative_to(root): raise ValueError(f"path leaves project: {name}")
    return candidate

def template_files(master=MASTER):
    root = Path(master) / "template"; result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.name != ".DS_Store":
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result

def ownership(name):
    return "project" if (name in PROJECT_OWNED or name.startswith((
        "devel-loop/self-improvement/assessments/", "devel-loop/self-improvement/records/"))) else "framework"

def master_fingerprint(master=MASTER):
    return sha(json_bytes({name: sha(data) for name, data in template_files(master).items()}))

def version_tuple(value):
    return tuple(int(part) for part in value.split("."))

def merge_special(name, existing, incoming):
    if existing == incoming: return existing
    if name == ".gitignore":
        lines = existing.decode().splitlines(); additions = [x for x in incoming.decode().splitlines() if x and x not in lines]
        return existing.rstrip(b"\n") + (b"\n" if existing else b"") + (("\n".join(additions) + "\n").encode() if additions else b"")
    if name == "CLAUDE.md":
        block = ("<!-- ESX-TEAM -->\nRead [ESX project instructions](esx/project_instructions.md) "
                 "for the team workflow and project configuration.\n<!-- /ESX-TEAM -->\n")
        return existing if "<!-- ESX-TEAM -->" in existing.decode() else existing.rstrip(b"\n") + b"\n\n" + block.encode()
    if name == ".claude/settings.json":
        old, new = json.loads(existing), json.loads(incoming)
        for event, groups in new.get("hooks", {}).items():
            target = old.setdefault("hooks", {}).setdefault(event, [])
            for group in groups:
                if group in target: continue
                for wanted in group.get("hooks", []):
                    if any(("tools/esx/hooks.py" in hook.get("command", "") or
                            "tools/esx/ralph_stop.py" in hook.get("command", ""))
                           for item in target for hook in item.get("hooks", [])):
                        raise ValueError(f"existing ESX {event} hook differs; reconcile it explicitly")
                target.append(group)
        return json_bytes(old)
    raise ValueError(f"collision: existing file blocks fresh install: {name}")

def esx_hook_key(hook):
    """Identify an ESX hook by script and subcommand, e.g. ('hooks.py', 'subagent-start')."""
    command = hook.get("command", "") if isinstance(hook, dict) else ""
    for script in ("tools/esx/hooks.py", "tools/esx/ralph_stop.py"):
        if script in command:
            rest = command.split(script, 1)[1].replace('"', " ").split()
            return (script, rest[0] if rest else "")
    return None

def add_missing_esx_hooks(existing, incoming):
    """Upgrade-time merge for project-owned settings: add ESX hook entries that are
    entirely absent; never modify or remove anything already present."""
    old, new = json.loads(existing), json.loads(incoming)
    if not isinstance(old, dict): raise ValueError(".claude/settings.json must contain a JSON object")
    present = {esx_hook_key(h) for groups in (old.get("hooks") or {}).values() for g in groups
               for h in (g.get("hooks") or [])} - {None}
    added = []
    for event, groups in (new.get("hooks") or {}).items():
        for group in groups:
            keys = {esx_hook_key(h) for h in group.get("hooks", [])} - {None}
            if keys and not keys & present:
                old.setdefault("hooks", {}).setdefault(event, []).append(group)
                present |= keys; added.append(event)
    return (json_bytes(old), added) if added else (existing, [])

def object_path(project, digest):
    path = Path(project) / LOCAL / "objects" / digest
    if path.is_symlink(): raise ValueError(f"baseline object cannot be a symlink: {digest}")
    return path

def store_object(project, data):
    digest = sha(data); target = object_path(project, digest)
    if target.exists() and target.read_bytes() != data: raise ValueError(f"baseline object hash collision: {digest}")
    if not target.exists(): atomic(target, data)
    return digest

def load_manifest(project):
    path = Path(project) / LOCAL / "manifest.json"
    if not path.is_file(): raise ValueError(f"{LOCAL}/manifest.json is missing; use esx_install.py or migrate the installation")
    value = json.loads(path.read_text())
    if value.get("schema_version") != SCHEMA or not isinstance(value.get("files"), dict):
        raise ValueError("unsupported or malformed local ESX manifest")
    return value

def local_config(project):
    path = Path(project) / LOCAL / "config.json"
    return json.loads(path.read_text()) if path.exists() else {}

@contextmanager
def project_lock(project):
    path = Path(project) / LOCAL / "upgrade.lock"; path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink(): raise ValueError(f"{LOCAL} cannot be a symlink")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX); yield

def three_way(current, base, incoming):
    if b"\x00" in current + base + incoming: return current, False
    with tempfile.TemporaryDirectory(prefix="esx-merge-") as folder:
        folder = Path(folder); paths = [folder / n for n in ("current", "base", "incoming")]
        for path, data in zip(paths, (current, base, incoming)): path.write_bytes(data)
        run = subprocess.run(["git", "merge-file", "-p", "-L", "project", "-L", "installed baseline",
                              "-L", "new ESX master", *map(str, paths)], capture_output=True)
        if run.returncode == 0: return run.stdout, True
        # git merge-file exits with the NUMBER of conflicts (1..127); only >=128 (or a signal/negative status) is an error.
        if 1 <= run.returncode <= 127: return run.stdout, False
        raise ValueError(f"git merge-file failed (exit {run.returncode}): " + run.stderr.decode(errors="replace").strip())

def deployment_id(action):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{action}-{uuid.uuid4().hex[:8]}"

def base_config(project, master, installed_at=None):
    result = {"schema_version": SCHEMA, "project_root": ".",
              "master_repository": "supplied-by-installer-or-upgrader", "installed_at": installed_at or now(),
              "project_configuration": "esx/project.json"}
    path = Path(project) / "esx/project.json"
    if path.exists():
        cfg = json.loads(path.read_text()); result.update(project_id=cfg.get("project_id"), project_name=cfg.get("project_name"))
    return result

def install_plan(project, master=MASTER, configuration=None):
    project, master = Path(project).resolve(), Path(master).resolve()
    if (project / LOCAL / "manifest.json").exists(): raise ValueError("project already has versioned ESX metadata; use esx_upgrade.py")
    if (project / "ESX-Team").exists(): raise ValueError("project contains a bundled ESX-Team copy; migrate it before installation")
    rows, conflicts = [], []
    for name, original in template_files(master).items():
        incoming = json_bytes(configuration) if name == "esx/project.json" and configuration is not None else original
        target = inside(project, name)
        if target.exists():
            try:
                result = merge_special(name, target.read_bytes(), incoming); action = "unchanged" if result == target.read_bytes() else "merge"
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                conflicts.append({"path": name, "reason": str(exc)}); continue
        else: result, action = incoming, "create"
        rows.append({"path": name, "ownership": ownership(name), "action": action,
                     "before_sha256": sha(target.read_bytes()) if target.exists() else None,
                     "result_sha256": sha(result), "master_sha256": sha(incoming), "content": result})
    return {"action": "install", "project": str(project), "master": str(master), "from_version": None,
            "to_version": version(master), "files": rows, "conflicts": conflicts}

def upgrade_plan(project, master=MASTER):
    project, master = Path(project).resolve(), Path(master).resolve()
    manifest, new_files = load_manifest(project), template_files(master); old_files = manifest["files"]
    target_version = version(master); fingerprint = master_fingerprint(master)
    if version_tuple(target_version) < version_tuple(manifest["version"]):
        raise ValueError(f"downgrade refused: installed {manifest['version']}, master {target_version}")
    if target_version == manifest["version"] and manifest.get("master_fingerprint") != fingerprint:
        raise ValueError("master template changed without a VERSION increment")
    rows, conflicts = [], []
    for name in sorted(set(old_files) | set(new_files)):
        target, old = inside(project, name), old_files.get(name); current = target.read_bytes() if target.exists() else None
        owner = ownership(name)
        if (name == ".claude/settings.json" and current is not None and name in new_files):
            try:
                merged, added = add_missing_esx_hooks(current, new_files[name])
            except ValueError as exc:
                conflicts.append({"path": name, "reason": f"cannot add new ESX hooks: {exc}"}); continue
            if added:
                rows.append({"path": name, "ownership": owner, "action": "add-esx-hooks", "added_hooks": added,
                             "before_sha256": sha(current), "result_sha256": sha(merged),
                             "master_sha256": sha(new_files[name]), "content": merged}); continue
        if owner == "project" and not (old is None and current is None and name in new_files):
            rows.append({"path": name, "ownership": owner, "action": "preserve",
                         "before_sha256": sha(current) if current is not None else None,
                         "result_sha256": sha(current) if current is not None else None,
                         "master_sha256": sha(new_files[name]) if name in new_files else None, "content": current}); continue
        if old is None:
            incoming = new_files[name]
            if current is None: result, action = incoming, "create"
            elif current == incoming: result, action = current, "adopt"
            else: conflicts.append({"path": name, "reason": "new master-managed path already exists with different content"}); continue
        else:
            digest = old.get("baseline_sha256"); baseline_path = object_path(project, digest)
            if not digest or not baseline_path.is_file() or sha(baseline_path.read_bytes()) != digest:
                conflicts.append({"path": name, "reason": "recorded baseline object is missing or corrupt"}); continue
            baseline = baseline_path.read_bytes()
            if name not in new_files:
                if current is None: result, action = None, "already-removed"
                elif current == baseline: result, action = None, "remove"
                else: conflicts.append({"path": name, "reason": "master removed a locally modified managed file"}); continue
            else:
                incoming = new_files[name]
                if current is None: conflicts.append({"path": name, "reason": "managed file was deleted locally"}); continue
                if current == baseline: result, action = incoming, "update" if incoming != current else "unchanged"
                elif incoming == baseline or current == incoming: result, action = current, "preserve" if incoming == baseline else "already-current"
                else:
                    result, clean = three_way(current, baseline, incoming)
                    if not clean:
                        conflicts.append({"path": name, "reason": "project and master edits overlap",
                                          "conflict_preview": result.decode(errors="replace")[:4000]}); continue
                    action = "three-way-merge"
        rows.append({"path": name, "ownership": owner, "action": action,
                     "before_sha256": sha(current) if current is not None else None,
                     "result_sha256": sha(result) if result is not None else None,
                     "master_sha256": sha(new_files[name]) if name in new_files else None, "content": result})
    return {"action": "upgrade", "project": str(project), "master": str(master),
            "from_version": manifest["version"], "to_version": target_version, "files": rows, "conflicts": conflicts}

def adopt_plan(project, master=MASTER):
    """Register a verified pre-versioned ESX deployment without replacing it."""
    project, master = Path(project).resolve(), Path(master).resolve()
    if (project / LOCAL / "manifest.json").exists():
        raise ValueError("project already has versioned ESX metadata")
    rows, conflicts = [], []
    for name, incoming in template_files(master).items():
        target = inside(project, name); current = target.read_bytes() if target.exists() else None
        if current is None and ownership(name) == "framework":
            rows.append({"path": name, "ownership": "framework", "action": "create",
                         "before_sha256": None, "result_sha256": sha(incoming),
                         "master_sha256": sha(incoming), "content": incoming})
        else:
            rows.append({"path": name, "ownership": ownership(name), "action": "adopt",
                         "before_sha256": sha(current) if current is not None else None,
                         "result_sha256": sha(current) if current is not None else None,
                         "master_sha256": sha(incoming), "content": current})
    return {"action": "adopt", "project": str(project), "master": str(master), "from_version": "unversioned",
            "to_version": version(master), "files": rows, "conflicts": conflicts}

def public_plan(plan):
    return {**{k: v for k, v in plan.items() if k != "files"},
            "files": [{k: v for k, v in row.items() if k != "content"} for row in plan["files"]],
            "summary": {action: sum(r["action"] == action for r in plan["files"])
                        for action in sorted({r["action"] for r in plan["files"]})}}

def apply_plan(plan):
    if plan["conflicts"]: raise ValueError(f"refusing apply with {len(plan['conflicts'])} unresolved conflict(s)")
    project, master = Path(plan["project"]), Path(plan["master"]); local = project / LOCAL
    with project_lock(project):
        for row in plan["files"]:
            target = inside(project, row["path"]); actual = sha(target.read_bytes()) if target.exists() else None
            if actual != row["before_sha256"]: raise ValueError(f"project changed after planning: {row['path']}")
        dep_id = deployment_id(plan["action"]); backup = local / "backups" / dep_id
        for row in plan["files"]:
            if row["action"] in ("create", "adopt", "unchanged", "already-current", "already-removed", "preserve"): continue
            target = inside(project, row["path"])
            if target.exists():
                saved = backup / row["path"]; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, saved)
        for row in plan["files"]:
            target, data = inside(project, row["path"]), row["content"]
            if data is None:
                if target.exists(): target.unlink()
            elif row["action"] not in ("unchanged", "already-current", "adopt", "preserve"):
                mode = target.stat().st_mode & 0o777 if target.exists() else 0o644; atomic(target, data); target.chmod(mode)
        manifest_files = {}; new_master = template_files(master)
        for row in plan["files"]:
            target = inside(project, row["path"])
            if not target.exists(): continue
            current = target.read_bytes()
            # A framework baseline is the master side of the merge. The installed
            # bytes can also contain a project customization; using those as the
            # next baseline would silently reclassify that customization as ESX.
            baseline = (new_master[row["path"]] if row["ownership"] == "framework"
                        and row["path"] in new_master else current)
            digest = store_object(project, baseline)
            manifest_files[row["path"]] = {"ownership": row["ownership"], "installed_sha256": sha(current),
                "baseline_sha256": digest, "master_sha256": sha(new_master[row["path"]]) if row["path"] in new_master else None}
        config = base_config(project, master, local_config(project).get("installed_at"))
        manifest = {"schema_version": SCHEMA, "version": plan["to_version"], "master_repository": "external-master",
                    "master_fingerprint": master_fingerprint(master),
                    "updated_at": now(), "files": manifest_files}
        record = public_plan(plan); record["project"] = "."; record["master"] = "external-master"
        record.update(schema_version=SCHEMA, deployment_id=dep_id, applied_at=now(),
                      status="applied", backup_directory=str(backup.relative_to(project)) if backup.exists() else None)
        atomic(local / "version", (plan["to_version"] + "\n").encode()); atomic(local / "config.json", json_bytes(config))
        atomic(local / "manifest.json", json_bytes(manifest)); atomic(local / "deployments" / f"{dep_id}.json", json_bytes(record))
        readme = ("# Local ESX deployment metadata\n\nThis directory records the installed ESX version, project configuration, "
                  "content-addressed baselines, rollback backups and deployment history. It contains no framework copy. "
                  "Use the external master repository's esx_upgrade.py; do not edit hashes or baselines manually.\n")
        atomic(local / "README.md", readme.encode())
        return record

def parse_request(args, action):
    if args.request:
        request = json.loads(Path(args.request).read_text())
        if request.get("action") != action: raise ValueError(f"request action must be {action!r}")
        args.project = request.get("project"); args.apply = bool(request.get("apply", False))
        if action == "upgrade": args.adopt_existing = bool(request.get("adopt_existing", False))
        if action == "install" and request.get("config"): args.config = request["config"]
    if not args.project: raise ValueError("--project is required (directly or in --request JSON)")
    return args

def parser(action):
    p = argparse.ArgumentParser(description=f"{action.title()} ESX from the one master repository")
    p.add_argument("--project", type=Path, help="receiving project root"); p.add_argument("--request", type=Path, help="agent-friendly JSON request")
    p.add_argument("--apply", action="store_true", help="apply the complete conflict-free plan")
    if action == "install": p.add_argument("--config", type=Path, help="completed esx/project.json")
    else: p.add_argument("--adopt-existing", action="store_true", help="register a verified unversioned installation")
    return p

def run_cli(action, argv=None):
    p = parser(action); args = p.parse_args(argv)
    try:
        args = parse_request(args, action); config = json.loads(Path(args.config).read_text()) if action == "install" and args.config else None
        plan = (install_plan(args.project, configuration=config) if action == "install" else
                adopt_plan(args.project) if args.adopt_existing else upgrade_plan(args.project))
        print(json.dumps(apply_plan(plan) if args.apply else public_plan(plan), indent=2)); return 0 if not plan["conflicts"] else 2
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"ESX {action}: {exc}", file=sys.stderr); return 1

def install_cli(argv=None): return run_cli("install", argv)
def upgrade_cli(argv=None): return run_cli("upgrade", argv)
