# ADX-to-ESX parity review and implementation — 2026-09-25

ESX master version **1.1.0** now incorporates the applicable ADX team controls.
The port keeps ESX's scientific configuration, frozen iteration timestamps,
retained identities, real independent checks and existing project customizations.
No receiving project was automatically upgraded. No live provider calls were made.

## Scope and evidence boundary

Reviewed ADX's 13 open process issues, 24 migrated closed issues, process changelog,
September 20/22/23 assessments and the current refactor commit **027d7f4** (including
its preceding process commits). The closed ADX labels retain their historical
meaning; they are not fresh proof of production savings. The source ledger still
contains publication/effectiveness caveats. This report evaluates executable
behavior and maps all 37 records below.

ESX started at **f8f6df1** with pre-existing uncommitted 1.0.2 work, including the
September 23 Mixing-derived improvements. Those changes were preserved: automatic
selection discovery, safe closeout defaults, footer guidance/signature command,
mirror checking and the conservative scientific-drift guard. The older advisory
assessment nudge is now supplemented by mandatory measured reflection.

## What changed

- Shared coordinator/issue/turn reservations, deadline and tool limits; unknown
  charges remain reserved and restart cannot reset the allocation. Explicit Owner
  extensions preserve prior liability and do not enlarge an independent run cap.
- Required measured retrospectives, owned process issues, recurring-problem
  follow-up, bounded standing rules and versionable reflection/accounting archives.
- Content-bound successful-start receipts; exact iteration matching; separate
  closed_at accounting time without changing ESX's start/done timestamp contract.
- Generated briefs and nested early footer checks, current structural evidence
  before review, stable handoffs and explicit closeout metadata.
- Recoverable open-to-closed promotion with preview, validation, locking,
  compare-and-swap, archived originals, interruption recovery and idempotency.
- Administrative findings can preserve expensive evidence. Live ledger integrity
  is still checked; executable witnesses, policy and declared scientific inputs
  remain in acceptance scope.
- Process phase accounting and explicit missing native/interactive-host coverage.
  Upgrades preserve project-owned process records, archives and standing rules.

The adaptation cycle also found and fixed a transport edge case: a provider that
never reads a large stdin prompt could block before the watchdog began. Prompt
writing now runs beside the watchdog; timeout still terminates the owned process
group. Both normal and failed exits clean up owned descendants. Interrupt handling
is restored after verification, and history refresh preserves the first closed_at.

Operating interfaces are documented in [team operations](../../template/devel-loop/team_operations.md),
[the self-improvement contract](../../template/devel-loop/self-improvement/README.md),
and [upgrade guidance](../../INSTALL_UPGRADE.md).

## Validation and measured performance

**283 tests passed across 13 modules in 100.41 seconds.**
The baseline had 223 tests; this change adds 60 checks. A fresh structural run in
the disposable diffusion replay took 0.197 seconds;
current cached structural evidence took a median 0.031 seconds
over five lookups. Five final-verification lookups reused the one scientific execution
with no administrative reseal. These are fixture-specific operation timings.

See [validation.json](validation.json) for commands, test counts, output hashes and
source hashes, [full output](final-tests.log), and [replay.json](replay.json) for the
disposable diffusion replay. The initial baseline had one sandbox restriction:
`ps` was denied in its existing descendant-cleanup test. The final suite ran with
process inspection enabled; this was not hidden by skipping that test.

The new stress/integration coverage includes concurrent reservations, unknown
charges, overshoot, correction/deadline exhaustion, restart accounting, long blocked
stdin, isolated process cleanup, nested footer failures, both ledger families,
concurrent promotion, interrupted writes, rollback, concurrent-edit refusal,
commit/evidence tampering, exact start receipts, mandatory empty-queue reflection,
recurrence/deferral expiry, administrative reuse and project-owned upgrade history.
Generated Bob and Richard briefs execute through deterministic local CLI fixtures;
Richard actually executes independent Fourier/conservation checks under its own
identity. These are offline transport tests, not live model quality measurements.

The replay executes real periodic-diffusion verification, adds an administrative
assessment, preserves the exact documentation seal, reuses scientific evidence five
times and accepts a measured retrospective. Its command is reproducible from any
working directory:

```sh
python3 /path/to/ESX-Team/self-improvement/2026-09-25-adx-parity/replay.py
```

Its timings measure this small fixture and evidence lookup; no causal production
cost-saving percentage is asserted. Additional paid provider validation spend was
**$0**. The cost of this editing session is not supplied by the project receipts.
Provider-reported USD remains distinct from invoices. Interactive Arch sessions
outside team_driver and native subagents retain explicit coverage gaps; a coordinator
pass is fully priced only after its provider result arrives, so an in-pass retrospective
may still mark that Arch cost unknown. Run totals retain the later receipt; complete
spend enforcement requires the metered coordinator and retained CLI path.

