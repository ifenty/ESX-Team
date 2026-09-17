#!/usr/bin/env python3
"""Compatibility interface for the versioned ESX installer.

New callers should use ``esx_install.py --project PROJECT [--apply]``. Existing
tests and scripts may continue importing :func:`deploy`.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from esx_manager import LOCAL, apply_plan, install_plan, public_plan, upgrade_plan


def deploy(destination, apply=False, configuration=None):
    installed = Path(destination) / LOCAL / "manifest.json"
    plan = upgrade_plan(destination) if installed.exists() else install_plan(destination, configuration=configuration)
    inert = {"unchanged", "already-current", "adopt", "preserve", "already-removed"}
    changed = [row["path"] for row in plan["files"] if row["action"] not in inert]
    if plan["conflicts"]:
        raise ValueError("collision: " + "; ".join(x["reason"] for x in plan["conflicts"]))
    if apply and changed:
        apply_plan(plan)
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.config.read_text()) if args.config else None
        plan = install_plan(args.destination, configuration=cfg)
        value = apply_plan(plan) if args.apply else public_plan(plan)
        print(json.dumps(value, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"ESX deployment: {exc}\n")
