#!/usr/bin/env python3
"""Repeat the offline evidence-reuse measurement in one disposable ESX project."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'template/tools/esx'),str(ROOT)]
import test_framework
import doc_contract
import final_verification
import project
import records
import self_improvement as si
import team_accounting as accounting
import team_retrospective as retro
import verify


def run():
    fixture=test_framework.FrameworkTests('runTest');fixture.setUp();root=fixture.root
    try:
        begun=time.perf_counter()
        with contextlib.redirect_stderr(io.StringIO()):
            done=fixture.complete()
        setup_seconds=time.perf_counter()-begun
        reference=done['maintenance']['documentation'];signature=project.source_signature(root)
        assessment=root/si.BASE/'assessments/benchmark/assessment.md'
        assessment.parent.mkdir(parents=True)
        assessment.write_text('A measured administrative assessment with no executable or scientific changes.\n')
        assert signature==project.source_signature(root)
        report=doc_contract.load(root,reference,'documentation',fixture.issue)
        assert doc_contract.seal(root,report)==reference
        calls=[]
        for _ in range(5):
            tick=time.perf_counter()
            assert final_verification.run(root,done,'arch')['status']=='REUSED EVIDENCE'
            calls.append(time.perf_counter()-tick)
        with contextlib.redirect_stderr(io.StringIO()):
            tick=time.perf_counter();verify.run(root,'structural','arch',fresh=True);fresh=time.perf_counter()-tick
        cached=[]
        for _ in range(5):
            tick=time.perf_counter();verify.structural_evidence(root);cached.append(time.perf_counter()-tick)
        accepted=fixture.gate.check_done();records.save_history(root,accepted)
        draft=retro.draft(root)
        draft['no_problem_reason']='The offline replay preserved exact scientific and documentation evidence after an administrative edit; simulated native provider cost remains unknown.'
        retro.accept(root,draft)
        receipts=[json.loads(p.read_text()) for p in (root/project.STATE/'verification').glob('*.json')]
        executions={suite:sum(r.get('suite')==suite for r in receipts) for suite in ('focused','structural','scientific')}
        return {'protocol':'offline disposable periodic diffusion project; native dispatches simulated; scientific commands actually executed',
                'complete_fixture_seconds':setup_seconds,'fresh_structural_seconds':fresh,
                'cached_structural_seconds':cached,'cached_structural_median_seconds':statistics.median(cached),
                'final_reuse_seconds':calls,'final_reuse_median_seconds':statistics.median(calls),
                'executed_verification_receipts':executions,'administrative_signature_preserved':True,
                'exact_documentation_seal_preserved':True,'accepted_retrospectives':1,
                'accounting':accounting.summary(root),'additional_paid_provider_calls':0,
                'limits':'Measures wrapper reuse, not live model reasoning, production throughput or invoice savings.'}
    finally:
        fixture.doCleanups()


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
