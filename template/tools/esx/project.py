"""Project configuration, path boundaries and reproducible source signatures.

Framework filenames are stable across deployments. Scientific paths, commands,
inputs and environment probes belong to esx/project.json. No module imports a
project's scientific code or sends external messages.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

STATE = 'devel-loop/loop_state'
FRAMEWORK_PATHS = ['tools/esx', '.claude', 'devel-loop', 'docs', 'esx', 'CLAUDE.md', '.gitignore']
EXCLUDED_PARTS = {'.git', '__pycache__', '.pytest_cache', 'loop_state'}
ROLES = ('arch', 'bob', 'richard', 'scout', 'prober', 'bisector', 'auditor')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def local(root, name):
    """Resolve a relative project path; reject traversal and external symlinks."""
    root = Path(root).resolve()
    require(isinstance(name, str) and name and name != '.' and not Path(name).is_absolute()
            and '..' not in Path(name).parts, f'invalid project path: {name!r}')
    path = root / name
    require(path.resolve().is_relative_to(root), f'path leaves project: {name}')
    return path


def config(root, ready=True):
    cfg = json.loads(local(root, 'esx/project.json').read_text())
    require(isinstance(cfg, dict), 'project.json must be an object')
    require(cfg.get('version') == 1, 'project.json version must be 1')
    for key in ('source_paths', 'test_paths', 'configuration_paths', 'output_paths', 'external_inputs', 'environment_variables'):
        require(isinstance(cfg.get(key), list) and all(isinstance(x, str) and x for x in cfg[key]), f'{key} must be a list of paths/names')
    for name in cfg['source_paths'] + cfg['test_paths'] + cfg['configuration_paths'] + cfg['output_paths']:
        local(root, name)
    for output in cfg['output_paths']:
        for source in cfg['source_paths'] + cfg['test_paths'] + cfg['configuration_paths'] + FRAMEWORK_PATHS:
            require(not (source == output or source.startswith(output.rstrip('/') + '/')),
                    f'output path would hide configured source/framework: {output}')
    require(isinstance(cfg.get('verification'), dict), 'verification must define named suites')
    for suite, commands in cfg['verification'].items():
        require(isinstance(commands, list), f'verification.{suite} must be a list of argv arrays')
        for argv in commands:
            require(isinstance(argv, list) and argv and all(isinstance(s, str) and s for s in argv), f'{suite}: invalid command')
    require(isinstance(cfg.get('toolchain_commands'), list), 'toolchain_commands must be argv arrays')
    for argv in cfg['toolchain_commands']:
        require(isinstance(argv, list) and argv and all(isinstance(s, str) and s for s in argv), 'invalid toolchain command')
    require(type(cfg.get('command_timeout_seconds')) in (int, float) and math.isfinite(cfg['command_timeout_seconds']) and cfg['command_timeout_seconds'] > 0,
            'command_timeout_seconds must be finite and positive')
    if ready:
        for key in ('project_id', 'project_name', 'mission'):
            require(isinstance(cfg.get(key), str) and cfg[key].strip(), f'complete esx/project.json: {key}')
        require(cfg['source_paths'] and cfg['test_paths'], 'configure source_paths and test_paths')
        require(cfg['verification'].get('structural') and cfg['verification'].get('scientific'),
                'configure nonempty structural and scientific acceptance suites')
        require(cfg.get('toolchain_commands'), 'configure toolchain_commands')
        for name in cfg['source_paths'] + cfg['test_paths'] + cfg['configuration_paths']:
            require(local(root, name).exists(), f'configured input is missing: {name}')
        for name in ('esx/project_profile.md', 'docs/code_map.md'):
            require('TODO_ESX' not in local(root, name).read_text(), f'complete {name}')
    return cfg


def mutable_loop_path(name):
    """Keep local loop state, locks, logs and terminal archives outside candidates."""
    return name.startswith(('.claude/esx-loop', '.claude/ralph-loop'))


def selected(name, cfg, scientific=False):
    if EXCLUDED_PARTS.intersection(Path(name).parts) or name.endswith(('.pyc', '.pyo')):
        return False
    if mutable_loop_path(name):
        return False
    if name == '.claude/worktrees' or name.startswith('.claude/worktrees/'):
        return False
    if any(name == p or name.startswith(p.rstrip('/') + '/') for p in cfg['output_paths']):
        return False
    roots = cfg['source_paths'] + cfg['test_paths'] + cfg['configuration_paths']
    roots += ['esx/project.json'] if scientific else FRAMEWORK_PATHS
    return any(name == p or name.startswith(p.rstrip('/') + '/') for p in roots)


def inventory_paths(root, cfg, scientific=False):
    """Include additions, deletions and ignored source through explicit path roots.

    Output directories must be separate from source/configuration roots. A source
    symlink leaving the project is refused; external datasets use external_inputs.
    """
    root = Path(root).resolve()
    roots = cfg['source_paths'] + cfg['test_paths'] + cfg['configuration_paths']
    roots += ['esx/project.json'] if scientific else FRAMEWORK_PATHS
    names = set()
    for name in roots:
        path = local(root, name)
        candidates = []
        if path.is_dir():
            require(not path.is_symlink(), f'configure the concrete directory instead of a symlink: {name}')
            for directory, folders, files in os.walk(path):
                folders[:] = [f for f in folders if selected((Path(directory) / f).relative_to(root).as_posix(), cfg, scientific)]
                for folder in folders:
                    require(not (Path(directory) / folder).is_symlink(), f'source directory symlink is not inventoried: {directory}/{folder}')
                candidates.extend(Path(directory) / f for f in files)
        else:
            candidates = [path]
        for candidate in candidates:
            rel = candidate.relative_to(root).as_posix()
            if selected(rel, cfg, scientific) and (candidate.is_file() or candidate.is_symlink()):
                local(root, rel)
                names.add(rel)
    return sorted(names)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_signature(root, scientific=False):
    root = Path(root).resolve()
    cfg = config(root)
    return digest({p: {'sha256': file_hash(local(root, p)), 'mode': local(root, p).stat().st_mode,
                       'link': os.readlink(root / p) if (root / p).is_symlink() else None}
                   for p in inventory_paths(root, cfg, scientific)})


def command(argv):
    return [sys.executable if s == '{python}' else s for s in argv]


def environment(root, cfg):
    """Measure declared tools, environment and actual external-input file bytes.

    Use small qualification datasets for routine checks. No unverified dataset
    checksum is accepted as a substitute for reading its configured input file.
    """
    probes = []
    for argv in cfg['toolchain_commands']:
        run = subprocess.run(command(argv), cwd=root, capture_output=True, text=True, timeout=30)
        require(run.returncode == 0, f'toolchain probe failed: {argv}')
        probes.append({'argv': command(argv), 'stdout': run.stdout, 'stderr': run.stderr})
    inputs = {}
    for name in cfg['external_inputs']:
        path = Path(name) if Path(name).is_absolute() else root / name
        inputs[str(path.resolve())] = file_hash(path)
    return {'python': sys.version, 'python_optimization': sys.flags.optimize,
            'executable': sys.executable, 'platform': platform.platform(),
            'variables': {k: os.environ.get(k) for k in cfg['environment_variables']},
            'tools': probes, 'inputs': inputs}


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def atomic_bytes(path, data):
    """Publish a complete file in its directory; failed replacement keeps old bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def json_file(root, name):
    return json.loads(local(root, name).read_text())
