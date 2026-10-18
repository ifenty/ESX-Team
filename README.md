# ESX-Team

ESX-Team is a framework kit for research and development projects in Earth science.
It gives a project a team of Claude roles and a loop of work that stops on its own.
A gate checks the evidence before an issue closes.

> **Writing standard.** All prose in this repository follows ASD-STE100
> (Simplified Technical English). In an installed project, all text that a person reads follows
> the same standard. This covers issues, lessons, long-term goals, status and messages.
> Read [WRITING_STANDARD.md](WRITING_STANDARD.md) before you edit a document.
> Future edits must follow the standard.

## What the kit does

Arch is the main Claude session. The kit also has 6 agent roles. Each role has a bounded task.

| Role | Task |
|---|---|
| Arch | Coordinates the work, selects the issue, and runs the final verification. |
| Bob | Implements the change and keeps the tests and the documents correct. |
| Richard | Reviews the change independently and runs a check of the reviewer's own choice. |
| Scout, Prober, Bisector, Auditor | Give bounded evidence when Arch asks a specific question. |

The kit keeps the issue loop and the contract for each role. It keeps the records of open and closed issues
and the lessons. It keeps the map from code to documents. It also keeps the rules for what counts as evidence.
The science stays in the project. The kit contains no scientific assumption.

## Where the master repository is

The master repository is `https://github.com/ifenty/ESX-Team`.
A project does not contain a copy of the kit. A project contains the installed files and
a small folder named `ESX-team-local/` with the installed version and the baselines.

See [INSTALL_UPGRADE.md](INSTALL_UPGRADE.md) to install and to upgrade.

## Requirements

- Python 3.10 or later. We tested the kit with Python 3.10 and Python 3.14.
- Linux or macOS. The verification uses POSIX file locks, and the hooks use shell syntax.
- Git. The kit needs Git to merge files during an upgrade and to record commits.
- A writable project folder.
- The Claude command-line tool, logged in, for the agent roles and the loop.

The project supplies its own compilers, packages, data and compute.

## What the kit installs in a project

| Path in the project | Content |
|---|---|
| `CLAUDE.md` | Sends the main session to the project and team contracts. |
| `.claude/ESX-team/` | The operating contract of Arch and the role manifest. |
| `.claude/agents/` | The 6 role definitions. |
| `.claude/skills/esx-*/` | The common contract and the procedures that a role loads when it needs them. |
| `.claude/commands/esx-loop.md` | The `/esx-loop` command. |
| `.claude/settings.json` | The hooks for the session, the completion capture, the record checks and the loop stop. |
| `esx/project.json` | The project identity, paths, commands and environment. |
| `esx/project_profile.md` | The scientific, numerical and operational facts about the project. |
| `esx/templates/` | Blank forms for a brief, an experiment, a qualification matrix, a report and a closeout. |
| `devel-loop/` | The contracts for the loop, communication, verification, records and writing. |
| `tools/esx/` | The gate, the verification, the navigation, the evidence and the hook tools. |
| `docs/code_map.md` | The map of the project: stages, owners, files and tests. |
| `docs/model_contract.md` | The scientific model or analysis that the project implements. |
| Root files for issues, lessons and milestones | The records that people read. |
| `devel-loop/loop_state/` | Local evidence and state of the active iteration. Git ignores this folder. |
| `ESX-team-local/` | The installed version, the manifest, the baselines, the backups and the deployment records. |

The source of these files is [template/](template/). The template is not configured.
The readiness checks fail until the project gives its scientific contract and its real commands.

## Install the kit in a project

1. Clone the master repository:

   ```sh
   git clone https://github.com/ifenty/ESX-Team.git
   ```

2. Preview the installation. The preview writes nothing.

   ```sh
   python3 ESX-Team/esx_install.py --project /path/to/project
   ```

3. Read the plan. Then apply the same plan.

   ```sh
   python3 ESX-Team/esx_install.py --project /path/to/project --apply
   ```

Use `--config FILE` to install a completed `esx/project.json` in the same step.
The installer makes no commit, sends no message, downloads nothing and changes no permission.
It refuses a collision before it writes any file.

If the project has a `CLAUDE.md`, a `.gitignore` or a `.claude/settings.json`, the installer adds the ESX
lines and keeps the other lines. Any other existing file at an ESX path is a collision.
See [INSTALL_UPGRADE.md](INSTALL_UPGRADE.md) for the details.

## Set up the project

1. Complete `esx/project.json`. Give the real source paths, test paths and commands.
2. Replace every `TODO_ESX` in `esx/project_profile.md` and in `docs/code_map.md`.
   Write a reason where a topic does not apply.
3. Write the model contract in `docs/model_contract.md`. Connect the equations and the acceptance criteria to the source and the tests.
4. Run the doctor from the project root:

   ```sh
   python3 tools/esx/loop_gate.py --doctor
   ```

