"""Run project checks and reuse content-matching successful evidence.

Commands are argv arrays and execute without a shell. Failures, empty suites,
timeouts, source drift and modified logs cannot establish a passing gate.
"""
import argparse
import fcntl
import json
import os
import signal
import threading
from pathlib import Path
import subprocess
import sys
import time
import uuid

from project import (STATE, atomic_json, command, config, digest, environment,
                     file_hash, json_file, local, now, require, source_signature)


def fingerprint(root, suite, commands):
    cfg = config(root)
    return digest({'source': source_signature(root, scientific=suite != 'structural'),
                   'framework': {p.name: file_hash(p) for p in (root / 'tools/esx').glob('*.py')},
                   'commands': commands, 'environment': environment(root, cfg), 'suite': suite})


def load_evidence(root, ref):
    require(isinstance(ref, dict), 'verification reference is required')
    sha = ref.get('sha256')
    require(ref.get('path') == f'{STATE}/verification/{sha}.json', 'invalid verification artifact path')
    record = json_file(root, ref['path'])
    require(digest(record) == sha, 'verification artifact was modified')
    require(record.get('exit') == 0 and type(record.get('exit')) is int and record.get('stable') is True,
            'verification did not finish successfully on a stable candidate')
    require(record.get('commands'), 'verification ran no commands')
    require(record['signature'] == fingerprint(root, record['suite'], record['commands']), 'verification evidence is stale')
    require(file_hash(local(root, record['log'])) == record['log_sha256'], 'verification log is missing or modified')
    return record


def run(root, suite, owner, fresh=False, override=None, _lease=None):
    """Serialize matching suites; independent fresh runs execute after acquiring the lock."""
    if suite == 'scientific':
        import final_verification
        final_verification.authorize(root, _lease)
    lock = local(root, f'{STATE}/verification/lock-{digest([suite, override])}')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if suite == 'scientific':
            final_verification.authorize(root, _lease)
        return _run(root, suite, owner, fresh, override)


def _run(root, suite, owner, fresh, override):
    cfg = config(root)
    require(suite in cfg['verification'], f'unknown verification suite: {suite}')
    require(isinstance(owner, str) and owner.strip(), 'record the actual verification owner')
    require(override is None or suite == 'focused', 'custom commands are restricted to focused checks')
    commands = [override] if override else cfg['verification'][suite]
    require(commands and all(isinstance(a, list) and a and all(isinstance(s, str) and s for s in a) for a in commands), 'verification suite is empty or invalid')
    signature = fingerprint(root, suite, commands)
    index = local(root, f'{STATE}/verification/cache-{digest([suite, commands])}.json')
    if not fresh and index.exists():
        ref = json.loads(index.read_text())
        try:
            record = load_evidence(root, ref)
            if record['signature'] == signature:
                return {'status': 'REUSED EVIDENCE', 'evidence': ref, 'original_finished_at': record['finished_at']}
        except (ValueError, OSError, KeyError):
            pass
    # A failed or interrupted fresh attempt must not expose an older PASS for
    # the same fingerprint on the next invocation.
    index.unlink(missing_ok=True)
    log = f'{STATE}/verification/run-{uuid.uuid4().hex}.log'
    path = local(root, log)
    path.parent.mkdir(parents=True, exist_ok=True)
    started_at, start, rc = now(), time.monotonic(), 0
    interrupted = None
    with path.open('w') as stream:
        for argv in commands:
            stream.write('COMMAND ' + json.dumps(command(argv)) + '\n')
            stream.flush()
            try:
                rc = execute(command(argv), root, stream, cfg.get('command_timeout_seconds', 3600))
            except (OSError, subprocess.TimeoutExpired) as exc:
                stream.write(str(exc) + '\n')
                rc = 124
            except (KeyboardInterrupt, InterruptedError) as exc:
                stream.write('INTERRUPTED ' + repr(exc) + '\n')
                rc, interrupted = 130, exc
            if rc != 0:
                break
    try:
        stable = signature == fingerprint(root, suite, commands)
    except (ValueError, OSError, subprocess.SubprocessError):
        stable = False
    record = {'version': 1, 'suite': suite, 'owner': owner, 'commands': commands,
              'signature': signature, 'started_at': started_at, 'finished_at': now(),
              'elapsed_seconds': time.monotonic() - start, 'exit': rc, 'stable': stable,
              'log': log, 'log_sha256': file_hash(path)}
    sha = digest(record)
    ref = {'path': f'{STATE}/verification/{sha}.json', 'sha256': sha}
    atomic_json(local(root, ref['path']), record)
    if interrupted is not None:
        raise interrupted
    require(rc == 0 and stable, f'verification failed or source changed; inspect {log}')
    atomic_json(index, ref)
    return {'status': 'EXECUTED PASS', 'evidence': ref, 'elapsed_seconds': record['elapsed_seconds']}


def execute(argv, root, stream, timeout):
    """Bound a complete process group and remove descendants on every exit path."""
    process = subprocess.Popen(argv, cwd=root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    previous = {}
    def interrupt(signum, frame):
        raise InterruptedError(f'verification received signal {signum}')
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupt)
    try:
        return process.wait(timeout=timeout)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--suite', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--command', type=json.loads, help='one focused argv array')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root.resolve(), args.suite, args.owner, args.fresh, args.command), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'ESX verification: {exc}\n')


if __name__ == '__main__':
    main()
