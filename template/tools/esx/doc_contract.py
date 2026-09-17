#!/usr/bin/env python3
"""Create and validate issue-local navigation and documentation evidence.

Artifacts are immutable, content-addressed JSON beneath loop_state/maintenance.
The gate validates identities, coverage and freshness. Authors and reviewers
remain responsible for whether the recorded explanations match the program.
"""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
import sys

from doc_inventory import MAP, changes, digest, excerpt, git, local, snapshot

from project import STATE
STORE = f'{STATE}/maintenance'
ROLES = ('arch', 'bob', 'richard', 'scout', 'prober', 'bisector', 'auditor')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def explanation(value):
    return isinstance(value, str) and len(value.strip()) >= 40


def evidence_path(root, name):
    """Resolve stored evidence without traversing symlink parents or leaves."""
    from issue_candidates import safe_path
    path = safe_path(root, name)
    require(not path.is_symlink(), f'evidence path cannot be a symlink: {name}')
    return path


def save(root, payload):
    """Write once under a digest-derived name; identical payloads reuse one artifact."""
    sha = digest(payload)
    ref = {'path': f'{STORE}/{sha}.json', 'sha256': sha}
    path = evidence_path(root, ref['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x') as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write('\n')
    except FileExistsError:
        require(json.loads(path.read_text()) == payload, 'existing evidence artifact is corrupt')
    return ref


def load(root, ref, kind, issue):
    require(isinstance(ref, dict), f'{kind} evidence reference is required')
    sha, name = ref.get('sha256'), ref.get('path')
    require(isinstance(sha, str) and len(sha) == 64 and name == f'{STORE}/{sha}.json',
            f'{kind} must reference a content-addressed maintenance artifact')
    payload = json.loads(evidence_path(root, name).read_text())
    require(digest(payload) == sha, f'{kind} evidence hash mismatch')
    require(isinstance(payload, dict), f'{kind} evidence must be an object')
    require(payload.get('version') == 1 and payload.get('kind') == kind,
            f'invalid {kind} evidence version/type')
    require(payload.get('issue_id') == issue, f'{kind} evidence belongs to another issue')
    if kind == 'baseline':
        require(isinstance(payload.get('files'), dict) and MAP in payload['files'],
                'baseline must include the code map and source inventory')
        if payload.get('source_snapshot'):
            from issue_candidates import load as load_candidate
            load_candidate(root, payload['source_snapshot'], issue)
    return payload


def envelope(kind, issue):
    require(isinstance(issue, str) and bool(issue.strip()), 'issue ID is required')
    return {'version': 1, 'kind': kind, 'issue_id': issue,
            'created_at': dt.datetime.now(dt.timezone.utc).isoformat()}


def baseline(root, issue, git_base=None, reason=None):
    """Reuse the issue's original baseline across every correction and loop turn.

    A write-once pin prevents a fresh working-tree capture from hiding cumulative
    edits. Existing issue history supplies the earliest recorded baseline when
    adopting an issue. Explicit commit recovery is for an absent original only.
    """
    require(not git_base or explanation(reason), 'commit recovery requires a substantive recovery reason')
    original = original_baseline(root, issue)
    if original:
        require(not git_base, 'original maintenance baseline already exists; commit recovery cannot replace it')
        pin_baseline(root, issue, original)
        return original
    payload = envelope('baseline', issue)
    commit = git(root, 'rev-parse', '--verify', git_base + '^{commit}').decode().strip() if git_base else None
    payload.update(files=snapshot(root, commit), recovery={'git_base': commit, 'requested_ref': git_base, 'reason': reason})
    if not commit:
        from issue_candidates import capture, load as load_candidate
        source_ref = capture(root, issue)
        captured = load_candidate(root, source_ref, issue)['files']
        require(set(payload['files']).issubset(captured)
                and all(name in captured and (captured[name]['kind'] == 'symlink'
                    or captured[name]['sha256'] == info['sha256'])
                    for name, info in payload['files'].items()),
                'source changed during baseline capture; capture again after edits finish')
        payload['source_snapshot'] = source_ref
    ref = save(root, payload)
    pin_baseline(root, issue, ref)
    return ref


def pin_path(root, issue):
    """Key original-baseline registrations by issue identity without path interpolation."""
    require(isinstance(issue, str) and issue.strip(), 'issue ID is required')
    return evidence_path(root, f'{STORE}/original/{digest(issue)}.json')


def original_baseline(root, issue):
    """Find the durable original or earliest retained history without changing records."""
    path = pin_path(root, issue)
    if path.exists():
        require(not path.is_symlink(), 'original maintenance baseline pin cannot be a symlink')
        record = json.loads(path.read_text())
        require(record.get('issue_id') == issue, 'original baseline pin identity mismatch')
        ref = record.get('baseline')
        load(root, ref, 'baseline', issue)
        return ref
    history = evidence_path(root, f'{STATE}/loop_history.jsonl')
    if history.exists():
        for line in history.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            require(isinstance(row, dict), 'baseline history row must be an object')
            ref = (row.get('maintenance') or {}).get('baseline')
            if row.get('id') == issue and ref:
                load(root, ref, 'baseline', issue)
                return ref
    start = evidence_path(root, f'{STATE}/issue-start.json')
    if start.exists():
        row = json.loads(start.read_text())
        ref = (row.get('maintenance') or {}).get('baseline')
        if row.get('id') == issue and ref:
            load(root, ref, 'baseline', issue)
            return ref
    return None


def pin_baseline(root, issue, ref):
    """Write the original registration once; concurrent attempts must agree."""
    load(root, ref, 'baseline', issue)
    path = pin_path(root, issue)
    require(not path.is_symlink(), 'original maintenance baseline pin cannot be a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'issue_id': issue, 'baseline': ref}
    try:
        with path.open('x') as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write('\n')
    except FileExistsError:
        require(json.loads(path.read_text()) == payload,
                'original maintenance baseline is already pinned; preserve cumulative issue changes')


def navigate(root, issue, base_ref, role, map_ref, targets, docs, use):
    """Print selected references and record how the role will use this dependency slice."""
    load(root, base_ref, 'baseline', issue)
    require(role in ROLES, 'unknown orientation role')
    require(map_ref.startswith(MAP + '#'), 'select a heading in the code map')
    require(len(set(targets)) >= 2 and all('::' in t for t in targets),
            'name an owning symbol/file and at least one distinct caller, consumer or test')
    require(bool(docs), 'name an applicable documentation or instruction contract')
    require(explanation(use), 'explain how these references guide this issue (at least 40 characters)')
    refs = list(dict.fromkeys([map_ref, *targets, *docs]))
    entries = [excerpt(root, r) for r in refs]
    for entry in entries:
        # Bound each display. Large symbols still require a focused Read/rg follow-up.
        lines = entry['text'].splitlines()
        print(f"\n--- {entry['ref']} ({len(lines)} lines; sha256={entry['sha256']}) ---", file=sys.stderr)
        print('\n'.join(lines[:65]), file=sys.stderr)
        if len(lines) > 65:
            print('Excerpt truncated: use a focused Read/rg for the relevant body.', file=sys.stderr)
    payload = envelope('orientation', issue)
    payload.update(baseline=base_ref, role=role, map=map_ref, targets=targets,
                   documents=docs, use=use,
                   references=[{k: e[k] for k in ('ref', 'sha256', 'components')} for e in entries])
    return save(root, payload)


def validate_orientation(root, ref, issue, base_ref, role, fresh=True):
    record = load(root, ref, 'orientation', issue)
    require(record.get('baseline') == base_ref and record.get('role') == role,
            f'{role} orientation must belong to this baseline and role')
    require(explanation(record.get('use')), f'{role} orientation lacks a substantive use explanation')
    require(isinstance(record.get('map'), str) and record['map'].startswith(MAP + '#'),
            f'{role} orientation must select a map heading')
    targets, docs = record.get('targets'), record.get('documents')
    require(isinstance(targets, list) and all(isinstance(t, str) and '::' in t for t in targets)
            and len(set(targets)) >= 2, f'{role} orientation needs owner and related code/test targets')
    require(isinstance(docs, list) and docs and all(isinstance(d, str) for d in docs),
            f'{role} orientation lacks its documentation contract')
    entries = record.get('references')
    require(isinstance(entries, list) and all(isinstance(e, dict) for e in entries),
            f'{role} orientation lacks reference hashes')
    require({e.get('ref') for e in entries} == {record['map'], *targets, *docs},
            f'{role} orientation references are incomplete')
    stale = []
    for entry in entries:
        require(isinstance(entry.get('sha256'), str) and len(entry['sha256']) == 64,
                f'{role} orientation has invalid hashes')
        if fresh:
            try:
                current = excerpt(root, entry['ref'])
                if current['sha256'] == entry['sha256']:
                    continue
                before, after = entry.get('components', {}), current.get('components', {})
                components = [key for key in before.keys() | after.keys() if before.get(key) != after.get(key)]
                stale.append({'target': entry['ref'], 'changed': components or ['legacy_hash'],
                              'before': entry['sha256'], 'after': current['sha256']})
            except (OSError, ValueError) as exc:
                stale.append({'target': entry['ref'], 'before': entry['sha256'], 'after': None, 'error': str(exc)})
    require(not stale, f'stale {role} orientation: receipt={ref}; changes={json.dumps(stale)}; '
            f'resume the same {role}, inspect every changed target, navigate again, '
            'run the affected independent check and return a fresh footer')
    return record


def draft(root, issue, base_ref, previous_ref=None):
    """Build complete coverage, optionally retaining measured unchanged judgments.

    Explicit dependency references permit selective reuse. Judgments with no
    declared dependency slice conservatively depend on the whole inventory.
    Every changed or unmeasured judgment remains blank for human review.
    """
    base = load(root, base_ref, 'baseline', issue)
    current = snapshot(root)
    payload = envelope('documentation', issue)
    payload.update(baseline=base_ref, candidate=digest(current),
                   changes=changes(base['files'], current),
                   dispositions=[{**r, 'action': '', 'reason': '', 'references': []}
                                 for r in changes(base['files'], current)],
                   map_delta={'status': '', 'reason': '', 'references': []})
    if previous_ref:
        previous = load(root, previous_ref, 'documentation', issue)
        require(previous.get('baseline') == base_ref, 'prior documentation report uses a different baseline')
        require('references' in previous, 'reuse requires a sealed documentation report')
        prior_rows = {r['target']: r for r in previous.get('dispositions', [])}
        for index, row in enumerate(payload['dispositions']):
            prior = prior_rows.get(row['target'])
            if prior and prior.get('change') == row['change'] and prior.get('judgment_inputs'):
                try:
                    valid = prior['judgment_inputs'] == judgment_inputs(root, prior, current)
                except (ValueError, OSError, KeyError):
                    valid = False
                if valid:
                    payload['dispositions'][index] = copy.deepcopy(prior)
                    payload['dispositions'][index]['reused_from'] = previous_ref
        delta = previous.get('map_delta', {})
        # Map judgments discuss routes across the entire inventory. Their reuse
        # requires the same inventory, retaining coverage of new dependencies.
        if previous.get('candidate') == payload['candidate'] and delta:
            payload['map_delta'] = copy.deepcopy(delta)
        payload['previous_report'] = previous_ref
    return payload


def unit_inputs(current, target):
    """Include enclosing definitions that supply closures or class-level values."""
    path, _, symbol = target.partition('::')
    units = current.get(path, {}).get('units', {})
    unit = units.get(symbol)
    if unit is None:
        return None
    result = {k: unit.get(k) for k in ('sha256', 'context', 'docs')}
    parents = ['.'.join(symbol.split('.')[:n]) for n in range(1, len(symbol.split('.')))]
    result['parents'] = {name: units[name]['sha256'] for name in parents if name in units}
    return result


def judgment_inputs(root, row, current):
    """Measure a target's context, explicit dependencies and cited explanations."""
    target = unit_inputs(current, row['target'])
    dependencies = row.get('dependencies', [])
    require(isinstance(dependencies, list) and all(isinstance(d, str) for d in dependencies),
            f"{row['target']}: dependencies must be a list of references")
    refs = sorted(set(row.get('references', []) + dependencies))
    hashes = [{k: entry[k] for k in ('ref', 'sha256', 'components')} for entry in (excerpt(root, r) for r in refs)]
    return {'target': target, 'references': hashes,
            'dependency_contexts': {ref: unit_inputs(current, ref) for ref in dependencies if '::' in ref},
            'dependency_inventory': None if dependencies else digest(current)}


def docs_measure(files, ref):
    """Compare source prose separately from executable text for an 'updated' claim."""
    path, _, symbol = ref.partition('::')
    path, sep, anchor = path.partition('#')
    file = files.get(path, {})
    if sep:
        value = file.get('sections', {}).get(anchor)
        return value, value is not None
    unit = file.get('units', {}).get(symbol or '<module>', {})
    return unit.get('docs'), unit.get('has_docs', False)


def validate_report(root, report, issue, base_ref, current=None):
    base = load(root, base_ref, 'baseline', issue)
    require(report.get('version') == 1 and report.get('kind') == 'documentation' and report.get('issue_id') == issue
            and report.get('baseline') == base_ref, 'documentation report identity/baseline mismatch')
    current = snapshot(root) if current is None else current
    require(report.get('candidate') == digest(current), 'documentation report is stale; regenerate the change inventory')
    expected = changes(base['files'], current)
    require(report.get('changes') == expected, 'documentation change inventory omits or misstates affected targets')
    rows = report.get('dispositions')
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), 'documentation dispositions are required')
    require(len(rows) == len(expected) and {r.get('target') for r in rows} == {r['target'] for r in expected},
            'documentation dispositions must cover every affected function/module exactly once')
    expected_by_target = {r['target']: r['change'] for r in expected}
    refs = set()
    for row in rows:
        target = row['target']
        require(row.get('change') == expected_by_target[target], f'{target}: incorrect change kind')
        action = row.get('action')
        require(action in ('updated', 'reviewed_unchanged', 'removed'), f'{target}: missing documentation action')
        require(action != 'removed' or row['change'] == 'removed', f'{target}: only a removed target can use removed')
        require(explanation(row.get('reason')), f'{target}: explain the resulting contract or why its descriptions remain accurate')
        links = row.get('references')
        require(isinstance(links, list) and links and all(isinstance(r, str) for r in links), f'{target}: documentation references are required')
        for link in links:
            excerpt(root, link)
            require(docs_measure(current, link)[1], f'{target}: {link} contains no inventoried documentation')
        if action == 'updated':
            require(any(docs_measure(base['files'], r)[0] != docs_measure(current, r)[0] for r in links),
                    f'{target}: updated requires a measured documentation edit; executable edits alone do not qualify')
        refs.update(links)
        measured = judgment_inputs(root, row, current)
        if 'judgment_inputs' in row:
            require(row['judgment_inputs'] == measured, f'{target}: documentation judgment inputs changed')
        if row.get('reused_from'):
            previous = load(root, row['reused_from'], 'documentation', issue)
            require(previous.get('baseline') == base_ref and 'references' in previous,
                    f'{target}: invalid documentation reuse source')
            found = [r for r in previous.get('dispositions', []) if r.get('target') == target]
            require(len(found) == 1 and found[0].get('judgment_inputs') == measured,
                    f'{target}: reused judgment has changed target, dependencies or references')
            require(all(row.get(k) == found[0].get(k) for k in
                        ('action', 'change', 'reason', 'references', 'dependencies')),
                    f'{target}: reused judgment text differs from its sealed source')
    delta = report.get('map_delta')
    require(isinstance(delta, dict) and delta.get('status') in ('updated', 'MAP-OK'), 'map_delta needs updated or MAP-OK status')
    require(explanation(delta.get('reason')), 'map_delta requires a concrete explanation of the affected route/contracts')
    mapped = delta.get('references')
    require(isinstance(mapped, list) and mapped and all(isinstance(r, str) and r.startswith(MAP + '#') for r in mapped),
            'map_delta must reference the relevant map headings')
    changed = base['files'].get(MAP, {}).get('sha256') != current.get(MAP, {}).get('sha256')
    require((delta['status'] == 'updated') == changed, 'map_delta status disagrees with measured map changes')
    refs.update(mapped)
    hashes = [{k: e[k] for k in ('ref', 'sha256', 'components')} for e in (excerpt(root, r) for r in sorted(refs))]
    if 'references' in report:
        require(report['references'] == hashes, 'documentation reference hashes are stale or incomplete')
    return hashes


