# CLAUDE.md

This repository is the ESX-Team framework kit. The master copy is `https://github.com/ifenty/ESX-Team`.

## Writing standard

Write all prose in ASD-STE100 (Simplified Technical English). Read `WRITING_STANDARD.md` before you
edit `README.md`, `INSTALL_UPGRADE.md`, `VALIDATION.md`, `PROVENANCE.md`, `CHANGELOG.md` or any
document under `template/`. Follow the same rules in a commit message and a pull request.

## Working rules

- Increase `VERSION` when a byte of `template/` changes. A change to a document outside `template/` does not need a new version.
- Put each release in `CHANGELOG.md`. Add a test in `tests/` for each behavior change.
- Run `python3 run_tests.py` before you push. The run makes no call to a provider.
- Push to the branch `esx-team-fixes`. The `main` branch is not the current release (see `INSTALL_UPGRADE.md`).
