#!/usr/bin/env python3
"""Run each portable regression module in an isolated process; no provider calls."""
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def main():
    started = time.monotonic()
    failures = []
    paths = sorted((ROOT / 'tests').glob('test_*.py'))
    if not paths:
        raise SystemExit('No regression modules found')
    for path in paths:
        print('Running ' + path.name, flush=True)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        run = subprocess.run([sys.executable, '-B', str(path)], cwd=ROOT, env=environment)
        if run.returncode:
            failures.append(path.name)
    print(f'{len(paths)} modules; {time.monotonic()-started:.2f} seconds; failures={failures}', flush=True)
    return bool(failures)

if __name__ == '__main__':
    raise SystemExit(main())
