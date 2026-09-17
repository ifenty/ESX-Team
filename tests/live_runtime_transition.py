#!/usr/bin/env python3
"""Opt-in, bounded real-Claude witness for retained configuration transitions.

Uses a disposable role and local settings. It changes no production hook, issue
or agent contract. The two role responses must demonstrate both retained memory
and the instruction marker from the updated role definition.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path(__file__).resolve().parents[1] / 'template/tools/esx/agent_runtime.py')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--claude', default='claude')
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error('output must be empty')
    root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.runtime.resolve().parent))
    spec = importlib.util.spec_from_file_location('agent_runtime', args.runtime)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    import runtime_recovery as recovery
    role = root / '.claude/agents/bob.md'
    role.parent.mkdir(parents=True)
    body = ('---\nname: bob\ndescription: Bounded runtime witness\nmodel: sonnet\ntools: Read\n---\n'
            'Return a fenced JSON footer with agent=bob, issue_id=LIVE-TRANSITION, correction_round from '
            'the assignment, marker equal to ROLE_MARKER, and remembered equal to the first token. '
            'Do only this transport witness. ROLE_MARKER=MARKER.\n')
    role.write_text(body.replace('MARKER.', 'FIRST.'))
    settings = root / '.claude/settings.json'
    settings.write_text(json.dumps({'permissions': {'allow': ['Read']}}))
    token = uuid.uuid4().hex
    first = runtime.run_turn(root, role='bob', issue='LIVE-TRANSITION',
        prompt='Remember this token for the continuation: '+token+'. Return the required footer.',
        executable=args.claude, timeout=55)
    if first['status'] != 'completed' or first['footer'].get('marker') != 'FIRST':
        raise RuntimeError('initial witness failed: '+json.dumps(first))
    role.write_text(body.replace('MARKER.', 'SECOND.'))
    settings.write_text(json.dumps({'permissions': {'allow': ['Read']}, 'env': {'ESX_TRANSITION_WITNESS': 'second'}}))
    # The compatibility check measures the intended fixture constraint. The live
    # continuation below separately establishes actual instruction reload behavior.
    check_path = root / 'compatibility.log'
    command = [sys.executable, '-c',
        "import json; from pathlib import Path; assert json.loads(Path('.claude/settings.json').read_text())['permissions']=={'allow':['Read']}; assert 'tools: Read' in Path('.claude/agents/bob.md').read_text(); print('PASS: role tools and project permissions unchanged')"]
    check = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
    check_path.write_text(check.stdout+check.stderr)
    state = json.loads((runtime.session_path(root, first['session_id']) / 'session.json').read_text())
    contract = runtime.runtime_contract(root, args.claude, 'bob')
    assessment = recovery.assess(root, state, contract, dict(assessor='arch', decision='resume',
        reason='This isolated witness changes only a response marker and harmless test environment variable; measured role tools and project permissions remain identical.',
        check=dict(command=' '.join(command), executed=True, exit=check.returncode,
                   evidence={'path':'compatibility.log','sha256':hashlib.sha256(check_path.read_bytes()).hexdigest()})))
    second = runtime.run_turn(root, session=first['session_id'], correction_round=1,
        prompt='Read .claude/agents/bob.md, follow the current marker instruction, recall the first token, and return the required footer.',
        transition=assessment, executable=args.claude, timeout=55)
    passed = (second['status'] == 'completed' and second['session_id'] == first['session_id']
              and second['footer'].get('marker') == 'SECOND' and second['footer'].get('remembered') == token)
    result = dict(status='PASS' if passed else 'FAIL', first_event=first['event_id'], second_event=second['event_id'],
                  session_id=first['session_id'], assessment=assessment,
                  footer=second['footer'], limitation='Explicit Read refresh was requested; automatic instruction reload and arbitrary plugins are not certified.')
    (root / 'live-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
