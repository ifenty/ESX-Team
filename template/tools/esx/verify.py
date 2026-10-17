"""Run project checks and reuse content-matching successful evidence.

Commands are argv arrays and execute without a shell. Failures, empty suites,
timeouts, source drift and modified logs cannot establish a passing gate.
"""
import argparse
import fcntl
import json
import os
import re
import shlex
import signal
import threading
from pathlib import Path
import subprocess
import sys
import time
import uuid

from project import (STATE, atomic_json, command, config, digest, environment,
                     file_hash, json_file, local, named_sha, now, require, source_signature)


class RunInterrupted(ValueError):
    """The suite did not finish: no verdict exists about the candidate."""
    def __init__(self, message, log, reason):
        super().__init__(message)
        self.log, self.reason = log, reason


class SourceChanged(ValueError):
    """Inputs moved under the run, so its outcome describes no single candidate."""
    def __init__(self, message, log=None):
        super().__init__(message)
        self.log = log


# pytest ends every completed session with e.g. "==== 3 passed in 0.12s ====".
PYTEST_SUMMARY = re.compile(r'^=+ .+ in [0-9.]+s\b.*=+\s*$', re.M)
FAILURE_LINE = re.compile(r'\b(FAILED|ERROR)\b')


def failure_lines(text):
    """Count failure-marked output lines, excluding the verifier's COMMAND echoes."""
    return sum(1 for line in text.splitlines() if not line.startswith('COMMAND ') and FAILURE_LINE.search(line))


def interruption(rc, text):
    """Name why a non-zero run never reached a verdict, or return None."""
    if rc == 0:
        return None
    if rc < 0:
        return f'child terminated by signal {-rc}'
    if 'test session starts' in text and not PYTEST_SUMMARY.search(text):
        return f'exit {rc} before the pytest summary line'
    return None


def fingerprint(root, suite, commands):
    cfg = config(root)
    return digest({'source': source_signature(root, scientific=suite != 'structural'),
                   'framework': {p.name: file_hash(p) for p in (root / 'tools/esx').glob('*.py')},
                   'commands': commands, 'environment': environment(root, cfg), 'suite': suite})


def structural_evidence(root):
    """Read current complete structural PASS without executing another suite."""
    commands = config(root)['verification']['structural']
    ref = json_file(root, f'{STATE}/verification/cache-{digest(["structural", commands])}.json')
    evidence = load_evidence(root, ref)
    require(evidence['suite'] == 'structural' and evidence['commands'] == commands,
            'structural receipt must cover the complete configured suite')
    return ref


def load_evidence(root, ref):
    """A suite receipt: a single-suite record, or in a grouped project the aggregate.

    A group record is refused here: it covers only part of the suite, so it can
    never stand for the scientific suite on its own.
    """
    return _load(root, ref)


def groups_of(cfg):
    """The configured scientific groups, or None for a single-suite project."""
    return cfg['verification'].get('scientific_groups')


def _load(root, ref, allow_group=False):
    import self_improvement
    if (Path(root) / self_improvement.OPEN).exists():
        errors = self_improvement.validate(root)
        require(not errors, '; '.join(errors))
    require(isinstance(ref, dict) and ref.get('path') and ref.get('sha256'),
            "verification reference is required -- a plain command (e.g. bare pytest) has no evidence file of its "
            "own; run it through verify.py (e.g. 'verify.py --suite focused --owner <id> --fresh') and cite that "
            "command's own returned evidence reference instead")
    sha = ref.get('sha256')
    require(ref.get('path') == f'{STATE}/verification/{sha}.json',
            f"invalid verification artifact path: the path names {named_sha(ref.get('path'))} but sha256 is {sha}")
    record = json_file(root, ref['path'])
    require(digest(record) == sha, 'verification artifact was modified')
    require(record.get('exit') == 0 and type(record.get('exit')) is int and record.get('stable') is True,
            'verification did not finish successfully on a stable candidate')
    require(record.get('commands'), 'verification ran no commands')
    require(record['signature'] == fingerprint(root, record['suite'], record['commands']),
            f"verification evidence is stale (sealed {ref['path']}, suite {record['suite']}, owner "
            f"{record.get('owner')}); rerun: {rerun_command(record)}")
    if record.get('groups') is not None:
        _check_aggregate(root, record, ref)
        return record
    if record['suite'] == 'scientific' and not record.get('group') and groups_of(config(root)):
        raise ValueError('this project configures scientific_groups: a flat scientific record is not accepted; '
                         'run final_verification.py run and cite its aggregate')
    require(allow_group or record.get('group') is None,
            f"evidence {ref.get('path')} is the record of scientific group {record.get('group')}, not of the whole suite; "
            'cite the aggregate returned by final_verification.py run')
    require(file_hash(local(root, record['log'])) == record['log_sha256'], 'verification log is missing or modified')
    return record


