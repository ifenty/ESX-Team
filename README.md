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
