#!/usr/bin/env python3
"""Opt-in actual Claude /esx-loop qualification in a disposable configured project.

Runs one bounded loop with communication disabled. Captures actual tool calls and
fails if Claude asks for routine confirmation or leaves the loop active. This
qualifies command discovery and execution; it does not qualify Slack delivery.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
import deploy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='esx-command-smoke-'))
    deploy.deploy(root, apply=True)
    example = KIT / 'examples/periodic_diffusion'
    for name in ('src', 'tests'):
        shutil.copytree(example / name, root / name)
    for source, dest in [('project.json','esx/project.json'),('project_profile.md','esx/project_profile.md'),('code_map.md','docs/code_map.md')]:
        shutil.copyfile(example / source, root / dest)
    env = dict(os.environ)
    for key in ('CLAUDE_PROJECT_DIR','ESX_AGENT_RUNTIME_CHILD','ESX_RALPH_PROJECT_DIR','CLAUDECODE'):
        env.pop(key, None)
    argv = [args.claude, '-p', '--output-format', 'stream-json', '--verbose',
            '--max-budget-usd', '3', '--allowedTools', 'Bash(python3 *)', 'Read', 'Skill',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
    print(json.dumps({'scratch': str(root), 'argv': argv}), flush=True)
    with (root / 'smoke.jsonl').open('w') as out, (root / 'smoke.stderr').open('w') as err:
        run = subprocess.run(argv, input='/esx-loop --max-iterations 1', text=True,
                             cwd=root, env=env, stdout=out, stderr=err, timeout=args.timeout)
    rows = [json.loads(line) for line in (root / 'smoke.jsonl').read_text().splitlines() if line.startswith('{')]
    calls = [c for row in rows for c in row.get('message',{}).get('content',[]) if isinstance(c,dict) and c.get('type')=='tool_use']
    commands = [c.get('input',{}).get('command','') for c in calls if c.get('name')=='Bash']
    assert run.returncode == 0, f'Claude failed: {root}'
    assert not any(c.get('name') in ('AskUserQuestion','EnterPlanMode') for c in calls), f'routine confirmation requested: {root}'
    assert any('loop_control.py run' in c for c in commands), f'command did not start: {root}'
    assert any('loop_gate.py --next' in c for c in commands), f'command did not execute NEXT: {root}'
    assert not (root / '.claude/esx-loop.local.md').exists(), f'loop still active: {root}'
    assert list((root / '.claude').glob('esx-loop.local.md.end.*')), f'no terminal archive: {root}'
    print(json.dumps({'status':'PASS','scratch':str(root),'tool_calls':len(calls)}))


if __name__ == '__main__':
    main()