def _check_aggregate(root, record, ref):
    """An aggregate stands for the suite only while every configured group is intact, passing, current and ours."""
    configured = groups_of(config(root))
    require(configured, 'aggregate scientific evidence in a project that configures no scientific_groups')
    require(record['suite'] == 'scientific' and record.get('group') is None, 'aggregate must be for the scientific suite')
    listed = record['groups']
    require(isinstance(listed, list) and all(isinstance(g, dict) for g in listed)
            and [g.get('name') for g in listed] == [g['name'] for g in configured],
            'aggregate groups differ from the configured scientific groups (missing, reordered or renamed)')
    flat = []
    for entry, group in zip(listed, configured):
        leaf = _load(root, entry.get('evidence'), allow_group=True)
        require(leaf.get('group') == group['name'] and leaf['suite'] == 'scientific' and leaf.get('groups') is None,
                f"group {group['name']}: evidence belongs to another group or is not a group record")
        require(leaf['commands'] == group['commands'], f"group {group['name']}: its commands differ from the configuration")
        require(leaf['owner'] == record.get('owner'), f"group {group['name']}: owned by {leaf['owner']}, not by the aggregate's owner {record.get('owner')}")
        flat += leaf['commands']
    require(record['commands'] == flat == config(root)['verification']['scientific'] and
            record.get('command_digest') == digest(flat), 'aggregate commands differ from the configured scientific suite')


def rerun_command(record):
    """The command line that reproduces a record's suite under its owner."""
    if record.get('groups') is not None:
        return ('python3 tools/esx/final_verification.py run --review devel-loop/loop_state/review.json '
                f"--owner {shlex.quote(str(record.get('owner')))}")
    argv = ['python3', 'tools/esx/verify.py', '--suite', record['suite'], '--owner', str(record.get('owner')), '--fresh']
    if record.get('group'):
        argv += ['--group', record['group']]
    if record['suite'] == 'focused' and len(record['commands']) == 1:
        argv += ['--command', json.dumps(record['commands'][0])]
    return ' '.join(shlex.quote(a) for a in argv)


def stale_evidence(root, owner):
    """The owner's latest record per suite and commands whose signature differs from the current fingerprint."""
    root = Path(root)
    latest = {}
    for path in sorted((root / STATE / 'verification').glob('*.json')):
        if not re.fullmatch(r'[0-9a-f]{64}', path.stem):
            continue
        try:
            record = json.loads(path.read_text())
            if record.get('owner') != owner or digest(record) != path.stem:
                continue
            key = digest([record['suite'], record['commands']])
            if key not in latest or record['finished_at'] > latest[key][1]['finished_at']:
                latest[key] = (path, record)
        except (ValueError, OSError, KeyError, TypeError, AttributeError):
            continue
    stale = []
    for path, record in latest.values():
        try:
            current = fingerprint(root, record['suite'], record['commands'])
        except (ValueError, OSError, KeyError, subprocess.SubprocessError):
            continue
        if record['signature'] != current:
            stale.append({'evidence': {'path': f'{STATE}/verification/{path.name}', 'sha256': path.stem},
                          'suite': record['suite'], 'finished_at': record['finished_at'],
                          'rerun': rerun_command(record)})
    return stale


def intact_owner(root, ref):
    """Owner recorded in an unmodified evidence file, or None; freshness is not judged here."""
    try:
        sha = ref.get('sha256')
        if ref.get('path') != f'{STATE}/verification/{sha}.json':
            return None
        record = json_file(root, ref['path'])
        return record.get('owner') if digest(record) == sha else None
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return None