def seal(root, report):
    """Validate a human-authored disposition plan and seal exactly the current candidate."""
    require(isinstance(report, dict), 'documentation plan must be an object')
    current = snapshot(root)
    report['references'] = validate_report(root, report, report.get('issue_id'), report.get('baseline'), current)
    for row in report['dispositions']:
        row['judgment_inputs'] = judgment_inputs(root, row, current)
    return save(root, report)


def check_start(root, start):
    """Check the recorded initial orientation; it remains historical during corrections."""
    errors = []
    try:
        state = start.get('maintenance')
        require(isinstance(state, dict), 'issue-start.maintenance is required before implementation')
        load(root, state.get('baseline'), 'baseline', start.get('id'))
        original = original_baseline(root, start.get('id'))
        require(not original or state.get('baseline') == original,
                'issue-start must preserve the original maintenance baseline across iterations')
        validate_orientation(root, state.get('orientation'), start.get('id'), state['baseline'], 'arch', fresh=False)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return errors


def historical_completion(entry, record, base, base_ref):
    """Recognize an explicitly retained completion predating commit-based recovery.

    This preserves the original hook evidence. It supplies no navigation or final
    documentation approval; current reviewers must establish those independently.
    """
    history = entry.get('maintenance_history')
    if history is None:
        return False
    recovery = base.get('recovery') or {}
    require(recovery.get('git_base') and explanation(recovery.get('reason')),
            'historical completion requires explicit commit-based baseline recovery')
    require(isinstance(history, dict) and history.get('status') == 'predates_recovery'
            and history.get('baseline') == base_ref and explanation(history.get('reason')),
            'invalid maintenance_history disposition')
    timestamp = record.get('ts')
    require(isinstance(timestamp, str), 'historical completion needs the captured hook timestamp')
    captured = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    recovered = dt.datetime.fromisoformat(base['created_at'])
    require(captured.tzinfo and recovered.tzinfo and captured + dt.timedelta(seconds=1) <= recovered,
            'completion does not predate recovered baseline')
    return True