The applied master matches all **114** source hashes in the staged validation
receipt. A fresh configured installation from that master passed doctor, process
ledger validation and the actual diffusion scientific suite. See
[master-smoke.json](master-smoke.json).

## Deployment and remaining qualification

The changes are in the single ESX master and its deployable template. They are not
committed here and do not modify existing installed projects or launch their loops.
An installed project receives 1.1.0 through the existing preview/apply upgrader;
local conflicts must be reviewed through its ordinary three-way workflow. Preserve
any in-flight legacy identity, then use new preparation for state-version-2 gates.

Production cost-effectiveness still requires matched accepted tasks in a receiving
project, live provider receipts including Arch, and regression outcomes. Missing
observations are never backfilled as zero. ESX still requires explicit scientific
paths, commands, external inputs and toolchain declarations; undeclared scientific
dependencies cannot be inferred by this port. Copilot-specific ADX launcher fixes
are not a claim that ESX's alternate host is qualified.

## Complete fix disposition

Paths below are relative to `template/tools/esx` unless a longer path is shown.
The machine-readable equivalent is [fix-matrix.json](fix-matrix.json).

| ADX record | Disposition | ESX implementation/equivalent | Reason |
|---|---|---|---|
| `TEAM-LEDGER-PROMOTION-001` | Ported | `ledger_transaction.py / loop_lifecycle.py` | Preview, validation, locked CAS, original archives, journal, recovery and idempotency for both ledgers. |
| `TEAM-SELF-IMPROVEMENT-RECORDS-001` | Ported | `self_improvement.py / process_evidence.py` | Separate project-owned process records, generated index, commit/source/output-bound successful evidence, honest effectiveness claims. |
| `GATE-SAME-ISSUE-ITERATION-BOUNDARY-001` | Adapted | `loop_iteration.py / loop_gate.py` | Keep ESX frozen start/done timestamp; require exact iteration identity for new state and archive previous done records. |
| `GATE-DONE-WITHOUT-START-001` | Ported | `loop_iteration.py / loop_gate.py / final_verification.py` | Content-bound successful start receipt before retained dispatch, final science and new-state closeout; legacy explicitly identified. |
| `GATE-POSTVERIFY-PAPERWORK-DEADLOCK-001` | Adapted | `project.py / audit.py / verify.py` | Exclude administrative records from expensive fingerprints; validate live ledgers even on cached passes; science configuration overrides exclusion. |
| `VERIFY-SCOPE-COMMENT-COST-001` | Not applicable | `project.py / verify.py` | ESX has no ADX verify_manifest parser. Preserve arbitrary configured input bytes, including comments; do not assume a language-independent comment semantics. |
| `HARNESS-BRIEF-FOOTER-CONTRACT-001` | Adapted | `brief.py / footer_contract.py / agent_runtime.py` | Generate role briefs from the existing report form; validate nested types, exact identities, own orientation and real approval evidence before completion. |
| `HARNESS-GATE-BEFORE-REVIEW-001` | Ported | `agent_runtime.py / workflow_handoff.py` | Require the full configured structural suite for current state before Richard or review readiness; reuse exact current evidence. |
| `HARNESS-LIFECYCLE-INPUT-SHAPES-001` | Adapted | `workflow_handoff.py / loop_lifecycle.py` | Accept explicit empty constraints, emit stable handoffs, prepare unaccepted closeout from explicit metadata and actual verification. |
| `POLICY-WITNESS-LOCATION-AND-SIGNATURE-SCOPE-001` | Adapted | `project.py / devel-loop/team_operations.md` | Keep executable witnesses and normative instructions in inventory; register scientific witnesses and executable dependencies in project configuration. |
| `TEAM-BUDGET-CONTINUATION-001` | Ported | `team_budget.py` | Owner-recorded hashed CAS extension retains cumulative spend, unknown reservations, calls and history; cannot extend independent run cap. |
| `TEAM-ACCOUNTING-COVERAGE-001` | Adapted | `team_accounting.py / team_driver.py` | Coordinator/child/repair/provider totals, interval unions, timed phases, native unknowns, missing timing and billing coverage. |
| `TEAM-RECURRING-FOLLOWUP-001` | Ported | `team_retrospective.py` | Twice in three records schedules owning process work or one-closeout deferral; no new unrelated work until disposition. |
| `TEAM-STANDING-RULE-LIFECYCLE-001` | Adapted | `team_retrospective.py / devel-loop/loop_rules.md` | Print standing/recent rules; flag repeats; reject repeated standing rules in new reflections; 25-rule budget and explicit retirement guidance. |
| `TEAM-RETROSPECTIVE-ACTIONABILITY-001` | Ported | `team_retrospective.py / loop_gate.py` | All completed/partial/blocked closeouts create mandatory measured debt; problems need dispositions and open owners for deferral. |
| `TEAM-RETROSPECTIVE-HISTORY-VERSIONING-001` | Adapted | `team_retrospective.py / esx_manager.py` | Archive accepted reflection plus accounting outside ignored loop_state; upgrades preserve project history. |
| `TEAM-FOOTER-PATH-ANNOTATION-001` | Already compatible | `workflow_records.py / loop_gate.py` | ESX does not reject files_touched prose by path equality; exact identity and actual source/evidence remain authoritative. |
| `TEAM-EFFICIENCY-CYCLE-001` | Adapted | `team_budget.py / team_driver.py / runtime_tool_hook.py / bounded_command.py` | Shared run/issue/turn limits, 80% handoff, isolated timeouts, early reports and deterministic reuse; no reduced scientific review. |
| `TEAM-RALPH-STOP-PROBE-001` | Already present | `check_ralph_hook.py / tests/test_ralph.py` | Project-owned executable hook qualification and isolated optional installed-plugin checks. |
| `TEAM-RALPH-PROMPT-001` | Already equivalent | `loop_control.py / devel-loop/autonomous_prompt.md` | ESX has its own canonical persisted prompt; Copilot-specific launcher details do not transfer. |
| `TEAM-COPILOT-CONTINUATION-001` | Not applicable | `devel-loop/loop_contract.md` | ESX supports the project-owned Claude loop. Do not import a different host continuation guard. Alternate-host qualification remains separate. |
| `TEAM-COPILOT-LOOP-HOST-001` | Not applicable | `devel-loop/team_operations.md` | Copilot-specific ADX host integration is outside ESX current support. Shared low-level adapter code is not evidence of an ESX Copilot deployment. |
| `TEAM-REPO-LAYOUT-PORTABILITY-001` | Already present; preserved | `project.py / install-upgrade / tests/test_framework.py` | Paths resolve from deployment root, including spaces and invocation outside it; deployed template has no source-project dependency. |
| `TEAM-MULTICHECKOUT-HOOK-001` | Already equivalent | `check_ralph_hook.py / loop_control.py` | Each ESX project owns its hooks/state; external Ralph overlap is refused without changing global plugin settings. |
| `HARNESS-FINALVERIFY-INTERRUPT-TEST-RACE-001` | Adapted | `verify.py::execute` | Install SIGINT as well as SIGTERM/SIGHUP handling while owning execution, then restore inherited handlers. |
| `LOOP-CLOSEOUT-GENERATED-VIEW-INVENTORY-001` | Adapted | `project.py / self_improvement.py` | New generated process index is administrative and stable; ESX has no ADX scientific precedent index. |
| `LOOP-GATE-LESSONS-ROOT-001` | Already present | `records.py / loop_gate.py` | Lesson validation uses the explicit ESX project root, never the Git root parent. |
| `PRECEDENT-INDEX-VOLATILE-STAMP-001` | Already equivalent | `self_improvement.py::index_text` | Generated process index has no volatile generation timestamp; ADX precedent-specific tool is absent. |
| `DISPATCH-FOOTER-SPECIALIST-ROUND-001` | Already present; preserved | `agent role files / agent_report.json / test_runtime.py` | All specialist instructions name the actual correction_round; retained runtime checks it. |
| `RUNTIME-CONTRACT-TEST-AMBIENT-ENV-001` | Already equivalent | `runtime_recovery.py / test_runtime.py / test_workflow_recovery.py` | Environment settings are normalized and tests control relevant overrides; secrets remain hashed in contract diagnostics. |
| `LOOP-SILENT-SELFTERM-001` | Already present; extended | `ralph_stop.py / loop_control.py` | Bounded owned loop retains terminal reasons and corruption archives; now also persists retrospective debt. |
| `VERIFY-SKIP-SCOPE-GAP-001` | Already present; preserved | `project.py / verify.py / final_verification.py` | Verification fingerprints bind framework, configured source/tests/config, commands, external inputs, toolchain and environment; current acceptance is separately validated. |
| `SKILLS-DISCOVERY-LOCATION-001` | Already present | `template/.claude/skills/esx-*/SKILL.md / audit.py` | Skills occupy direct discoverable project skill directories; required files are checked. |
| `HARNESS-CONFIG-UNVERSIONED-001` | Already present | `template/.claude/settings.json / esx_manager.py / audit.py` | Versioned project hooks and integrity checks are installed from the master while preserving unrelated settings. |
| `LESSONS-PRUNE-BACKLOG-001` | Not applicable | `records.py` | ESX has no ADX-specific lesson-count limit to raise. Retain duplicate/evidence validation and project-owned lesson history. |
| `LOOPSTATE-IN-CLAUDE-DIR-001` | Already present | `project.py::STATE` | Durable evidence is in devel-loop/loop_state; only hook-owned continuation state remains under .claude and is excluded from signatures. |
| `GATE-SIG-UNTRACKED-ARTIFACTS-001` | Already equivalent | `project.py::selected / inventory_paths` | Configured output exclusions and cache/state exclusions preserve untracked real source and witnesses. No blanket tracked-only filter. |