def run(root, suite, owner, fresh=False, override=None, _lease=None, group=None):
    """Serialize matching suites; independent fresh runs execute after acquiring the lock.

    In a project with ``scientific_groups`` the scientific suite is a sequence of
    groups: ``group`` runs exactly one of them (reusing its intact current PASS
    unless ``fresh``), and no group runs every group in order and seals the aggregate.
    """
    import team_accounting
    if group is not None or suite == 'scientific':
        groups = groups_of(config(root)) if suite == 'scientific' else None
        require(group is None or suite == 'scientific' and groups,
                '--group needs the scientific suite of a project that configures scientific_groups')
        require(group is None or group in [g['name'] for g in groups],
                f"unknown scientific group {group!r}; configured: {', '.join(g['name'] for g in groups or [])}")
        if groups and group is None:
            require(override is None, 'custom commands are restricted to focused checks')
            return run_groups(root, owner, fresh, _lease)
    if suite == 'structural':
        import self_improvement
        if (Path(root) / self_improvement.OPEN).exists():
            errors = self_improvement.validate(root)
            require(not errors, '; '.join(errors))
    if suite == 'scientific':
        import final_verification
        final_verification.authorize(root, _lease)
    lock = local(root, f'{STATE}/verification/lock-{digest([suite, override] + ([group] if group else []))}')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if suite == 'scientific':
            final_verification.authorize(root, _lease)
        active = local(root, f'{STATE}/issue-start.json')
        issue = json.loads(active.read_text()).get('id') if active.exists() else None
        with team_accounting.phase(root, issue, 'verification', role=owner if isinstance(owner, str) else None):
            return _run(root, suite, owner, fresh, override, group)


def group_commands(cfg, name):
    return next(g['commands'] for g in groups_of(cfg) if g['name'] == name)


def group_pointer(root, commands, name):
    return local(root, f'{STATE}/verification/cache-{digest(["scientific", commands, name])}.json')


def aggregate_pointer(root, cfg):
    return local(root, f"{STATE}/verification/aggregate-{digest(['scientific', cfg['verification']['scientific']])}.json")


def _run(root, suite, owner, fresh, override, group=None):
    cfg = config(root)
    require(suite in cfg['verification'] and suite != 'scientific_groups', f'unknown verification suite: {suite}')
    require(group is None or suite == 'scientific', 'groups belong to the scientific suite')
    require(not (suite == 'scientific' and groups_of(cfg) and group is None),
            'the scientific suite of this project is grouped; run it through final_verification.py run or verify.py without --command')
    require(isinstance(owner, str) and owner.strip(), 'record the actual verification owner')
    require(override is None or suite == 'focused', 'custom commands are restricted to focused checks')
    commands = group_commands(cfg, group) if group else [override] if override else cfg['verification'][suite]
    require(commands and all(isinstance(a, list) and a and all(isinstance(s, str) and s for s in a) for a in commands), 'verification suite is empty or invalid')
    signature = fingerprint(root, suite, commands)
    index = group_pointer(root, commands, group) if group else local(root, f'{STATE}/verification/cache-{digest([suite, commands])}.json')
    if not fresh and index.exists():
        ref = json.loads(index.read_text())
        try:
            record = _load(root, ref, allow_group=bool(group))
            # A group is reused only for the same group and the same accountable owner.
            if record['signature'] == signature and (not group or (record.get('group'), record['owner']) == (group, owner)):
                return {'status': 'REUSED EVIDENCE', 'evidence': ref, 'original_finished_at': record['finished_at']}
        except (ValueError, OSError, KeyError):
            pass
    # A failed or interrupted fresh attempt must not expose an older PASS for
    # the same fingerprint on the next invocation.
    index.unlink(missing_ok=True)
    if group:
        # Re-running any group voids the aggregate and the receipt that cites it,
        # so a later failure cannot leave an older qualification usable.
        aggregate_pointer(root, cfg).unlink(missing_ok=True)
        local(root, f'{STATE}/final-verification/current.json').unlink(missing_ok=True)
    log = f'{STATE}/verification/run-{uuid.uuid4().hex}.log'
    path = local(root, log)
    path.parent.mkdir(parents=True, exist_ok=True)
    started_at, start, rc = now(), time.monotonic(), 0
    interrupted = timed_out = None
    with path.open('w') as stream:
        for argv in commands:
            stream.write('COMMAND ' + json.dumps(command(argv, cfg)) + '\n')
            stream.flush()
            try:
                rc = execute(command(argv, cfg), root, stream, cfg.get('command_timeout_seconds', 3600))
            except (KeyboardInterrupt, InterruptedError) as exc:
                # First: InterruptedError is an OSError, and a signal is not a failure to launch.
                stream.write('INTERRUPTED ' + repr(exc) + '\n')
                rc, interrupted = 130, exc
            except (OSError, subprocess.TimeoutExpired) as exc:
                stream.write(str(exc) + '\n')
                rc, timed_out = 124, True
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
    if group:
        record['group'] = group
    sha = digest(record)
    ref = {'path': f'{STATE}/verification/{sha}.json', 'sha256': sha}
    atomic_json(local(root, ref['path']), record)
    if interrupted is not None:
        interrupted.log = log
        raise interrupted
    text = path.read_text(errors='replace')
    # A timeout is the configured verdict on a hung candidate, not an interruption.
    reason = None if timed_out else interruption(rc, text)
    if reason:
        raise RunInterrupted(f'verification interrupted ({reason}); {failure_lines(text)} failure lines '
                             f'were logged and the suite reached no verdict; inspect {log}', log, reason)
    if not stable:
        raise SourceChanged(f'source changed during verification (exit {rc}); inspect {log}', log)
    if rc != 0:
        failure = ValueError(f'verification failed (exit {rc}); inspect {log}')
        failure.log = log
        raise failure
    atomic_json(index, ref)
    return {'status': 'EXECUTED PASS', 'evidence': ref, 'elapsed_seconds': record['elapsed_seconds']}


