# Install and upgrade ESX-Team

This guide shows how to install the kit in a project, upgrade it, and adopt an older installation.
It follows ASD-STE100. See [WRITING_STANDARD.md](WRITING_STANDARD.md).

## The master repository

The master repository is `https://github.com/ifenty/ESX-Team`. It is the only source of the kit.
A project receives files from the folder `template/` of the master. A project does not receive the installer,
the tests, the examples or a second copy of the template.

Get the master before you install or upgrade. Update it each time you upgrade:

```sh
git clone https://github.com/ifenty/ESX-Team.git
git -C ESX-Team pull
```

The file `VERSION` in the master has the version of the kit.

The installer and the upgrader read the master from the folder where they run. They record no location of the master in the project.

## Requirements

- Python 3.10 or later.
- Git. The upgrader uses `git merge-file` for a three-way merge.
- A writable project folder. The installer refuses a symbolic link at an ESX path.

## Install the kit in a new project

1. Preview the installation. The preview writes nothing.

   ```sh
   python3 /path/to/ESX-Team/esx_install.py --project /path/to/project
   ```

2. Read the plan. It lists each file with an action.
3. Apply the same plan.

   ```sh
   python3 /path/to/ESX-Team/esx_install.py --project /path/to/project --apply
   ```

Use `--config FILE` to give a completed `esx/project.json` in the same step.

The installer makes no commit, sends no message and changes no permission.
If the plan has a collision, the installer writes no file.

### What happens to files that already exist

| File | Result |
|---|---|
| `CLAUDE.md` | The installer adds an ESX routing block. It keeps the other lines. |
| `.gitignore` | The installer adds the missing ignore lines. |
| `.claude/settings.json` | The installer adds the ESX hooks. It keeps the other settings and an external plugin hook. |
| Any other file at an ESX path | This is a collision. The plan stops. |

To resolve a collision, install into an empty folder. Then merge the files by hand.
The installer never replaces existing issue or lesson history.

### The folder ESX-team-local

The installer creates `ESX-team-local/` in the project.

| Path | Content |
|---|---|
| `version` | The installed version of the kit. |
| `config.json` | The project identity and the time of the installation. |
| `manifest.json` | Each installed path, its owner and its hashes. |
| `objects/` | The baselines for three-way merges. Each file name is a hash. |
| `deployments/` | One record for each install or upgrade. |
| `backups/` | The files that an upgrade replaced, as they were before. |
| `upgrade.lock` | A lock. It stops 2 upgrades from running at the same time. |

This folder has metadata only. It has no copy of the framework.
Commit the folder with the project. Another computer needs the `objects/` files to do the next upgrade.

## Who owns each file

The manifest marks each file as `framework` or `project`.

| Owner | Files | Upgrade behavior |
|---|---|---|
| `framework` | Contracts, agent definitions, skills, commands, templates and tools. | The upgrade updates the file. |
| `project` | `CLAUDE.md`, `.gitignore`, `.claude/settings.json`, `esx/project.json`, `esx/project_profile.md`, `docs/code_map.md`, `docs/model_contract.md`, `docs/doc_format_guide.md`. Also the record files for issues, lessons and goals, `devel-loop/loop_rules.md`, and the files for the process issues of the project. | The upgrade never changes the file. It adds new ESX hooks to `.claude/settings.json`. |

A rule that must reach existing projects goes in a `framework` file. A change to a `project` file reaches new installations only.

## Upgrade a project

The master changes `VERSION` when a byte of `template/` changes. Do this check before you upgrade:

```sh
git -C /path/to/ESX-Team pull
cat /path/to/ESX-Team/VERSION
cat /path/to/project/ESX-team-local/version
```

1. Preview the upgrade. The preview writes nothing.

   ```sh
   python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project
   ```

2. Read the result. The keys that matter are `from_version`, `to_version`, `conflicts` and `summary`.
   `conflicts` must be empty.
3. Apply the same plan.

   ```sh
   python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --apply
   ```

The upgrade checks that the project and the master did not change since the preview.
It saves the replaced files in `backups/`. It publishes each file in one atomic step.
It then writes the new version, the manifest and a deployment record.

### The action of each file

| Action | Meaning |
|---|---|
| `create` | The file is new in the master. The upgrade writes it. |
| `update` | The project file equals the old baseline. The upgrade writes the new file. |
| `three-way-merge` | The project changed the file. The upgrade merges the change with the new master file. |
| `already-current` | The project file already equals the new master file. |
| `unchanged` | Nothing changed. |
| `preserve` | A project-owned file. The upgrade does not touch it. |
| `add-esx-hooks` | The upgrade adds new ESX hooks to `.claude/settings.json`. |
| `remove`, `adopt` | The master removed the file, or the upgrade registers an existing file. |

### What stops an upgrade

An upgrade writes nothing when it finds any of these problems:

- A merge conflict in a framework file.
- A baseline that is missing or damaged.
- A master version that is lower than the installed version.
- A master whose template changed and whose `VERSION` did not.
- A framework file that the project removed, or that the master removed after a local edit.

Do not edit the manifest, the objects or the version to remove a refusal.
Resolve the cause. A conflict means that the project and the master changed the same lines.
Compare the two files and move your change into the master, or drop it.

### After the upgrade

1. Preview again. The result must show the same version in `from_version` and `to_version`, and an empty `conflicts` list.
2. Run `python3 tools/esx/loop_gate.py --doctor` in the project. The result must be `PASS`.
3. Run the framework tests of the project, if it has them.
4. Review every file that had the action `three-way-merge`. Use `git diff`.
5. Commit the changed files and the new files in `ESX-team-local/`.
6. Take new evidence. The evidence fingerprint includes the hash of each file in `tools/esx/`.
   Old verification evidence becomes stale after an upgrade that changes a tool.

Some upgrades change the contract of a role session. Then follow the retained-session transition
process in `devel-loop/recovery.md` before you resume a session.

## Adopt an installation that has no version

Use this once for a project that has an ESX installation but no `ESX-team-local/`.

1. Check that the installation is valid.
2. Remove any copy of the distribution that the project holds.
3. Preview the adoption.

   ```sh
   python3 /path/to/ESX-Team/esx_upgrade.py --project /path/to/project --adopt-existing
   ```

4. Apply the same plan with `--apply`.

Adoption records the installed bytes as the baseline. It creates the framework files that are missing.
It does not replace an existing file. After the adoption, use the normal upgrade.

## Requests for an agent

Both commands print JSON. An agent can also read a request file:

```json
{"action":"upgrade","project":"/absolute/project/path","apply":false}
```

```sh
python3 /path/to/ESX-Team/esx_upgrade.py --request /path/to/request.json
```

The accepted keys are `action`, `project` and `apply`. An install request also accepts `config`.
An adoption request accepts `adopt_existing`.

An agent must preview first. It must read `conflicts` and `summary`. Then it sends the same request with `"apply": true`.

## Version notes

[CHANGELOG.md](CHANGELOG.md) lists the changes in each version.
Read the entries between the installed version and the new version before you upgrade.
