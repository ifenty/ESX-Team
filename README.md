# ESX-team — Earth Science-X development and research framework

ESX-team is a reusable deployment of the ADX team organization: Arch coordinates,
Bob implements, Richard reviews independently, and Scout, Prober, Bisector and
Auditor supply bounded specialist evidence. It retains the issue loop, contracts,
agent continuity, staged verification, code-map/documentation maintenance,
open/closed issue records, lesson index/evidence archive and communication protocol.

This directory is the single master ESX repository. Receiving projects contain an
active installation and a small `ESX-team-local/` metadata directory. They do not
contain another copy of this repository. Scientific assumptions remain in each
receiving project.

## What gets deployed

| Path in the receiving project | Purpose |
|---|---|
| `CLAUDE.md` | Route the main session to the project and team contracts |
| `.claude/ESX-team/` | Arch's operating contract and role manifest |
| `.claude/agents/` | Bob, Richard, Scout, Prober, Bisector and Auditor |
| `.claude/skills/esx-*/` | Small common contract and on-demand procedures |
| `.claude/settings.json` | Session routing, completion capture, record checks and local loop Stop |
| `esx/project.json` | Project identity, scientific paths, commands, inputs and environment |
| `esx/project_profile.md` | Scientific, numerical, operational and authorization customization |
| `esx/templates/` | Blank brief, experiment, qualification matrix, report and closeout forms |
| `devel-loop/` | Loop, communication, verification, maintenance and record contracts |
| `tools/esx/` | Portable gate, verification, navigation, evidence, record and hook utilities |
| `docs/code_map.md` | Project-specific stage/owner/artifact/test routes |
| `docs/model_contract.md` | Implemented scientific model or analysis contract |
| `docs/doc_format_guide.md` | Documentation purpose, scientific clarity and rendering expectations |
| Root issue, lesson and milestone files | Human-readable project records with fenced blank examples |
| `devel-loop/loop_state/` | Ignored local evidence, active iteration state and durable loop history |
| `ESX-team-local/` | Installed version, project/deployment configuration, baselines, backups and deployment records |

The source template is under [template/](template/). It is intentionally unconfigured:
readiness checks fail until a new project supplies its scientific contract and
actual verification commands. Blank examples never count as real issues or lessons.

## Deploy into a project

Requirements for the supplied adapter: Python 3.10 or later on macOS or Linux/POSIX,
and a writable project folder. Verification uses POSIX file locks; the Claude hooks
use shell command syntax. Git is needed when recording commits or recovering a baseline from a commit.
The scientific project supplies its own compilers, packages, data and compute access.
Claude-specific integration additionally requires an authenticated Claude CLI and
hook support. The kit supplies its own bounded Ralph-style loop and retained
agent transport. An external Ralph plugin can remain installed with inactive state.

Preview a fresh installation, then apply the reviewed plan:

```sh
python3 /path/to/ESX-Team/esx_install.py --project /path/to/project
python3 /path/to/ESX-Team/esx_install.py --project /path/to/project --apply
```

Use `--config /path/to/completed-project.json` to install completed project
configuration in one transaction. The installer performs no commits, messages,
downloads, plugin installation or permission changes. It refuses collisions before
writing and records the exact installation in `ESX-team-local/deployments/`.

For an existing repository, it appends an ESX routing block to an existing CLAUDE.md,
adds missing ignore entries, and merges the ESX hooks into settings while
preserving unrelated settings and any external plugin Stop hook. ESX uses its own
loop state file; its launcher refuses overlapping active loop owners. Any different existing
file at another destination blocks the plan before writing. To reconcile collisions,
install into a staging directory and merge the specific contracts/records deliberately.
Existing issue and lesson history is never replaced automatically.

After installation:

1. Complete `esx/project.json`, including real source/test paths and commands.
2. Fill every `TODO_ESX` in `esx/project_profile.md` and `docs/code_map.md`. Use a
   justified not-applicable statement where a scientific topic does not apply.
3. Write the model/analysis contract and populate the qualification matrix. Connect
   equations, data conventions and acceptance criteria to actual source and tests.
4. Confirm the project runtime and allowed operations. Configure role models if
   desired; the templates omit model pins and inherit the runtime configuration.
5. Run `python3 tools/esx/loop_gate.py --doctor` from the project root.
6. Run the project's scientific and structural suites through the verification wrapper.
7. Qualify retained sessions with `agent_runtime.py probe`, then a bounded role/tool
   and peer-message task. Check `check_ralph_hook.py` and the ESX start/status/cancel
   lifecycle. Follow [execution.md](template/devel-loop/execution.md).

