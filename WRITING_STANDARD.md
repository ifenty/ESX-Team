# Writing standard

All prose in this repository follows ASD-STE100 (Simplified Technical English).
This rule applies to every new edit and to every rewrite.
Future edits must follow the same standard.

## The rules

The rules are in [template/devel-loop/writing_standard.md](template/devel-loop/writing_standard.md).
That file is the only copy. The kit installs it in each project, so the kit and the projects use the same rules.
Read it before you edit a document.

## Credit

The structural rules, the word rules, the scan checklist and the linter come from the skill
[asd-ste100](https://github.com/danyuchn/asd-ste100-skill) by Dustin Yuchen Teng (MIT license).
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the license text.

## What this repository covers

The rule covers these files:

- `README.md`, `INSTALL_UPGRADE.md`, `VALIDATION.md`, `PROVENANCE.md` and `WRITING_STANDARD.md`.
- Every entry in `CHANGELOG.md` for version 1.8.0 and later.
- Every document under `template/`.
- Commit messages and the text of a pull request.

The rule does not cover these items:

- The code, the comments in the code and the output of the tools.
- The `CHANGELOG.md` entries for version 1.7.4 and earlier. These entries are history and keep their original text.
- The text in `self-improvement/` and `validation/` that records past work.

## Check a document

Run the linter before you commit a document:

```sh
python3 template/tools/esx/ste_lint.py README.md INSTALL_UPGRADE.md VALIDATION.md PROVENANCE.md
```

A hard violation makes the exit code 1. A passive verb is advice only.
The test `tests/test_release_180.py` runs the linter on the main documents of this repository.
The linter checks the form of the text. Read the text again to check the meaning.

## Limit of the check

The official dictionary of ASD-STE100 is not in this repository, and ASD does not allow general copying of it.
The check therefore tests the structural rules only. The result is not a formal STE validation.
