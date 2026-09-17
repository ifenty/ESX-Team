#!/usr/bin/env python3
"""Qualify actual role tools, retained history and direct peer messages in scratch.

This opt-in command uses the configured Claude provider and may incur charges.
--resume-root continues the printed scratch deployment after a failed turn.
It preserves failed evidence and assigned identities. No external messages run.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import uuid

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'template/tools/esx'))
import agent_runtime
import doc_contract
import issue_candidates
import loop_gate
import project


def setup():
    spec = importlib.util.spec_from_file_location('esx_live_deploy', KIT / 'deploy.py')
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    root = Path(tempfile.mkdtemp(prefix='esx-live-runtime-')).resolve()
    deploy.deploy(root, apply=True)
    example = KIT / 'examples/periodic_diffusion'
    for name in ('src', 'tests'):
        shutil.copytree(example / name, root / name)
    for source, target in [('project.json', 'esx/project.json'), ('project_profile.md', 'esx/project_profile.md'),
                           ('code_map.md', 'docs/code_map.md')]:
        shutil.copyfile(example / source, root / target)
    settings = project.json_file(root, '.claude/settings.json')
    settings['permissions'] = {'allow': ['Read', 'Glob', 'Grep',
        'Write(./results/**)', 'Edit(./results/**)', 'Bash(python3 tools/esx/*)']}
    project.atomic_json(root / '.claude/settings.json', settings)
    (root / 'results').mkdir()
    (root / 'open_issues.md').write_text('# Open issues\n\n## UNRESOLVED: Retained role transport qualification\n'
        '**Status**: Unresolved\n**UUID**: RUNTIME-QUALIFICATION\n'
        '**Anchors**: src/diffusion.py::step; tests/check_diffusion.py::<module>\n')
    with (root / 'esx/project_profile.md').open('a') as stream:
        stream.write('\n## Authorized disposable transport qualification\n\n'
            'The owner authorizes RUNTIME-QUALIFICATION in this scratch project. Bob writes '
            'a public marker and correction in results/runtime_probe.txt; Richard reads it, '
            'requests the corrected line, then checks that correction on resume. Both may '
            'use tools/esx helpers for orientation, focused checks and peer messages. '
            'The test makes no scientific acceptance claim or external announcement.\n')
    with contextlib.redirect_stderr(io.StringIO()):
        loop_gate.Gate(root).prepare('RUNTIME-QUALIFICATION', 'harness_change', (), 'arch',
            'Qualify retained role tools and communication before scientific work.',
            'docs/code_map.md#pipeline', ['src/diffusion.py::step', 'tests/check_diffusion.py::<module>'],
            ['docs/model_contract.md'], 'Locate the scientific owner and oracle to restrict the transport test to disposable result files.')
    return root


def qualify(executable='claude', timeout=180, resume_root=None):
    root = Path(resume_root).resolve() if resume_root else setup()
    print(json.dumps({'scratch': str(root), 'status': 'starting'}), flush=True)
    spec = importlib.util.spec_from_file_location('esx_live_runtime', root / 'tools/esx/agent_runtime.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    probe = runtime.probe_status(root, executable)
    if probe['status'] != 'passed':
        probe = runtime.probe_runtime(root, executable, timeout)
    if probe['status'] != 'passed':
        raise ValueError('retained-history probe failed; scratch=' + str(root))
    start = project.json_file(root, 'devel-loop/loop_state/issue-start.json')
    issue = start['id']
    if issue != 'RUNTIME-QUALIFICATION':
        raise ValueError('resume-root must be this script’s disposable transport issue')
    metadata = root / 'devel-loop/loop_state/live-qualification.json'
    if metadata.exists():
        saved = json.loads(metadata.read_text())
    else:
        marker = root / 'results/runtime_probe.txt'
        token = marker.read_text().splitlines()[0] if marker.exists() else 'test-marker-' + uuid.uuid4().hex
        plan = doc_contract.draft(root, issue, start['maintenance']['baseline'])
        if plan['changes']:
            raise ValueError('qualification source changed; review its actual changes before resuming')
        plan['map_delta'] = {'status': 'MAP-OK', 'reason': 'The transport exercise writes only excluded scratch result files; the scientific map and oracle routes remain accurate.',
                             'references': ['docs/code_map.md#pipeline']}
        saved = {'token': token, 'documentation': doc_contract.seal(root, plan)}
        project.atomic_json(metadata, saved)
    review_packet = {'id': issue,
        'candidate': issue_candidates.capture(root, issue, start['maintenance']['baseline']),
        'maintenance': {'baseline': start['maintenance']['baseline'], 'documentation': saved['documentation']},
        'handoff': {'outcome': 'Qualify retained marker correction', 'constraints': ['scratch result files only'],
                    'acceptance_tests': ['marker retained and corrected second line']}}
    project.atomic_json(root / 'devel-loop/loop_state/live-review.json', review_packet)
    token = saved['token']
    (root / 'results/check_transport.py').write_text(
        "from pathlib import Path\nimport sys\nlines=Path('results/runtime_probe.txt').read_text().splitlines()\n"
        "assert lines and lines[0].startswith('test-marker-')\n"
        "if '--corrected' in sys.argv: assert lines[1:]==['corrected']\nprint('PASS: inspected transport marker')\n")

    def events():
        path = root / 'devel-loop/loop_state/dispatch_log.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def latest(role):
        return next((row for row in reversed(events()) if row.get('agent_type') == role and row.get('issue_id') == issue), None)

    def turn(role, prompt, previous=None, number=0, budget=None):
        options = {'session': previous['agent_id']} if previous else {'role': role, 'issue': issue}
        if role == 'richard':
            options['review_packet'] = review_packet
        result = runtime.run_turn(root, executable=executable, timeout=budget or timeout,
                                  correction_round=number, prompt=prompt, **options)
        print(json.dumps({key: result.get(key) for key in ('agent_type', 'status', 'session_id', 'event_id', 'error')}), flush=True)
        if result['status'] != 'completed':
            raise ValueError('role turn failed; resume with --resume-root ' + str(root))
        return result

    def footer(role, number, **fields):
        value = {'agent': role, 'issue_id': issue, 'iteration_timestamp': start['timestamp'],
                 'correction_round': number, **fields}
        return ('\nEnd with one JSON fence containing these fields plus your actual orientation reference: '
                + json.dumps(value))

    def briefing(role):
        argv = ['python3', 'tools/esx/doc_contract.py', 'navigate', '--issue', issue,
            '--baseline', json.dumps(start['maintenance']['baseline']), '--role', role,
            '--map', 'docs/code_map.md#pipeline', '--target', 'src/diffusion.py::step',
            '--target', 'tests/check_diffusion.py::<module>', '--doc', 'docs/model_contract.md',
            '--use', 'The mapped diffusion owner and oracle bound this transport check to scratch outputs without changing scientific behavior.']
        return ('Arch assigns the authorized disposable transport issue. Your dispatcher context supplies '
            'your exact runtime identity and iteration. Save your orientation with this exact command:\n'
            + shlex.join(argv) + '\nThe sealed documentation report is '
            + json.dumps(saved['documentation']) + '. No source files changed. '
            'This bounded review concerns results/runtime_probe.txt. Read that file and the supplied '
            'report; no discovery of additional roles, suite routing or scientific implementation is required. '
            'A focused check is available through python3 tools/esx/verify.py --suite focused '
            '--owner YOUR_ACTUAL_AGENT_ID --fresh --command '
            + shlex.quote(json.dumps(['{python}', 'results/check_transport.py'])) + '. '
            'Return after these bounded observations; Arch handles subsequent dispatch and closeout. ')

    bob = latest('bob')
    if not bob or bob['status'] != 'completed':
        number = bob.get('correction_round', 0) + 1 if bob else 0
        bob = turn('bob', briefing('bob') + 'Remember public marker ' + token
            + '. Write it and a newline to results/runtime_probe.txt using Write. '
            + footer('bob', number, action='wrote-initial-marker'), bob, number)
    richard = latest('richard')
    if not richard or richard['status'] != 'completed':
        number = richard.get('correction_round', 0) + 1 if richard else 0
        richard = turn('richard', briefing('richard') +
            'Remember the file’s marker for your next turn. It has no corrected line yet. '
            'Request that one correction from Arch and return REJECT. The missing line is the expected '
            'witness; repeated execution of that failure adds no evidence. Do not dispatch Bob in this '
            'initial review; Arch will resume his existing session. If you already executed the focused '
            'check before a timeout, report that evidence with its actual result. '
            + footer('richard', number, verdict='REJECT', must_fix=['Append the corrected marker.']), richard, number)
    number = bob.get('correction_round', 0) + 1
    review_round = richard.get('correction_round', 0) + 1
    request = root / 'results/review-request.txt'
    request.write_text('Inspect results/runtime_probe.txt with Read. Confirm its marker matches your '
        'remembered value and its second line is corrected. Use your existing orientation if valid. '
        'This is the assigned focused delta review; report its result and return. '
        + footer('richard', review_round, verdict='APPROVE', must_fix=[]))
    command = shlex.join(['python3', 'tools/esx/agent_runtime.py', 'message', '--session', richard['agent_id'],
        '--from-session', bob['agent_id'], '--correction-round', str(review_round), '--timeout', str(timeout),
        '--prompt-file', 'results/review-request.txt', '--review-packet', 'devel-loop/loop_state/live-review.json'])
    bob_final = turn('bob', 'Apply Richard’s correction by appending corrected to results/runtime_probe.txt. '
        'Preserve your remembered public marker. Then send the review request directly to the same '
        'Richard using this exact command:\n' + command + '\nRequire completed status and APPROVE. '
        'Return after that result; Arch owns closeout. ' + footer('bob', number, action='corrected-and-messaged'), bob, number, budget=2*timeout+30)
    peers = [row for row in events() if row.get('agent_id') == richard['agent_id']
        and row.get('sender_session_id') == bob['agent_id'] and row.get('correction_round') == review_round]
    if len(peers) != 1 or peers[0]['status'] != 'completed' or peers[0]['footer'].get('verdict') != 'APPROVE':
        raise ValueError('direct retained peer correction was not observed; scratch=' + str(root))
    if (root / 'results/runtime_probe.txt').read_text().splitlines() != [token, 'corrected']:
        raise ValueError('corrected file failed the exact marker oracle')
    result = {'status': 'PASS', 'checks': ['two-turn retained history', 'actual role tools', 'actual file edit',
        'same Bob resumed', 'Bob directly messaged retained Richard', 'Richard returned recorded approval',
        'corrected file preserves marker'], 'records': [bob, richard, bob_final, *peers],
        'limits': 'This scratch transport smoke does not qualify scientific changes or measure issue-development throughput.'}
    project.atomic_json(root / 'qualification.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--claude', default='claude')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--resume-root', type=Path)
    args = parser.parse_args()
    try:
        result = qualify(args.claude, args.timeout, args.resume_root)
        print(json.dumps({'status': result['status'], 'checks': result['checks'], 'limits': result['limits']}, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