5. Run the structural suite and the scientific suite with the verification wrapper:

   ```sh
   python3 tools/esx/verify.py --suite structural --owner arch
   python3 tools/esx/verify.py --suite scientific --owner arch
   ```

6. Qualify the role sessions. Run `python3 tools/esx/agent_runtime.py probe`.
   Then follow [execution.md](template/devel-loop/execution.md).

The installer leaves the loop off and creates no issue. Add a first issue when the setup is complete.

## The fields of esx/project.json

Paths are relative to the project root. List real folders. The kit refuses a symbolic link to a folder.

| Field | Meaning |
|---|---|
| `project_id`, `project_name`, `mission` | The identity and purpose of the project. You must set them. |
| `source_paths` | The folders and files of the scientific source. |
| `test_paths` | The checks, the independent oracles and the test data. |
| `configuration_paths` | Build files, parameter files, lock files and scripts that change a result. |
| `output_paths` | Generated output. The kit leaves it out of the inventories. It must not hide a configured path above. |
| `external_inputs` | Files outside the project. The kit hashes the bytes of each file. |
| `mirrored_paths` | Optional. Pairs of a canonical file and the copies that a build needs. `audit.py` reports a copy that differs. |
| `archive_paths` | Optional. Old documents kept for history. `audit.py` does not check their links. |
| `documentation_paths` | Optional. Documents outside the tracked footprint. They never change the scientific signature. |
| `framework_test_paths` | Optional. Tests of the framework or of the records. They run in `structural` and stay out of the scientific inventory. |
| `environment_variables` | The variables that can change a result. Do not list a secret. |
| `toolchain_commands` | Commands that print the compiler, interpreter and library versions. |
| `command_timeout_seconds` | The longest time of one foreground command. |
| `python` | Optional. The absolute path of the interpreter. `{python}` in a command means this file. |
| `required_imports` | Optional. Python modules that the suites import. The doctor checks that they import. |
| `role_models` | Optional. The model for a role, as a name or as a default for new sessions. |
| `runtime.turn_timeout_seconds` | Optional. The time limit of one role turn, as a number or as a value for each role. |
| `verification` | The suites. See the next section. |
| `communication` | The provider, the channel, the message prefix, the authorization reference, `heartbeat_minutes` and `screen_status_minutes`. |
| `commit_policy` | The commit rule and the reference to the owner's authorization. |

`PATH` is usually in `environment_variables`. It is then part of the evidence fingerprint.
Evidence from one `PATH` is stale under another `PATH`. Run all the gate and verification commands of
one iteration with the same `PATH`.

## Verification suites

A command is an array of strings, for example `["{python}", "tests/check_mass.py"]`.
The kit does not use a shell. To run a shell script, call it as a command and keep its exit status.

| Key in `verification` | Use |
|---|---|
| `structural` | Checks of the framework and of the project records. It includes `audit.py`. |
| `focused` | Checks for the implementer. A reviewer can give one custom command. |
| `scientific` | The complete acceptance suite. It must not be empty. |
| `scientific_groups` | Replaces `scientific`. A list of groups, each with a `name` and `commands`. The groups run in order, and an interrupted run resumes. |
| Any other name | A list of commands. Run it with `verify.py --suite NAME --owner ID`. |

An issue of the kind `scientific_change` closes only when the complete `structural` suite and the
complete `scientific` suite (or all groups) pass. The kit does not accept part of a suite.

A project can use two tiers. A short suite in `scientific_groups` closes each issue.
A long suite, for example `full`, runs for releases and for large changes.
The runoff project does this. Its short suite takes about 6 minutes, and its long suite takes hours.

## Run the loop

Use the `/esx-loop` command in the main Claude session of the project.

| Command | Result |
|---|---|
| `/esx-loop` | Starts a loop of 30 iterations, or continues the active loop. |
| `/esx-loop --max-iterations N` | Starts a loop of N iterations. |
| `/esx-loop --permissions MODE` | Sets the permission mode of the role sessions (see below). |
| `/esx-loop status` | Shows the state. It starts nothing. |
| `/esx-loop pause`, `/esx-loop resume` | Holds the loop, or lifts the hold. A pause does not use an iteration. |
| `/esx-loop cancel` | Lets the active iteration finish. It starts no new iteration. |
| `/esx-loop abort` | Ends the loop now and abandons the active iteration. |

Arch does routine work without a question to the owner. Arch asks only for a decision that the
evidence and the authorization cannot give. The loop ends at the iteration limit.

### Permission mode of the role sessions

A role session runs without a person to answer a prompt. The kit passes a permission mode to each session.
The Claude command-line tool does not apply `permissions.defaultMode` from the settings files to such a session.

| Mode | Result for a role session |
|---|---|
| `auto` | The default. A classifier approves routine commands. It ran a compound command, a redirection, `taskset` and `docker` with no denial. |
| `bypassPermissions` | Runs every command with no check. The hook still enforces `deny` rules, the tool-call budget and the time limit. |
| `inherit` | Uses `permissions.defaultMode` from the settings files. It uses `auto` if that mode is not usable. |

