#!/usr/bin/env python3
"""Exercise an explicitly selected installed Ralph adapter in a temporary project.

No live agent or provider runs. Only the selected setup/Stop scripts execute,
against synthetic transcripts and state inside a disposable working directory.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

PROMISE = 'ESX-LOOP-NO-ACTIONABLE-WORK'
PROMPT = f'Run python3 tools/esx/loop_gate.py --next FIRST. Emit <promise>{PROMISE}</promise> only when --next exits 3.'

if not __debug__:
    raise SystemExit('Adapter checks require assertions enabled; remove -O/PYTHONOPTIMIZE.')


def check(plugin):
    setup, stop = plugin / 'scripts/setup-ralph-loop.sh', plugin / 'hooks/stop-hook.sh'
    if not setup.is_file() or not stop.is_file():
        raise ValueError('selected plugin lacks the expected setup/stop adapter paths')
    with tempfile.TemporaryDirectory(prefix='esx-ralph-adapter-') as directory:
        root = Path(directory)
        env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(root)}
        state = root / '.claude/ralph-loop.local.md'
        transcript = root / 'synthetic-transcript.jsonl'

        def start(limit):
            subprocess.run(['bash', str(setup), '--max-iterations', str(limit), '--completion-promise', PROMISE, PROMPT],
                           cwd=root, env=env, check=True, capture_output=True, text=True)
            assert state.exists() and 'active: true' in state.read_text()
            assert f'completion_promise: "{PROMISE}"' in state.read_text()
            assert state.read_text().split('---', 2)[2].strip() == PROMPT

        def finish(text):
            transcript.write_text(json.dumps({'role': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}}, separators=(',', ':')) + '\n')
            return subprocess.run(['bash', str(stop)], input=json.dumps({'cwd': str(root), 'transcript_path': str(transcript)}),
                                  cwd=root, env=env, capture_output=True, text=True, check=True)

        start(5)
        response = finish('Work remains; continue the bounded investigation.')
        body = json.loads(response.stdout)
        assert body['decision'] == 'block' and body['reason'].strip() == PROMPT
        assert 'iteration: 2' in state.read_text()
        response = finish(f'<promise>{PROMISE}</promise>')
        assert not state.exists() and ('promise' in response.stdout.lower() or PROMISE in response.stdout)
        start(2)
        finish('Work remains.')
        response = finish('Work remains.')
        assert not state.exists() and ('limit' in response.stdout.lower() or 'max iterations' in response.stdout.lower())
    return {'status': 'PASS', 'checks': ['prompt preservation', 'completion-promise configuration',
                                        'prompt reinjection', 'iteration increment', 'promise termination', 'finite iteration cap'],
            'live_agent_dispatch': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.plugin.resolve()), indent=2))