def run_groups(root, owner, fresh, lease):
    """Run (or reuse) every scientific group in order, then seal the aggregate.

    A failed or interrupted group raises with its own log and leaves the groups
    before it reusable; re-running resumes at that group.
    """
    root = Path(root)
    cfg = config(root)
    flat = cfg['verification']['scientific']
    aggregate_pointer(root, cfg).unlink(missing_ok=True)
    results = []
    for group in groups_of(cfg):
        results.append((group, run(root, 'scientific', owner, fresh, _lease=lease, group=group['name'])))
    records = []
    for group, result in results:
        try:
            records.append(_load(root, result['evidence'], allow_group=True))
        except ValueError as exc:
            raise SourceChanged(f"scientific group {group['name']} no longer matches the candidate after the grouped run: {exc}",
                                json_file(root, result['evidence']['path']).get('log')) from exc
    aggregate = {'version': 1, 'suite': 'scientific', 'owner': owner, 'commands': flat, 'command_digest': digest(flat),
                 'signature': fingerprint(root, 'scientific', flat),
                 'groups': [{'name': g['name'], 'evidence': r['evidence']} for g, r in results],
                 'started_at': min(r['started_at'] for r in records), 'finished_at': now(),
                 'elapsed_seconds': sum(r['elapsed_seconds'] for r in records), 'exit': 0, 'stable': True}
    sha = digest(aggregate)
    ref = {'path': f'{STATE}/verification/{sha}.json', 'sha256': sha}
    atomic_json(local(root, ref['path']), aggregate)
    _load(root, ref)
    atomic_json(aggregate_pointer(root, cfg), ref)
    executed = [r for _, r in results if r['status'] == 'EXECUTED PASS']
    return {'status': 'EXECUTED PASS' if executed else 'REUSED EVIDENCE', 'evidence': ref,
            'elapsed_seconds': sum(r['elapsed_seconds'] for r in executed),
            'groups': [{'name': g['name'], 'status': r['status'], 'evidence': r['evidence']} for g, r in results],
            'log': records[-1]['log']}


def group_status(root, owner):
    """Per-group state for the owner: current, missing (no passing evidence) or stale (with the reason)."""
    cfg = config(root)
    rows = []
    for group in groups_of(cfg) or []:
        pointer = group_pointer(root, group['commands'], group['name'])
        row = {'name': group['name'], 'status': 'missing'}
        if pointer.exists():
            try:
                ref = json.loads(pointer.read_text())
                record = _load(root, ref, allow_group=True)
                require(record.get('group') == group['name'], 'pointer names another group')
                require(record['owner'] == owner, f"owned by {record['owner']}, not {owner}")
                row.update(status='current', evidence=ref)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                row.update(status='stale', reason=str(exc)[:160])
        rows.append(row)
    return rows


def execute(argv, root, stream, timeout):
    """Bound a complete process group and remove descendants on every exit path."""
    previous = {}
    process = None
    def interrupt(signum, frame):
        raise InterruptedError(f'verification received signal {signum}')
    # Handlers go in before the child starts: a signal in between must interrupt
    # the run (and leave its record), not kill the runner.
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupt)
    try:
        process = subprocess.Popen(argv, cwd=root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        return process.wait(timeout=timeout)
    finally:
        try:
            if process is not None:
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
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--suite', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--command', type=json.loads, help='one focused argv array')
    parser.add_argument('--group', help='run one scientific group (projects with verification.scientific_groups)')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root.resolve(), args.suite, args.owner, args.fresh, args.command, group=args.group), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'ESX verification: {exc}\n')


if __name__ == '__main__':
    main()
