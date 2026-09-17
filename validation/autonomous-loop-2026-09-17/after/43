"""Durable loop event outbox. Arch delivers via the authorized provider tool.

No network or credential access occurs here. Events are derived from project
records and deduplicated by stable identity; successful delivery retains the raw
provider response. A concrete failed/unavailable attempt permits scientific work
while remaining visible in the ledger. Pending is never treated as an attempt.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import sys
from project import STATE, atomic_json, digest, local, now, require
from records import json_lines, validate_records

ROOT = Path(__file__).resolve().parents[2]
LEDGER = f'{STATE}/notifications.json'


@contextmanager
def ledger(root):
    path = local(root, LEDGER)
    lock = local(root, f'{STATE}/notifications.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else {'version': 1, 'events': {}, 'runs': {}}
        require(data.get('version') == 1, 'unsupported notification ledger')
        try:
            yield data
            atomic_json(path, data)
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def emit(data, key, kind, subject, text, route):
    identity = digest([key, route.get('provider'), route.get('channel')])[:24]
    if identity not in data['events']:
        data['events'][identity] = {'id': identity, 'kind': kind, 'subject': subject,
            'text': ((route.get('message_prefix') or '[ESX]') + ' ' + text)[:1800],
            'provider': route.get('provider'), 'channel': route.get('channel'),
            'created_at': now(), 'status': 'pending', 'attempts': []}
    return identity


def synchronize(root, terminal=None):
    """Collect actual transitions; baseline pre-existing issues and lessons once.

    Closeouts come only from validated history. A newly closed Markdown entry
    cannot establish acceptance. Local state and provider receipts are excluded
    from source signatures by their loop_state location.
    """
    root = Path(root).resolve()
    path = local(root, '.claude/esx-loop.local.md')
    if not path.exists():
        return
    from ralph_stop import parse_state
    state = parse_state(path.read_text())
    if state['active'] != 'true':
        return
    cfg = json.loads(local(root, 'esx/project.json').read_text())
    route = cfg.get('communication', {})
    if not route.get('provider') or route.get('provider') in ('none', 'disabled'):
        return
    require(route.get('channel'), 'configured communication requires a channel')
    opened, closed, lessons = validate_records(root)
    starts = local(root, f'{STATE}/issue-start.json')
    start = json.loads(starts.read_text()) if starts.exists() else None
    history = json_lines(local(root, f'{STATE}/loop_history.jsonl'))
    match = re.search(r'(?m)^run_id:\s*([^\s]+)', state['header'])
    # Existing deployments use the fixed header (minus the counter) as identity.
    run = match[1] if match else digest([state['limit'], state['promise'], state['prompt']])[:24]
    with ledger(root) as data:
        if run not in data['runs']:
            data['runs'][run] = {'issues': sorted(set(opened) | set(closed)), 'lessons': sorted(lessons),
                                'history': [[h['id'], h['timestamp']] for h in history]}
            emit(data, ['loop_start', run], 'loop_start', run,
                 f"Loop active at iteration {state['iteration']}/{state['limit']}. "
                 f"{len(opened)} open issues; autonomous work follows the project contracts.", route)
        seen = data['runs'][run]
        for iid in sorted(set(opened) - set(seen['issues'])):
            emit(data, ['issue_opened', run, iid], 'issue_opened', iid,
                 f"New issue {iid}: {opened[iid]['title']}. Recorded for investigation.", route)
        for lid in sorted(lessons - set(seen['lessons'])):
            lines = local(root, 'lessons_learned.md').read_text().splitlines()
            description = next((line.strip() for line in lines if f'[{lid}]' in line), lid)
            emit(data, ['lesson', run, lid], 'lesson', lid, f'Lesson recorded: {description}', route)
        seen['issues'] = sorted(set(seen['issues']) | set(opened) | set(closed))
        seen['lessons'] = sorted(set(seen['lessons']) | lessons)
        if start and not any((h['id'], h['timestamp']) == (start['id'], start['timestamp']) for h in history):
            emit(data, ['issue_start', start['id'], start['timestamp']], 'issue_start', start['id'],
                 f"Starting {start['id']}: {start['title']}. {start['priority_reason']}", route)
        for h in history:
            identity = [h['id'], h['timestamp']]
            if identity not in seen['history']:
                emit(data, ['closeout', *identity], 'issue_closeout', h['id'],
                     f"{h['id']} — {h['outcome']}: {h['summary']}", route)
                seen['history'].append(identity)
        if state['iteration'] > 1 and terminal is None:
            iid = start['id'] if start else 'issue selection'
            emit(data, ['progress', run, state['iteration']], 'progress', run,
                 f"Loop iteration {state['iteration']}/{state['limit']}; current record: {iid}. "
                 'Work and verification continue; completion is reported after validated closeout.', route)
        if terminal:
            emit(data, ['loop_end', run], 'loop_end', run,
                 f"Loop ending: {terminal}. {len(opened)} open issues, "
                 f"{sum(r['state'] == 'blocked' for r in opened.values())} blocked. "
                 'Unfinished work remains recorded on disk.', route)


def pending(root):
    path = local(Path(root).resolve(), LEDGER)
    if not path.exists():
        return []
    events = [e for e in json.loads(path.read_text())['events'].values() if e['status'] == 'pending']
    return sorted(events, key=lambda e: (e['created_at'], e['id']))


def record(root, identity, response=None, disposition=None, detail=None, tool=None, authorization=None):
    """Attach an actual response or a concrete provider/authorization failure.

    The local receipt proves what was recorded; the provider owns delivery truth.
    It must contain an explicit successful message/channel or Slack timestamp.
    """
    with ledger(Path(root).resolve()) as data:
        require(identity in data['events'], 'unknown notification event')
        e = data['events'][identity]
        require(e['status'] != 'sent', 'event already delivered; do not post it again')
        require(isinstance(tool, str) and tool.strip(), 'record the attempted tool or tool-discovery action')
        attempt = {'at': now(), 'tool': tool}
        if response is not None:
            require(isinstance(authorization, str) and authorization.strip(), 'record applicable owner authorization')
            require(isinstance(response, dict) and not response.get('error') and response.get('ok') is not False,
                    'provider response reports an error or has invalid shape')
            if e['provider'] == 'slack':
                # Authenticated Slack MCP returns message_context; Web API uses ok/channel/ts.
                context = response.get('message_context', {})
                require(isinstance(context, dict), 'invalid Slack message_context')
                channel = context.get('channel_id') if context else response.get('channel')
                ts = context.get('message_ts') if context else response.get('ts')
                require(bool(context) or response.get('ok') is True, 'Slack API receipt requires ok=true')
                require(channel == e['channel'], 'receipt channel differs from the event destination')
                require(isinstance(ts, str) and re.fullmatch(r'\d{10}\.\d{6}', ts),
                        'Slack receipt requires the returned message timestamp')
            else:
                require(response.get('ok') is True and response.get('channel') == e['channel']
                        and response.get('message_id'), 'provider receipt needs success, destination and message_id')
            attempt.update(status='sent', response=response, authorization=authorization)
        else:
            require(disposition in ('failed', 'unavailable', 'unauthorized'), 'record a real delivery disposition')
            require(isinstance(detail, str) and len(detail.strip()) >= 20, 'provide concrete failure/discovery/authorization details')
            attempt.update(status=disposition, detail=detail)
        e['attempts'].append(attempt)
        e['status'] = attempt['status']
        return e


def notice(root):
    events = pending(root)
    if events:
        return ('NEXT: deliver ' + str(len(events)) + ' pending loop notification(s) using '
                '.claude/skills/esx-announce/SKILL.md; run tools/esx/notifications.py pending. '
                'Record the real receipt or concrete provider failure, then run --next again.')
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('pending')
    sub.add_parser('sync')
    sub.add_parser('status')
    r = sub.add_parser('record')
    r.add_argument('event')
    r.add_argument('--response-file', type=Path)
    r.add_argument('--disposition', choices=('failed', 'unavailable', 'unauthorized'))
    r.add_argument('--detail')
    r.add_argument('--tool', required=True)
    r.add_argument('--authorization')
    args = p.parse_args(argv)
    try:
        if args.action in ('sync', 'pending'):
            synchronize(args.root)
            result = pending(args.root)
        elif args.action == 'status':
            path = local(args.root, LEDGER)
            result = json.loads(path.read_text()) if path.exists() else {'events': {}}
        else:
            result = record(args.root, args.event,
                json.loads(args.response_file.read_text()) if args.response_file else None,
                args.disposition, args.detail, args.tool, args.authorization)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ESX notifications: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
