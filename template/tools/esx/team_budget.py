#!/usr/bin/env python3
"""Atomic spend reservations shared by coordinator, children, resumes and repairs.

Reserve a provider-enforced maximum BEFORE launch. Settle known usage afterward;
unknown or interrupted usage retains its entire reservation, so a retry cannot
silently spend it again. Scope identifiers and original deadlines are immutable.
This bounds allocated spend; provider billing enforcement/overshoot is recorded,
not misrepresented as a guarantee about an external invoice.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import time
import team_accounting as accounting

DEFAULTS = {
    'scientific_small': {'minutes': 30, 'usd': 15, 'calls': 120, 'corrections': 1, 'turn_usd': 5},
    'scientific_change': {'minutes': 120, 'usd': 60, 'calls': 500, 'corrections': 2, 'turn_usd': 12},
    'harness_change': {'minutes': 45, 'usd': 20, 'calls': 180, 'corrections': 1, 'turn_usd': 5},
    'documentation': {'minutes': 30, 'usd': 15, 'calls': 120, 'corrections': 1, 'turn_usd': 5},
    'investigation': {'minutes': 45, 'usd': 20, 'calls': 180, 'corrections': 2, 'turn_usd': 5}}


class Exhausted(ValueError):
    pass


def limits(kind='investigation', override=None):
    value = dict(DEFAULTS[kind])
    if override: value.update(override)
    if set(value) != set(DEFAULTS[kind]) or any(not accounting.number(n) for n in value.values()):
        raise ValueError('budget must contain finite nonnegative minutes/usd/calls/corrections/turn_usd')
    if any(value[k] <= 0 for k in ('minutes', 'usd', 'calls', 'turn_usd')):
        raise ValueError('time, spend and call budgets must be positive')
    if type(value['calls']) is not int or type(value['corrections']) is not int:
        raise ValueError('call and correction limits must be integers')
    return value


def file_for(root):
    return Path(root) / accounting.STATE / 'budget_ledger.json'


@contextmanager
def transaction(root, write=True):
    path = file_for(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = json.loads(path.read_text()) if path.exists() else {'version': 1, 'scopes': {}, 'reservations': {}}
        yield value
        if write:
            accounting.atomic(path, value)


def reserve(root, event, issue, budget, *, run=None, run_budget=None, correction=0, amount=None, turn_seconds=None, turn_calls=None):
    budget = limits(override=budget)
    amount = budget['turn_usd'] if amount is None else amount
    if not accounting.number(amount) or amount <= 0: raise ValueError('positive reservation required')
    if turn_seconds is not None and (not accounting.number(turn_seconds) or turn_seconds <= 0): raise ValueError('positive turn timeout required')
    if turn_calls is not None and (type(turn_calls) is not int or turn_calls <= 0): raise ValueError('positive turn call cap required')
    scopes = [('issue:' + issue, budget)]
    if run:
        scopes.append(('run:' + run, limits(override=run_budget or budget)))
    with transaction(root) as ledger:
        if event in ledger['reservations']: raise ValueError('event already reserved')
        for key, cap in scopes:
            saved = ledger['scopes'].setdefault(key, {'limits': cap, 'started': time.time(), 'calls': []})
            if saved.get('breached'): raise Exhausted(key + ': provider exceeded its reservation')
            if saved['limits'] != cap: raise ValueError('budget cannot change/reset during scope: ' + key)
            if time.time() >= saved.get('deadline', saved['started'] + cap['minutes'] * 60): raise Exhausted(key + ': wall budget exhausted')
            if correction > cap['corrections']: raise Exhausted(key + ': correction budget exhausted; diagnose before continuing')
            spent = sum(r['charged_usd'] for r in ledger['reservations'].values() if key in r['scopes'])
            available = cap['usd'] - spent
            if available <= 1e-8: raise Exhausted(key + ': spend budget exhausted')
            amount = min(amount, available)
        deadlines = [ledger['scopes'][k].get('deadline', ledger['scopes'][k]['started'] + c['minutes'] * 60) for k, c in scopes]
        soft_deadlines = [ledger['scopes'][k].get('soft_deadline', ledger['scopes'][k]['started'] + c['minutes'] * 48) for k,c in scopes]
        if turn_seconds is not None:
            deadlines.append(time.time()+turn_seconds)
            soft_deadlines.append(time.time()+turn_seconds*.8)
        receipt = {'event_id': event, 'scopes': [k for k, _ in scopes], 'reserved_usd': amount,
                   'charged_usd': amount, 'reported_usd': None, 'status': 'reserved',
                   'deadline': min(deadlines), 'soft_deadline': min(soft_deadlines),
                   'call_limit': turn_calls, 'calls': []}
        ledger['reservations'][event] = receipt
    return receipt


def settle(root, event, reported):
    if reported is not None and not accounting.number(reported): raise ValueError('invalid provider amount')
    with transaction(root) as ledger:
        entry = ledger['reservations'][event]
        if entry['status'] != 'reserved':
            if entry['reported_usd'] != reported: raise ValueError('conflicting settlement')
            return entry
        entry.update(reported_usd=reported, charged_usd=reported if reported is not None else entry['reserved_usd'],
                     status='settled' if reported is not None else 'unknown_reserved')
        entry['provider_overshoot'] = reported is not None and reported > entry['reserved_usd'] + 1e-8
        # A provider breach consumes the remaining scope; never authorize another call.
        if entry['provider_overshoot']:
            for key in entry['scopes']: ledger['scopes'][key]['breached'] = True
    return entry


def allow_tool(root, event, tool_id):
    with transaction(root) as ledger:
        entry = ledger['reservations'][event]
        identity = event + ':' + tool_id
        if all(identity in ledger['scopes'][k]['calls'] for k in entry['scopes']): return
        if entry.get('call_limit') and len(entry['calls']) >= max(1,int(entry['call_limit']*.8)):
            raise Exhausted('80% turn call budget reached: return your measured partial handoff now')
        for key in entry['scopes']:
            scope = ledger['scopes'][key]
            if scope.get('breached'): raise Exhausted('provider exceeded reservation')
            if time.time() >= entry['soft_deadline'] or len(scope['calls']) >= int(scope['limits']['calls'] * .8):
                raise Exhausted('80% budget reached: return a partial handoff with completed evidence and next action')
        identity = event + ':' + tool_id
        for key in entry['scopes']:
            calls = ledger['scopes'][key]['calls']
            if identity not in calls: calls.append(identity)
        entry.setdefault('calls', []).append(identity)


def assignment(root, issue):
    path = Path(root) / accounting.STATE / 'issue-start.json'
    start = json.loads(path.read_text()) if path.exists() else {}
    if start.get('id') != issue: start = {}
    kind = (start.get('workflow') or {}).get('kind', 'investigation')
    budget = limits(kind, start.get('budget'))
    # An explicit owner-authorized extension updates this same cumulative scope.
    ledger_path = file_for(root)
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    existing = ledger.get('scopes', {}).get('issue:' + issue)
    if existing:
        budget = limits(override=existing['limits'])
    run_path = Path(root) / accounting.STATE / 'run_budget.json'
    run = json.loads(run_path.read_text()) if run_path.exists() else {}
    return budget, run


def scope_digest(scope):
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def extend(root, authorization, apply=False):
    """Preview/apply a recorded Owner allocation; never reset prior spend or calls.

    Authorization is an operator-supplied hashed JSON reference, not something a
    role may invent. CAS and unique authorization IDs make stale/repeated requests
    safe. Active reservations and provider breaches require resolution first.
    """
    from process_evidence import reference
    request = json.loads(reference(root, authorization))
    for key in ('issue', 'authorization_id', 'evidence', 'reason', 'expected_scope_sha256'):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError('authorization missing ' + key)
    if request.get('authorized_by') != 'Owner':
        raise ValueError('explicit Owner authorization required')
    additions = {key: request.get('add_' + key, 0) for key in ('usd', 'minutes', 'calls', 'corrections')}
    if any(not accounting.number(n) for n in additions.values()) or additions['minutes'] <= 0:
        raise ValueError('nonnegative allocations and positive additional minutes required')
    if any(type(additions[k]) is not int for k in ('calls', 'corrections')):
        raise ValueError('additional calls/corrections must be integers')
    with transaction(root, write=apply) as ledger:
        key = 'issue:' + request['issue']
        scope = ledger['scopes'][key]
        prior = next((r for r in scope.get('extensions', [])
                      if r['request']['authorization_id'] == request['authorization_id']), None)
        if prior:
            if prior['request'] != request:
                raise ValueError('conflicting authorization ID')
            return {'status': 'already_applied', 'scope': scope}
        if scope_digest(scope) != request['expected_scope_sha256']:
            raise ValueError('scope changed since authorization; refresh its expected hash')
        if scope.get('breached'):
            raise ValueError('provider breach requires reconciliation, not a budget extension')
        if any(key in r['scopes'] and r['status'] == 'reserved' for r in ledger['reservations'].values()):
            raise ValueError('cannot extend with active reservations')
        updated = json.loads(json.dumps(scope))
        for name, amount in additions.items():
            updated['limits'][name] += amount
        updated['limits'] = limits(override=updated['limits'])
        begun = max(time.time(), scope.get('deadline', scope['started'] + scope['limits']['minutes'] * 60))
        updated['deadline'] = begun + additions['minutes'] * 60
        updated['soft_deadline'] = begun + additions['minutes'] * 48
        updated.setdefault('extensions', []).append({'request': request, 'authorization': authorization,
                                                    'applied_at': accounting.now()})
        if apply:
            ledger['scopes'][key] = updated
        return {'status': 'applied' if apply else 'preview', 'scope': updated,
                'retained_charged_usd': sum(r['charged_usd'] for r in ledger['reservations'].values() if key in r['scopes'])}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('--issue', required=True)
    renewal = sub.add_parser('extend')
    renewal.add_argument('--authorization', required=True, help='repository path#sha256 of Owner request')
    renewal.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.command == 'inspect':
        ledger = json.loads(file_for(args.root).read_text())
        scope = ledger['scopes']['issue:' + args.issue]
        result = {'scope': scope, 'expected_scope_sha256': scope_digest(scope)}
    else:
        result = extend(args.root, args.authorization, args.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
