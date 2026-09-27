# Installing and upgrading ESX

`/Users/ifenty/ProjectsNotBox/ESX-Team` is the authoritative framework repository.
Projects receive the active workflow files from `template/`; they do not receive
the framework's installer, tests, examples or another template tree.

## Fresh installation

Preview first:

```sh
python3 /path/to/ESX-Team/esx_install.py --project /path/to/project
```

Apply the same complete plan:

```sh
python3 /path/to/ESX-Team/esx_install.py --project /path/to/project --apply
```

`--config FILE` supplies a completed `esx/project.json`. Existing `CLAUDE.md`,
`.gitignore` and `.claude/settings.json` receive their bounded ESX additions.
Other existing ESX paths are reported as collisions. Apply performs no partial
installation when the plan contains a collision.

The project receives `ESX-team-local/`:

| Path | Contents |
|---|---|
| `version` | Installed ESX version |
| `config.json` | Project root, master location, project identity and install time |
| `manifest.json` | Every installed path, ownership and measured hashes |
| `objects/` | Content-addressed baselines used by three-way upgrades |
| `deployments/` | Immutable JSON records of applied installs and upgrades |
| `backups/` | Pre-upgrade bytes for files changed by each transaction |
| `upgrade.lock` | Serializes install/upgrade publication |

This directory contains deployment metadata. It contains no runnable copy of the
ESX framework. Keep it with the project and exclude only transient lock handling
according to the project's version-control policy.

## Upgrade

Increment the master's `VERSION` whenever template bytes change. Preview and apply:

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --apply
```

The plan classifies each file as create, update, remove, preserve, adopt,
already-current, unchanged or three-way-merge. Any conflict prevents all writes.
The apply phase verifies that project and master inputs still match the plan,
backs up replaced files and atomically publishes each result. It then records the
new version, manifest and deployment receipt.

Project-owned files include scientific configuration and maps, issue/lesson
records, project status/goals, hook settings and root routing documents. Upgrades
inventory and preserve them. Framework contracts, agent definitions, skills and
tools are managed. A local edit to a managed text file is retained when it can be
merged cleanly with the new master. Review every three-way merge.

## Existing unversioned deployment

After confirming that a project already contains a valid ESX installation and
removing any bundled distribution copy, register its current files:

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --adopt-existing
python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --adopt-existing --apply
```

Adoption records current installed bytes as the baseline and creates missing
framework files. It does not replace existing files. Use it once; subsequent work
uses ordinary upgrades.

## Agent-interpretable requests

Both commands emit JSON. An interactive agent may pass a reviewed request file:

```json
{"action":"upgrade","project":"/absolute/project/path","apply":false}
```

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --request /path/to/request.json
```

Accepted keys are `action`, `project`, `apply`, plus `config` for installation or
`adopt_existing` for migration. Agents should preview, inspect `conflicts` and the
file summary, then repeat with `apply: true`. They must not edit the manifest,
objects or version to bypass a refusal. A runtime-contract change can require the
project's documented retained-session transition process after upgrade.

## Upgrading to 1.1.0

Preview the normal three-way upgrade from the single master. Complete an in-flight
legacy iteration with its original identity; new preparation emits state_version 2
and requires a successful --check-start receipt. Do not fabricate receipts for old
iterations. The latest closeout may require a retrospective before further work.

Process open/closed ledgers, generated process changelog, migration manifest,
standing rules and project assessment/original-record archives are project-owned.
Incoming blank forms initialize absent files; existing content remains unchanged.
Executable process helpers and normative contracts remain framework-owned.