def check_done(root, start, done, records, candidate_signature):
    """Gate completion for every workflow, including records without a workflow field.

    Earlier role completions retain historical navigation. Current Arch and final
    approving reviewers need fresh references; every supplied completion needs
    its own role-bound orientation in the captured hook footer. Report approval
    is independently captured by each reviewer whose candidate is current.
    """
    if done.get('outcome') != 'completed':
        if not (start or {}).get('maintenance'):
            return []
        errors = check_start(root, start)
        if done.get('maintenance') and done['maintenance'].get('baseline') != start['maintenance'].get('baseline'):
            errors.append('partial completion must preserve the original maintenance baseline')
        return errors
    errors = check_start(root, start or {})
    try:
        state = done.get('maintenance')
        initial = (start or {}).get('maintenance') or {}
        require(isinstance(state, dict), 'issue-done.maintenance is required for completion')
        base_ref = initial.get('baseline')
        require(state.get('baseline') == base_ref, 'completion must preserve the original maintenance baseline')
        base = load(root, base_ref, 'baseline', done.get('id'))
        validate_orientation(root, state.get('orientation'), done.get('id'), base_ref, 'arch')
        report_ref = state.get('documentation')
        report = load(root, report_ref, 'documentation', done.get('id'))
        require('references' in report, 'documentation report must be sealed')
        validate_report(root, report, done.get('id'), base_ref)
        require(done.get('map_delta') == report['map_delta'], 'issue-done.map_delta must equal the sealed report disposition')
        from audit import audit_code_map, audit_instructions
        findings = audit_code_map(Path(root))['findings']
        findings += audit_instructions(Path(root), [MAP])['findings']
        require(not findings, f'code map audit has unresolved findings: {findings[:3]}')
        subs = done.get('subagents') or {}
        require(isinstance(subs, dict), 'subagents must be an object')
        receipt_owners = {}
        confirmed_reviewers = set()
        for role, entries in subs.items():
            require(isinstance(entries, list), f'{role}: expected completion list')
            for entry in entries:
                require(isinstance(entry, dict), f'{role}: invalid completion')
                if entry.get('waived'):
                    continue
                found = [r for r in records if r.get('agent_id') == entry.get('dispatch_id')
                         and r.get('event_id') == entry.get('dispatch_event_id')]
                require(len(found) == 1, f'{role}: documentation evidence needs one exact hook completion')
                raw_footer = found[0].get('footer')
                footer = raw_footer if isinstance(raw_footer, dict) else {}
                if found[0].get('status', 'completed') != 'completed':
                    from workflow_policy import resolved_dispatch
                    require(resolved_dispatch(found[0], records, done),
                            f'{role}: incomplete dispatch needs a completed continuation or explicit replacement')
                    # A failed turn may have produced no footer. Its actual
                    # status remains in history; the completed continuation or
                    # replacement supplies current navigation and approval.
                    if footer.get('orientation'):
                        validate_orientation(root, footer['orientation'], done['id'], base_ref, role, fresh=False)
                    continue
                require(isinstance(raw_footer, dict), f'{role}: completed dispatch needs a structured footer')
                if historical_completion(entry, found[0], base, base_ref):
                    continue
                from workflow_policy import current_review
                final_review = current_review(found[0], records, done, candidate_signature)
                validate_orientation(root, footer.get('orientation'), done['id'], base_ref, role, fresh=final_review)
                receipt_id = footer['orientation']['sha256']
                owner = receipt_owners.setdefault(receipt_id, entry.get('dispatch_id'))
                require(owner == entry.get('dispatch_id'), 'distinct agents must record their own navigation')
                if 'orientation' in entry:
                    require(entry['orientation'] == footer.get('orientation'), f'{role}: pasted orientation differs from hook')
                if final_review and footer.get('verdict') in ('APPROVE', 'APPROVE_WITH_FIXES'):
                    review = footer.get('documentation_review')
                    require(isinstance(review, dict) and review.get('report') == report_ref
                            and review.get('status') == 'confirmed' and explanation(review.get('notes')),
                            'Richard must confirm the exact sealed documentation report with substantive notes')
                    if 'documentation_review' in entry:
                        require(entry['documentation_review'] == review, 'pasted documentation review differs from hook')
                    confirmed_reviewers.add(entry.get('dispatch_id'))
        workflow = done.get('workflow') or {}
        require(isinstance(workflow, dict), 'workflow must be an object')
        minimum = workflow.get('minimum_reviewers', 0)
        require(type(minimum) is int and 0 <= minimum <= 2, 'invalid minimum reviewers')
        require(len(confirmed_reviewers) >= minimum,
                'final documentation approval requires the workflow minimum of current reviewers; historical completions cannot supply it')
    except (ValueError, OSError, KeyError, TypeError, SyntaxError) as exc:
        errors.append(str(exc))
    return errors