The loop command and lifecycle are in
[the loop contract](template/devel-loop/loop_contract.md). The installer leaves the
loop inactive and creates no live issue. Add a bounded first issue when ready.

## Customize the science and operations

`esx/project_profile.md` asks for the information a fresh agent needs to reason
correctly about an Earth science project:

- Governing equations or estimands; approximations, discretization and solvers.
- Variable dimensions, units, coordinates, calendars and temporal alignment.
- Grid topology, masks, boundaries, exchanges and missing-data semantics.
- Conservation, positivity, symmetry, stability and other correctness invariants.
- Controls, objectives, identifiable parameters and statistical assumptions.
- Independent oracles, sample counts, sensitivity, tolerances and uncertainty.
- Data provenance, subsets, licenses/access restrictions and external manifests.
- Compiler/interpreter, precision, parallel environment and reproducibility limits.
- Local/remote qualification, scheduler adapters, compute budget and output retention.
- Applicable commit, communication, deployment and resource authorization.

Research work uses the same evidence discipline. An issue may ask whether an
estimator is biased, a processing step changes a budget, or an inference survives
an independent baseline. A completed investigation records the supported answer
and its limits. Changes that affect scientific calculations or conclusions use
`scientific_change`, with implementation and independent review.

The blank [experiment contract](template/esx/templates/experiment.md) covers
hypotheses, confounders, data separation, replicates, uncertainty and baselines.
The [qualification matrix](template/esx/templates/verification_matrix.md) makes
local and full scientific acceptance explicit. Create domain-specific skills using
[the skill form](template/esx/templates/domain_skill.md), and add their Read paths
and triggers to the relevant role definitions.

## Configuration reference

| `project.json` field | Meaning |
|---|---|
| `project_id`, `project_name`, `mission` | Required deployment identity and purpose |
| `source_paths` | Actual scientific/analysis source directories or files |
| `test_paths` | Scientific checks, independent oracles, drivers and qualification fixtures |
| `configuration_paths` | Relevant lockfiles, solver settings, build files, parameter files and scripts |
| `output_paths` | Generated outputs excluded from source inventories; must not conceal a configured root |
| `external_inputs` | Explicit external input files; their actual bytes and resolved identities are hashed |
| `mirrored_paths` | Optional: `{"canonical": path, "mirrors": [path, ...]}` pairs for files a build/compile step needs its own local copy of (no shared-import mechanism available); `tools/esx/audit.py` flags any mirror whose bytes have drifted from its canonical source |
| `archive_paths` | Optional: paths holding superseded documentation kept for provenance. `tools/esx/audit.py` skips instruction-link checking beneath them, because their links describe a layout that no longer exists. A configured scientific root always wins, so real source/tests/configuration never become unchecked by being listed here |
| `environment_variables` | Environment values relevant to reproducibility; do not list credential variables |
| `toolchain_commands` | Foreground argv arrays reporting the actual compiler/interpreter/library environment |
| `command_timeout_seconds` | Maximum foreground command duration; choose for the declared workflow |
| `verification.structural` | Framework and project harness checks; includes the ESX audit |
| `verification.focused` | Implementation/correction battery; reviewers may supply a custom focused argv |
| `verification.scientific` | Complete required scientific acceptance suite; must be nonempty |
| `communication` | Provider/channel/format preferences and reference to applicable authorization |
| `commit_policy` | Commit preference and reference to applicable owner authorization |

Paths within the project are relative to its root; list concrete directories for
source inventories, because directory symlinks are refused. External input files may use
absolute paths. Keep big datasets outside source inventories; use representative
qualification inputs for local checks. Every relevant executable dependency must
be included through source/test/configuration paths or toolchain/environment probes.
A wrapper cannot discover undeclared scientific dependencies.

Commands are JSON argv arrays, such as `["{python}", "tests/check_mass.py"]`.
`{python}` selects the verification wrapper's interpreter. There is no implicit
shell expansion. For Fortran or MPI builds, call a checked project script or use
an explicit shell argv and preserve the command's real exit status. A cluster
adapter must wait, collect outputs and return the checked scientific verdict.

## What is preserved from the team workflow

Arch supplies a bounded outcome, invariant set, evidence and acceptance criteria.
Bob resolves ordinary implementation choices and reports contradictory evidence.
Richard independently checks a stable candidate. Additional reviewers follow
explicit mathematical risk criteria. Specialists are optional and have stopping
conditions. The same agents are resumed for corrections; after two unsuccessful
rounds they hold a short diagnosis checkpoint.