The modes `acceptEdits`, `dontAsk`, `manual` and `plan` are not valid. Measured on 2026-10-18,
the first three denied the shell commands, and `plan` cannot write.
Each role definition in `.claude/agents/` also lists the tools of the role. This list applies in every mode.

## How the work flows

1. Arch selects one issue and records the baseline of the files.
2. Arch writes a brief. The brief states the behavior, the invariants, the scope and the oracle.
3. Bob implements the change and runs focused checks.
4. Richard reviews the candidate and runs a check that Richard selects.
5. Bob and Richard correct the change until Richard approves. After 2 rounds that fail, they stop for a short diagnosis.
6. Arch runs the complete scientific suite once, as the single owner of the final run.
7. Arch closes the issue, writes the retrospective, and commits.

The kind of work sets the review. A `scientific_change` needs Bob and Richard. A change needs a second Richard when it relaxes
a correctness guard, accepts a new supported class, or changes a fundamental algorithm. A `documentation` or `harness_change` has a lighter path.

Code, documents and the map have the same weight at acceptance. Every changed target needs a reason in
a documentation report. The final reviewer checks the exact report.

## Records and evidence

- Issue and lesson identifiers stay the same. Nobody reuses an identifier.
- `open_issues.md` holds open issues. The gate moves an issue to `closed_issues.md` only when the closeout passes.
- A scope decision names each new finding: introduced regression, dependency, separate existing defect, separate new defect, or unknown.
- Evidence files carry the signature of the files they checked. A file that changes makes the evidence stale.
- A failed or interrupted run stays in the record as a failure. A later run does not hide it.
- Every record that a person reads follows [the writing standard](template/devel-loop/writing_standard.md).

## Try the kit on the example

The example is a small diffusion model with an independent Fourier oracle.

```sh
K=/path/to/ESX-Team
mkdir /tmp/esx-diffusion
python3 $K/esx_install.py --project /tmp/esx-diffusion \
  --config $K/examples/periodic_diffusion/project.json --apply
cp -R $K/examples/periodic_diffusion/src /tmp/esx-diffusion/
cp -R $K/examples/periodic_diffusion/tests /tmp/esx-diffusion/
cp $K/examples/periodic_diffusion/project_profile.md /tmp/esx-diffusion/esx/
cp $K/examples/periodic_diffusion/code_map.md /tmp/esx-diffusion/docs/
cd /tmp/esx-diffusion
python3 tools/esx/loop_gate.py --doctor
python3 tools/esx/verify.py --suite scientific --owner arch
python3 tools/esx/verify.py --suite scientific --owner arch
```

The doctor reports `PASS`. The first verification reports `EXECUTED PASS`. The second verification
reports `REUSED EVIDENCE`. The example qualifies only itself. See [examples/README.md](examples/README.md) for more examples.

## Test the kit

```sh
python3 run_tests.py
```

The runner starts each test module in its own process. It makes no call to a provider and sends no message.
[VALIDATION.md](VALIDATION.md) has the last measured result and the limits of the tests.

An optional test uses the real Claude provider in a disposable project. It can cost money.

```sh
python3 tests/live_runtime.py --timeout 180
```

## Upgrade a project

Preview the upgrade. Then apply it.

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --apply
```

An upgrade that has a conflict writes nothing. See [INSTALL_UPGRADE.md](INSTALL_UPGRADE.md).

## Credit

ESX-Team grew out of the repository [three-man-team](https://github.com/russelleNVy/three-man-team) by Russell Aaron (MIT license).

The writing rules and the linter `tools/esx/ste_lint.py` come from the skill
[asd-ste100](https://github.com/danyuchn/asd-ste100-skill) by Dustin Yuchen Teng (MIT license).
ASD-STE100 is the specification of ASD, the AeroSpace and Defence Industries Association of Europe.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Where to read next

| Document | Content |
|---|---|
| [INSTALL_UPGRADE.md](INSTALL_UPGRADE.md) | Install, upgrade, adopt, and the master repository. |
| [CHANGELOG.md](CHANGELOG.md) | The changes in each version. |
| [VALIDATION.md](VALIDATION.md) | What the tests show, and what they do not show. |
| [PROVENANCE.md](PROVENANCE.md) | The source of the kit. |
| [WRITING_STANDARD.md](WRITING_STANDARD.md) | The writing rules for all prose in this repository. |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Credit and license of the work of other authors. |
| [template/devel-loop/writing_standard.md](template/devel-loop/writing_standard.md) | The writing rules that the kit installs in each project. |
| [template/docs/esx_framework_map.md](template/docs/esx_framework_map.md) | The modules, the contracts and the tests of the framework. |
| [template/devel-loop/execution.md](template/devel-loop/execution.md) | The exact commands for a role turn, a candidate and a closeout. |
| [template/devel-loop/loop_contract.md](template/devel-loop/loop_contract.md) | The loop and the steps of one iteration. |