def parse_ref(value):
    """Accept the JSON reference printed by an evidence-producing command."""
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('baseline', help='save the working source before issue edits')
    capture.add_argument('--issue', required=True)
    capture.add_argument('--git-base', help='recover from a known commit; review every intervening change')
    capture.add_argument('--reason')
    nav = sub.add_parser('navigate', help='display a bounded dependency slice and save role evidence')
    nav.add_argument('--issue', required=True)
    nav.add_argument('--baseline', type=parse_ref, required=True)
    nav.add_argument('--role', choices=ROLES, required=True)
    nav.add_argument('--map', required=True)
    nav.add_argument('--target', action='append', required=True, help='path::qualified.symbol or path::<module>')
    nav.add_argument('--doc', action='append', required=True, help='path#heading or path::symbol')
    nav.add_argument('--use', required=True)
    reuse = sub.add_parser('check-orientation', help='check whether saved navigation can be reused')
    reuse.add_argument('--issue', required=True)
    reuse.add_argument('--baseline', type=parse_ref, required=True)
    reuse.add_argument('--role', choices=ROLES, required=True)
    reuse.add_argument('--receipt', type=parse_ref, required=True)
    plan = sub.add_parser('draft', help='generate a current change inventory with blank dispositions')
    plan.add_argument('--issue', required=True)
    plan.add_argument('--baseline', type=parse_ref, required=True)
    plan.add_argument('--previous', type=parse_ref, help='reuse unchanged judgments from a sealed report')
    for name in ('seal', 'check'):
        command = sub.add_parser(name, help='validate a filled documentation plan' if name == 'check' else 'validate and store a filled plan')
        command.add_argument('plan', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'baseline':
            result = baseline(args.root, args.issue, args.git_base, args.reason)
        elif args.command == 'navigate':
            result = navigate(args.root, args.issue, args.baseline, args.role, args.map, args.target, args.doc, args.use)
        elif args.command == 'draft':
            result = draft(args.root, args.issue, args.baseline, args.previous)
        elif args.command == 'check-orientation':
            validate_orientation(args.root, args.receipt, args.issue, args.baseline, args.role)
            result = {'valid': True, 'evidence': 'reused', 'orientation': args.receipt}
        else:
            report = json.loads(args.plan.read_text())
            require(isinstance(report, dict), 'documentation plan must be an object')
            result = seal(args.root, report) if args.command == 'seal' else {
                'valid': True, 'references': validate_report(args.root, report, report.get('issue_id'), report.get('baseline'))}
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, SyntaxError) as exc:
        parser.exit(1, f'documentation contract: {exc}\n')


if __name__ == '__main__':
    main()