Implementation uses focused checks. Richard selects an independent witness.
One owner supplies the final complete suite, with content-matching evidence reused
explicitly. New defects receive a scope decision: introduced regression, required
dependency, separate existing defect or unknown. A separate defect gets its own
reproducer and issue; accepted work does not silently expand into another project.

Code, documentation and map use carry equal acceptance weight. Baselines include
the existing working tree. Navigation receipts identify actual source/map/doc slices.
Python AST inventories include qualified nested definitions; other languages use
file/module contracts. Every changed target receives a justified documentation
review, and final reviewers confirm the exact sealed report.

Issue and lesson IDs remain stable. An active lesson is a short principle with a
trigger and detailed evidence. Archive lessons with rationale; never reuse IDs.
Project reference docs describe implemented behavior and scientific justification.
Issue and milestone records preserve the development history.

Arch announces only within applicable authorization. Delivery is best effort.
Commits remain an explicit disposition. Closeout history retains the complete
validated record, including commit and communication results. A later delivery
update refreshes the same iteration without incrementing its count.

## Runnable local demonstration

Create a disposable project, then install the small diffusion model and its profile:

```sh
python3 ESX-team/deploy.py /tmp/esx-diffusion --apply \
  --config ESX-team/examples/periodic_diffusion/project.json
cp -R ESX-team/examples/periodic_diffusion/src /tmp/esx-diffusion/
cp -R ESX-team/examples/periodic_diffusion/tests /tmp/esx-diffusion/
cp ESX-team/examples/periodic_diffusion/project_profile.md /tmp/esx-diffusion/esx/
cp ESX-team/examples/periodic_diffusion/code_map.md /tmp/esx-diffusion/docs/
cd /tmp/esx-diffusion
python3 tools/esx/loop_gate.py --doctor
python3 tools/esx/verify.py --suite scientific --owner arch
python3 tools/esx/verify.py --suite scientific --owner arch
```

The second identical verification reports REUSED EVIDENCE. The model performs a
periodic explicit diffusion update. Its independent discrete Fourier oracle checks
32 cells over twelve steps, mass conservation, finite values, nontrivial decay and
rejection of unstable parameters. It qualifies that small synthetic example.
[Additional domain adaptations](examples/README.md) cover observational processing,
Fortran/MPI models and inverse/ML research.

## Test the kit

```sh
python3 ESX-team/run_tests.py
```

Tests deploy into temporary folders, including paths containing spaces, and exercise
actual project scripts plus simulated runtime hook events. They cover deployment
merges/collisions, configuration readiness, different scientific directory layouts,
positive closeout, risk-based review, exact completion correlation, receipt/log
integrity, source/input drift, failed/empty checks, code-map/documentation drift,
lesson consistency, resumed completion IDs and commit/communication history.

See [VALIDATION.md](VALIDATION.md) for the measured result and its qualification
boundary. The default test runner makes no provider calls or external notifications.
An opt-in live qualification checks real retained sessions, tool access and Bob's
direct correction request to the same Richard in a disposable project:

```sh
python3 ESX-team/tests/live_runtime.py --timeout 180
```

This uses the configured Claude provider and may incur its normal usage charges.
It preserves artifacts in the reported scratch folder. After a timeout, use
`--resume-root /path/printed/by/the/test` to continue those same role sessions. Neither the offline suite
nor this transport smoke certifies a receiving project's scientific results or
its feature-development throughput. Each deployment supplies its own acceptance.

An optional adapter test executes an explicitly selected installed plugin's setup
and Stop scripts in a temporary directory with synthetic transcripts:

```sh
python3 ESX-team/tests/check_installed_ralph.py --plugin /path/to/ralph-wiggum/version
```

It checks prompt preservation, reinjection, completion-promise termination and the
finite iteration cap. This is optional compatibility coverage; ESX itself uses
the project-owned handler tested by test_ralph.py. It requires the plugin's own shell dependencies and creates
no live agent session. It leaves the project's active loop state untouched.

## Workflow debugging and upgrades

[The framework map](template/docs/esx_framework_map.md) locates owning modules,
contracts and tests. [The execution contract](template/devel-loop/execution.md)
gives exact resume/message, candidate and closeout commands. Inspect the captured
records before changing acceptance policy. Failed and interrupted calls preserve
truthful status; a newer failure cannot leave an old approval usable for closure.

