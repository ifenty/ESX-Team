#!/usr/bin/env python3
"""Explicit closeout preparation and recoverable scientific issue promotion.

Preparation copies the reviewed packet and guarded receipt; mandatory judgments
come from metadata. It creates an unaccepted draft. Promotion stages the ledgers
and runs the full gate; check-done records the accepted iteration afterwards.
"""
import argparse
import json
from pathlib import Path
import sys
import ledger_transaction
from project import STATE, atomic_json, json_file, require


def prepare_done(root, packet, verification, metadata):
    start = json_file(root, STATE + '/issue-start.json')
    require(packet.get('id') == start['id'] and packet.get('timestamp') == start['timestamp'], 'packet must match the active iteration')
    allowed = {'summary', 'tests_status', 'milestone', 'lessons', 'lessons_na', 'rules_updated', 'rules_updated_na', 'git', 'communication'}
    require(isinstance(metadata, dict) and set(metadata) <= allowed, 'metadata has unsupported fields')
    require(len(str(metadata.get('summary', ''))) >= 40 and metadata.get('tests_status') in ('passing','failing','not_run'),
            'metadata needs a substantive summary and tests_status')
    require(isinstance(metadata.get('git'), dict) and isinstance(metadata.get('communication'), dict), 'record explicit Git and communication dispositions')
    done = dict(packet, **metadata, outcome='completed', state_version=start.get('state_version',1),
                iteration=start['iteration'], start_timestamp=start['timestamp'], open_issues_md_updated=True)
    done['verification'] = dict(packet.get('verification') or {}, final_owner=start['workflow']['final_verify_owner'])
    if start['workflow']['kind'] == 'scientific_change':
        require(verification.get('receipt') and verification.get('scientific'), 'supply the final_verification.py run result')
        done['verification'].update(receipt=verification['receipt'], scientific=verification['scientific'])
    import verify
    done['verification']['structural'] = verify.structural_evidence(root)
    done.setdefault('milestone', {'logged': False})
    atomic_json(root / STATE / 'issue-done.json', done)
    return {'status':'prepared', 'path': STATE + '/issue-done.json', 'accepted':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    sub=p.add_subparsers(dest='command',required=True)
    done=sub.add_parser('prepare-done')
    for name in ('packet','verification','metadata'):
        done.add_argument('--'+name,required=True)
    promote=sub.add_parser('promote')
    for name in ('issue','closure','expected-sha256'):
        promote.add_argument('--'+name,required=True)
    promote.add_argument('--apply',action='store_true')
    a=p.parse_args();root=a.root.resolve()
    try:
        if a.command=='promote':
            value=ledger_transaction.promote(root,'esx',a.issue,json_file(root,a.closure),a.expected_sha256,a.apply)
        else:
            value=prepare_done(root,json_file(root,a.packet),json_file(root,a.verification),json_file(root,a.metadata))
        print(json.dumps(value,indent=2));return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc)}));return 1


if __name__=='__main__':
    raise SystemExit(main())
