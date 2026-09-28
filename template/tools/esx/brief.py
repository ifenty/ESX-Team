#!/usr/bin/env python3
"""Generate bounded role briefs with exact assignment and evidence interfaces."""
import argparse
import json
from pathlib import Path
import shlex
import sys
import doc_contract
import footer_contract
from project import STATE, json_file, require


def build(root, role, issue, design, question=None, packet=None, correction_round=0):
    start = json_file(root, STATE + '/issue-start.json')
    require(start['id'] == issue, 'brief must name the active issue')
    require(isinstance(design, str) and design.strip(), 'provide the bounded design and acceptance tests')
    if role == 'richard':
        require(question and packet, 'Richard needs a distinct question and reviewed packet')
        import agent_runtime
        agent_runtime.review_context(root, packet, issue, start['maintenance']['baseline'])
    context = packet or start
    nav = doc_contract.load(root, context['maintenance']['orientation'], 'orientation', issue)
    command = [sys.executable, 'tools/esx/doc_contract.py', 'navigate', '--issue', issue,
               '--baseline', json.dumps(nav['baseline']), '--role', role, '--map', nav['map']]
    for target in nav['targets']:
        command += ['--target', target]
    for doc in nav['documents']:
        command += ['--doc', doc]
    command += ['--use', 'Inspect the assigned owner and test to evaluate the bounded design and independent acceptance question.']
    footer = footer_contract.example(root, role)
    reseal = ('# Reseal before reporting\n'
              'Implementation normally edits the very targets this orientation was taken against, which '
              'invalidates the receipt and leaves an otherwise complete turn unreviewable. So as the FINAL steps '
              'after your last edit, in this order: re-run the orientation command above with your own --use '
              'sentence, then run ' + shlex.join([sys.executable, 'tools/esx/project.py', 'signature']) + '. Put '
              'both results in your footer. Running them before your last edit does not count; the receipt must '
              'bind to the bytes a reviewer will see.\nOriented targets, any of which triggers this:\n'
              + '\n'.join('  ' + target for target in nav['targets']))
    footer.update(issue_id=issue, iteration_timestamp=start['timestamp'], correction_round=correction_round)
    return '\n\n'.join([
        '# ' + role + ': ' + issue, '# Design and acceptance\n' + design,
        '# Question\n' + (question or 'Implement the bounded design and report actual focused checks.'),
        '# Expected cost and effort\n' + json.dumps(start.get('budget', {})) +
        '\nThese are recorded expectations, not caps: nothing will stop you at them, and exceeding one is measured '
        'rather than refused. Report a partial handoff when the work genuinely reaches a clean stopping point, not '
        'because a number was reached. If you do exceed an expectation, say by how much and why -- that measurement '
        'is how the expectation gets corrected.',
        '# Own orientation\n' + shlex.join(command) + '\nUse the returned orientation receipt, not the baseline.',
        reseal,
        '# Evidence\nUse tools/esx/project.py signature for candidate_signature. Execute independent checks through '
        'tools/esx/verify.py --suite focused --owner DISPATCHER_AGENT_ID --fresh and cite its returned evidence. '
        'Richard confirms the exact sealed documentation reference in this packet: ' + json.dumps(packet),
        '# Report\nKeep actual identity, evidence and limitations. Required values cannot be invented.\n```json\n'
        + json.dumps(footer, indent=2) + '\n```']) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--role', choices=('bob', 'richard'), required=True)
    p.add_argument('--issue', required=True)
    p.add_argument('--design', type=Path, required=True)
    p.add_argument('--question')
    p.add_argument('--packet', type=Path)
    p.add_argument('--round', type=int, default=0)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    value = build(a.root.resolve(), a.role, a.issue, (a.root / a.design).read_text(), a.question,
                  json.loads((a.root / a.packet).read_text()) if a.packet else None, a.round)
    if a.output:
        (a.root / a.output).write_text(value)
    else:
        print(value, end='')


if __name__ == '__main__':
    main()