Preview and apply an upgrade from this master repository:

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --apply
```

The upgrader uses the baseline recorded by the preceding installation. Unchanged
framework files update directly. Project-owned configuration, scientific maps,
issues and lessons remain untouched. Nonoverlapping framework customizations use a
three-way merge. Overlapping edits, missing baselines, downgrades and unversioned
master changes refuse the complete transaction. The apply phase rechecks every
input and saves rollback bytes before publishing. See [INSTALL_UPGRADE.md](INSTALL_UPGRADE.md).

## Start autonomous work

After configuring and qualifying a deployment, invoke `/esx-loop` in its main
Claude session. `/esx-loop --max-iterations 30` chooses a fresh budget; an existing
loop retains its assignments and budget. `/esx-loop status` inspects it and
`/esx-loop cancel` cancels it. Arch executes routine work without confirmation
under its Autonomous loop authority contract. Configure the interpreter and
record the owner's actual communication authorization in the project profile.

Required loop notifications are retained in `devel-loop/loop_state/notifications.json`.
Arch sends through the authenticated provider tool and records actual receipts or
concrete delivery failures. The gate prioritizes pending announcements. Failed
network delivery remains visible and permits scientific work to proceed.
# ESX-Team

## Version 1.5.0: eleven process fixes from a receiving project's retrospectives

Each change answers one measured `TEAM-*` issue filed by 1D_Mixing_Model. No
existing integrity check was relaxed; every change is additive or makes a refusal
more informative.

- **Interrupted is not failed (TEAM-VERIFY-RERUN-001).** A final scientific run killed
  by a signal, or ending without a pytest summary, records `INTERRUPTED`; a source
  change during the run records `SOURCE_CHANGED`; `FAILED` means only a real test
  failure. With no current receipt, `--check-done` names the latest attempt's status,
  log and failure-line count instead of an `Errno 2`. `loop_lifecycle.py rebind-receipt`
  re-points a prepared closeout at a later matching receipt and refuses one whose
  review signature differs, replacing a hand edit of `issue-done.json`.
- **The ledger records only accepted work (TEAM-LEDGER-AHEAD-001).** `--check-done`
  now moves a completed entry from `open_issues.md` to `closed_issues.md` itself, as a
  journaled transaction validated by the full gate, with `Date Resolved` equal to the
  acceptance time. A refused closeout writes nothing. Entries moved by hand are still
  accepted. Previously the ledger had to claim a resolution before validation; one
  such claim stood unqualified for 3h10m.
- **All closeout requirements at once (TEAM-CLOSEOUT-DOCTOR-001,
  TEAM-REITERATION-CLOSEOUT-001).** Read-only `loop_gate.py --closeout-doctor [--done
  PATH]` lists every unmet requirement and the fields `review_signature` binds, and
  replays the strict gate against the staged ledger move, so `ready` means
  `--check-done` would accept. `prepare-done` finds the prior closeout itself and
  drafts a `replacements` entry per failed turn with `reason` and `evidence_refs`
  left for Arch. Scope decisions accept `separate_new`. The verification and runtime
  identity refusals name the values they need, and waiving a failed review is
  explained as invalid.
- **Reviewers see the current seal (TEAM-SEAL-CITATION-001).** Reviewer briefs carry a
  labeled section with the current sealed documentation report's path and sha256,
  pre-filled in the example footer. An approval citing any other seal is rejected at
  capture with both hashes named, not at final verification.
- **Enumerate stale documents up front (TEAM-DOC-SWEEP-001).** `brief.py --sweep-symbol
  NAME` (repeatable) lists every project file mentioning the name, with line numbers,
  whether or not the change touches it. Capped at 50 files and 20 lines per file.
- **Re-orientation without retyping (TEAM-ARCH-REORIENT-001).** `doc_contract.py navigate
  --reuse-args <receipt> --use '<fresh>'` reloads the recorded map, targets and
  documents and still prints every excerpt. It needs a new `--use`, rejects echoed
  hashes, and refuses when the change lies outside the declared slice.
- **Retrospectives record what worked (TEAM-RETRO-SUCCESS-001).** Schema 3 adds
  `confirmations` (category, summary, evidence). An empty `problems` list may be
  explained by one confirmation with evidence of at least 60 characters, the same
  floor `no_problem_reason` has. Schema 2 is still accepted; recurrence counts
  problems only.
- **Coordinator cost is measurable (TEAM-COORDINATOR-COST-001).** Gate commands log
  Arch wall time as role-tagged phases, and `team_accounting.py record-arch --issue ID
  --phase P --minutes M [--usd X] --source TEXT` records main-session cost with
  provenance. `coordinator_coverage` reads `recorded` only with a self-report or
  driver receipt. Dispatched-agent figures keep their meaning, and each
  retrospective's `measured.cost_scope` says whether coordinator cost is included.
- **One record for a dead transport (TEAM-DEAD-TRANSPORT-001).** `notifications.py
  outage` covers every queued and later event for a provider in the current run.
  `status` separates these from `failed` sends. While an outage is active, `--next`
  requires a `reprobe` every iteration or every 10 covered events, and the outage
  must be renewed with fresh evidence after 5 iterations. `reprobe --result up`
  clears it.
- **Sourced cost figures (TEAM-ESTIMATE-EVIDENCE-001).** `issue_priority.md` requires
  scoping cost figures to name their source, and a cost-based deferral to rest on a
  measured cheap prefix of the real command.

## Version 1.4.0: an issue no longer re-judges another issue's accepted work

A baseline is pinned write-once, deliberately, so a fresh working-tree capture
cannot hide cumulative edits. The consequence was that an issue left open while the
tree moved inherited every other issue's changes into its own candidate diff.
Measured in a receiving project after four unrelated closures: one issue needed 85
judgments, another 58, another 54 -- overwhelmingly work those other issues had
already dispositioned and whose closeouts had been accepted with review.

Dispositions gain a `carried_forward` action, prefilled by `doc_contract.draft`.
The proof is exact rather than by baseline ancestry: a sealed disposition records
its target's own byte state in `judgment_inputs.target.sha256`, so a target whose
**current** state was already judged under another issue's accepted closeout has
genuinely been reviewed, and its provenance is cited instead of restated.

The integrity property is preserved on every side. `validate_report` re-derives the
attribution and never trusts the report's claim, since the whole force of the action
is an assertion about some *other* closeout. A target that changed since that seal
has a different state and still needs a judgment. An issue cannot carry forward its
own judgment. Only closeouts recorded `completed` qualify, so a partial iteration's
dispositions confer nothing.

Together with 1.3.0's `upgrade_supplied`, the two attributions leave an issue
judging what it actually changed. In the observed project one issue fell from 18
judgments to 1.

## Version 1.3.0: an upgrade no longer makes every open issue harder to close

`FRAMEWORK_PATHS` includes `tools/esx` and participates in the inventory a
candidate diff is computed over, so upgrading ESX put every changed framework
symbol into the candidate diff of every open project issue. Measured in a receiving
project immediately after a 1.1.1 to 1.2.2 upgrade with six issues open: each
gained 18 to 20 framework-owned disposition targets, and one gained **18 of 18** --
its own deliverables sat outside the scanned roots, so closing it would have meant
a report-splitting issue certifying documentation for `team_budget.py::observe`.
Before that upgrade the same issue's diff was a single target.

Dispositions now carry an `upgrade_supplied` action. `doc_contract.draft` fills it
in automatically when both the baseline and current bytes of a framework file are
states a recorded applied upgrade produced, citing the deployment record that
supplies them, so no judgment is asked for work the issue did not do.

The integrity property is preserved rather than traded away. `validate_report`
re-derives the attribution from `ESX-team-local/deployments/` and never trusts the
claim in the report, because a claimed upgrade origin is exactly what a local edit
could forge. A genuinely patched framework file matches no recorded upgrade state
on at least one endpoint, so it still requires an explicit judgment -- which is how
this project's own two framework patches reached review before being upstreamed
into 1.1.1. Unapplied previews and project-owned files never attribute. The
deployment record is deliberately not sealed into `references`, since it lives
under the ignored `ESX-team-local/` tree; absent records fail validation loudly
instead of passing silently.

## Version 1.2.2: separate effort from elapsed time, and say which budget ran out

Two corrections to 1.2.x, both from an operator reading the output and asking what
it meant.

`ralph_stop.py` announced "The ESX work budget is exhausted" when it meant the
loop's iteration budget. That read naturally while allocations were caps; with cost
caps gone it reads as money. It now names the iteration budget and its limit, and
states outright that cost and effort are measured rather than capped.

The `minutes` dimension compared against elapsed time since a scope's first
dispatch, so an issue carried across iterations accrued every hour spent
elsewhere. Measured in a receiving project: one issue reported 436.8 calendar
minutes against 92.3 minutes of actual dispatch, and another 136.4 against 28.6 --
both "overruns" were artifacts, and raising the nominal allocation would have
buried the measurement bug under a bigger number. Effort is now summed dispatch
duration via `scope_effort`, and elapsed time is recorded separately as
`calendar_minutes` with its meaning stated in the record. The nominal 120 minutes
stays: measured effort across nine issues ran 21 to 92 minutes, well inside it.

## Version 1.2.1: an elapsed allocation must not hand back a past deadline

Found by using 1.2.0 immediately: removing the refusal left `reserve` still
returning the scope's own deadline, so a turn launched against an already-elapsed
nominal allocation received a deadline in the past and `run_turn` killed it at
launch -- observed as a 0.18-second "timeout" with `returncode -15` and an empty
report, on an issue whose only remaining work was a reseal.

The returned deadlines bound one turn's liveness; they were never meant as a
cumulative cap. Only still-future scope deadlines now constrain a turn, and every
turn gets a real horizon: its own `--timeout` when given, otherwise the scope's
nominal duration measured from now. The elapsed wall time is still recorded as an
overrun, and a scope's stored deadline still never resets. Two regression tests
cover both directions -- an expired scope yielding a usable future deadline, and a
still-valid scope deadline continuing to bound a longer turn.

## Version 1.2.0: cost and effort are measured, never capped

Allocations are now **nominal expectations, not caps**. `team_budget` no longer
refuses anything: spend, wall clock, tool calls, correction rounds and provider
overshoot are each recorded under a scope's `overruns` with the expected value, the
observed magnitude and first/last observation times. Repeated crossings of one
dimension update that record instead of growing it, so monitoring cannot itself
become a cost. `Exhausted` is retained for callers that catch it but is never
raised. The loop's own `max_iterations` is the single enforced terminal bound.

No provider spend cap is passed either: `agent_runtime` and `team_driver` have
dropped `--max-budget-usd` and `--max-ai-credits`, so a turn is never truncated
mid-work over a pricing estimate. Copilot still requires an explicit credit/USD
liability, not to cap a run but because its rate is unpublished and the cost is
otherwise unmeasurable. `extend` no longer refuses a scope after a provider
overshoot; it exists to correct an expectation that measurement has shown to be
wrong, so later monitoring compares against a realistic baseline.

This came out of a receiving project where a 74-cent provider overshoot on a
12-dollar per-turn reservation set `breached` and made an issue permanently
undispatchable with half its wall clock and 48 of 60 dollars unspent -- while four
of five comparable turns had measured 11 to 19 dollars against the same 12-dollar
expectation. The unrecoverable failure attached to the one quantity nobody controls.

Two further fixes from the same project. A timed-out turn now records
`source_changed_during_turn` and `source_signature_at_finish`, so recovery reads
whether durable work landed rather than inferring it from a bare `failed` status;
that distinction decides whether to resume or restart, and 12 of 115 role dispatches
in that project timed out with their work already on disk. And `brief.py` now emits
the reseal instruction automatically, naming the oriented targets, because an
implementer who edits a target it was oriented on always invalidates its own
receipt -- three iterations there closed partial for exactly that, including one
where the coordinator explicitly told the implementer to skip it.

Upgrading changes no project records. Existing installations need a preview/apply
upgrade to receive these controls.

## Version 1.1.1: command-line qualification and configured archives

Two fixes found by a receiving project that had patched framework code to work
around both. `final_verification.py` now aliases itself into `sys.modules` when
executed as a script, so `verify.py`'s lazy import resolves to the running
module and the lease it just granted is honoured; previously the documented
command refused every active-issue scientific qualification while reporting that
the operator should run the command they were already running. Its regression
test invokes the real command in a subprocess, which is the only arrangement
that reproduces the defect. `esx/project.json` also accepts optional
`archive_paths`, excluding superseded documentation from instruction-link
checking, so retaining historical Markdown no longer requires editing
`audit.py`. A configured scientific root always outranks that exclusion.

## Version 1.1.0: measured and bounded team operation

The master includes shared run/issue/turn budgets, coordinator and child accounting,
mandatory measured retrospectives, recurring-issue follow-up, successful-start
receipts, generated briefs, early report validation, and recoverable ledger
promotion. See [bounded operations](template/devel-loop/team_operations.md) and
[self-improvement](template/devel-loop/self-improvement/README.md).

New process records and standing rules belong to each receiving project; upgrades
preserve them. Existing installations need a preview/apply upgrade to receive these
controls. Master changes alone do not change a running project. Qualify its real
provider separately; offline tests do not establish live savings or billing totals.
