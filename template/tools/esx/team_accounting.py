#!/usr/bin/env python3
"""Reconcile ESX effort and provider-reported costs without inventing missing data.

Read retained turns (including historical repair streams), coordinator receipts,
and phase events. JSON summaries preserve source IDs and coverage gaps. The
``phase`` context manager appends a timed event; the CLI is read-only unless
--output is supplied. No API calls or price assumptions. Tests: test_team_operations.py.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('devel-loop/loop_state')
PHASES = ('orientation', 'implementation', 'review', 'verification', 'closeout', 'retrospective', 'waiting', 'coordination')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def timestamp(value):
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('timestamp needs a timezone')
    return stamp.timestamp()


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(payload, f, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(payload, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


@contextmanager
def phase(root, issue, name, reason=None):
    if name not in PHASES or (name == 'waiting' and not reason):
        raise ValueError('phase needs a known name and waits need a reason')
    event = {'event_id': uuid.uuid4().hex, 'issue_id': issue, 'phase': name,
             'started_at': now(), 'reason': reason}
    started = time.monotonic()
    try:
        yield event
    finally:
        event.update(finished_at=now(), seconds=time.monotonic() - started)
        append(Path(root) / STATE / 'phase_events.jsonl', event)


def stream_usage(path):
    """Deduplicate streaming message/tool IDs; final result owns cost/usage."""
    final, tools, messages = None, set(), {}
    if path.exists():
        with path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('type') == 'result':
                    final = row
                if row.get('type') == 'assistant':
                    message = row.get('message') or {}
                    if message.get('id'):
                        messages[message['id']] = message.get('usage') or {}
                    for item in message.get('content') or []:
                        if isinstance(item, dict) and item.get('type') == 'tool_use' and item.get('id'):
                            tools.add(item['id'])
    usage = (final or {}).get('usage')
    if usage is None and messages:
        usage = {k: sum(v.get(k, 0) for v in messages.values()) for k in
                 ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')}
    return {'cost_usd': (final or {}).get('total_cost_usd'), 'usage': usage,
            'tool_calls': len(tools), 'usage_complete': final is not None,
            'model_usage': (final or {}).get('modelUsage'),
            'result_subtype': (final or {}).get('subtype'), 'result_is_error': (final or {}).get('is_error')}


def turns(root):
    root = Path(root)
    entries = []
    for path in sorted((root / STATE / 'agent_runtime/sessions').glob('*/turns/*/record.json')):
        record = json.loads(path.read_text())
        components = record.get('accounting_components')
        if components is None:
            components = [{'event_id': record['event_id'], 'cost_usd': record.get('cost_usd'),
                           'usage': record.get('usage'), 'tool_calls': record.get('tool_calls'), 'kind': 'turn'}]
            for repair in sorted(path.parent.glob('repair-*.jsonl')):
                components.append({'event_id': repair.stem, 'kind': 'repair', **stream_usage(repair)})
        entries.append({**record, 'accounting_components': components, 'source': str(path.relative_to(root))})
    for path in sorted((root / STATE / 'coordinator').glob('*/record.json')):
        entries.append({**json.loads(path.read_text()), 'source': str(path.relative_to(root))})
    captured = {r['event_id'] for r in entries}
    for record in rows(root / STATE / 'dispatch_log.jsonl'):
        if record.get('runtime') == 'native_subagent' and record.get('event_id') not in captured:
            entries.append(dict(record, source=str(STATE / 'dispatch_log.jsonl'),
                accounting_components=[{'event_id': record['event_id'], 'cost_usd': None,
                    'usage': None, 'tool_calls': None, 'kind': 'unmetered_native'}]))
    unique = {}
    for entry in entries:
        key = entry['event_id']
        if key in unique:
            raise ValueError('duplicate accounting event: ' + key)
        unique[key] = entry
    return list(unique.values())


def union_seconds(intervals):
    merged = []
    for start, end in sorted(intervals):
        if end < start:
            raise ValueError('negative interval')
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return sum(b - a for a, b in merged)


def snapshot(root):
    """One fresh read per report, shared by issue summaries; never cached across runs."""
    return {'turns': turns(root), 'phases': rows(Path(root) / STATE / 'phase_events.jsonl')}


def summary(root, issue=None, start=None, end=None, *, evidence=None, run_id=None):
    root = Path(root)
    evidence = snapshot(root) if evidence is None else evidence
    selected = [r for r in evidence['turns'] if issue is None or r.get('issue_id') == issue]
    if run_id: selected = [r for r in selected if r.get('run_id') == run_id
                           or 'run:'+run_id in (r.get('budget') or {}).get('scopes', [])]
    # Bound repeated iterations by observed overlap, never by round counters.
    if start:
        selected = [r for r in selected if timestamp(r.get('finished_at') or r.get('ts')) >= timestamp(start)]
    if end:
        selected = [r for r in selected if timestamp(r.get('started_at') or r.get('ts')) <= timestamp(end)]
    roles, components, seen, intervals = {}, [], set(), []
    for r in selected:
        role = r.get('agent_type', 'unknown')
        group = roles.setdefault(role, {'dispatches': 0, 'rounds': set(), 'seconds': 0.,
                                        'reported_usd': 0., 'unknown_cost_events': 0, 'tool_calls': 0,
                                        'unknown_tool_call_events': 0, 'usage': {}})
        group['dispatches'] += 1
        group['rounds'].add((r.get('session_id'), r.get('correction_round', 0)))
        if r.get('started_at') and r.get('finished_at'):
            a, b = timestamp(r['started_at']), timestamp(r['finished_at'])
            if start: a = max(a, timestamp(start))
            if end: b = min(b, timestamp(end))
            if b >= a:
                if role != 'arch': intervals.append((a, b))
                group['seconds'] += b - a
        for c in r.get('accounting_components') or [r]:
            key = c['event_id']
            if key in seen:
                raise ValueError('duplicate cost component: ' + key)
            seen.add(key)
            cost = c.get('cost_usd')
            if cost is not None and not number(cost):
                raise ValueError('invalid cost for ' + key)
            group['reported_usd'] += cost or 0
            group['unknown_cost_events'] += cost is None
            calls = c.get('tool_calls')
            group['tool_calls'] += calls or 0
            group['unknown_tool_call_events'] += calls is None
            for k, v in (c.get('usage') or {}).items():
                if k.endswith('tokens') and number(v):
                    group['usage'][k] = group['usage'].get(k, 0) + v
            components.append({'event_id': key, 'parent_event_id': r['event_id'], 'role': role,
                               'kind': c.get('kind', 'turn'), 'reported_usd': cost, 'source': r['source']})
    for group in roles.values(): group['rounds'] = len(group['rounds'])
    span = timestamp(end) - timestamp(start) if start and end else None
    if span is not None and span < 0: raise ValueError('close predates start')
    phases = [r for r in evidence['phases'] if not issue or r['issue_id'] == issue]
    phases = [r for r in phases if (not start or timestamp(r.get('finished_at') or r.get('ts')) >= timestamp(start))
              and (not end or timestamp(r.get('started_at') or r.get('ts')) <= timestamp(end))]
    by_phase = {}
    for event in phases:
        a, b = timestamp(event['started_at']), timestamp(event['finished_at'])
        if start: a = max(a, timestamp(start))
        if end: b = min(b, timestamp(end))
        if b >= a: by_phase.setdefault(event['phase'], []).append((a,b))
    phase_totals = {name: {'elapsed_seconds': union_seconds(spans),
                          'effort_seconds': sum(b-a for a,b in spans), 'events': len(spans)}
                    for name,spans in by_phase.items()}
    child = union_seconds(intervals)
    return {'schema_version': 2, 'issue_id': issue, 'start': start, 'end': end,
            'span_seconds': span, 'child_elapsed_seconds': child,
            'outside_child_intervals_seconds': max(0, span - child) if span is not None else None,
            'by_role': roles, 'reported_usd': sum(c['reported_usd'] or 0 for c in components),
            'unknown_cost_event_ids': [c['event_id'] for c in components if c['reported_usd'] is None],
            'coordinator_coverage': 'recorded' if 'arch' in roles else 'missing',
            'billing_status': 'provider_reported_not_invoice_reconciled',
            'missing_timing_event_ids': [r['event_id'] for r in selected if not r.get('started_at') or not r.get('finished_at')],
            'by_phase': phase_totals, 'phase_events': phases, 'components': components}


def measured(report):
    """Canonical retrospective fields, including honest unknown coverage."""
    return {'span_minutes': round(report['span_seconds'] / 60) if report['span_seconds'] is not None else None,
            'dispatches': {r: v['dispatches'] for r, v in report['by_role'].items()},
            'rounds': {r: v['rounds'] for r, v in report['by_role'].items()},
            'cost_usd': {r: v['reported_usd'] for r, v in report['by_role'].items()},
            'unknown_cost_event_ids': report['unknown_cost_event_ids'],
            'coordinator_coverage': report['coordinator_coverage'], 'billing_status': report['billing_status']}


def concise(report):
    span = report['span_seconds']
    elapsed = f'{span / 60:.1f} min' if span is not None else 'elapsed unknown'
    return (f"{report['issue_id'] or 'RUN'}: {elapsed}; child elapsed {report['child_elapsed_seconds']/60:.1f} min; "
            f"reported ${report['reported_usd']:.2f}; unknown costs {len(report['unknown_cost_event_ids'])}; "
            f"Arch {report['coordinator_coverage']}; not invoice reconciled")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--issue'); p.add_argument('--start'); p.add_argument('--end')
    p.add_argument('--output', type=Path); p.add_argument('--concise', action='store_true')
    a = p.parse_args()
    report = summary(a.root, a.issue, a.start, a.end)
    if a.output: atomic(a.output, report)
    print(concise(report) if a.concise else json.dumps(report, indent=2))


if __name__ == '__main__': main()
