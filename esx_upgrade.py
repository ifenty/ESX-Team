#!/usr/bin/env python3
"""Upgrade an ESX project installation from this master repository."""
from esx_manager import upgrade_cli

if __name__ == "__main__":
    raise SystemExit(upgrade_cli())
