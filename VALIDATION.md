# Validation record

This record states what the tests of the kit show, and what they do not show.
It follows ASD-STE100. See [WRITING_STANDARD.md](WRITING_STANDARD.md).
Each number has a date, a machine and a command.

## Current result: version 1.8.0

| Item | Value |
|---|---|
| Date | 2026-10-18 |
| Machine | Linux 6.18 (WSL2), x86_64, 4 cores allowed |
| Python | 3.14.7 |
| Command | `python3 run_tests.py` |
| Test modules | 39 |
| Tests | 675 |
| Time | 389 seconds |
| Failed modules | none |
| Calls to a provider | none |

The runner starts each module in its own process. The tests use disposable projects and make no network call.

## What the tests cover

- Install, upgrade and adoption in disposable projects, including paths with spaces.
- A rejected plan writes nothing. An adopted installation stays unchanged until a newer master exists.
- Three-way merges, conflicts, damaged baselines and a master whose `VERSION` did not change.
- Project readiness, scientific directory layouts, and positive and negative closeouts.
- Review rules, exact correlation of agent completions, and integrity of receipts and logs.
- Drift of source and inputs, failed or empty checks, and drift of the code map or documents.
- The loop: the stop hook, finite budgets, pause, resume, cancel, abort and loop owner isolation.
- Retained sessions: footer capture, identity, permission modes, and the tool hook.
- Verification: grouped suites, resume, reuse of evidence, and classification of the outcome.
- Records: lessons, the ledger of process issues, retrospectives and communication history.
- The writing standard: the rule file, the credit, the linter, and zero hard violations in the kit documents.

The example in `examples/periodic_diffusion/` runs a diffusion model against an independent Fourier oracle.
It checks conservation and finite values. An injected wrong coefficient is caught.

## Permission modes of a role session

Measured on 2026-10-18 with the Claude command-line tool. Each mode ran once, with the start arguments of a role.
The command was a compound command with a heredoc and a redirection. A second run of `auto` used 5 routine commands.

| Mode | Command ran | Denials |
|---|---|---|
| `auto` | yes | 0 |
| `bypassPermissions` | yes | 0 |
| `acceptEdits` | no | 1 |
| `dontAsk` | no | 1 |
| `manual` | no | 1 |
| `plan` | no, read-only | 0 |

Before the fix, nine of nine role turns in the runoff project recorded denials, from 1 to 14 per turn.
The kit now passes `auto` to each role session. Test: `tests/test_release_173.py`.

## Field use

The sparse-runoff project `MITgcm_new_runoff` is the pilot project. On 2026-10-17 and 2026-10-18 it closed 3 issues
with kit versions 1.7.2 to 1.7.4: RUNOFF-037, RUNOFF-052 and RUNOFF-022. Each issue passed the project's own
short scientific suite after independent review by Richard. The pilot found these defects in the kit,
and each is now fixed:

- A role session ran in the `default` permission mode (version 1.7.3).
- The frontmatter of `/esx-loop` did not parse (version 1.7.4).
- Two tests assumed a process layout that WSL2 does not have, or did not wait for a second process.

This use shows that the loop can close real issues. It does not certify the science of the project.

## What was not run

- The live smoke test `tests/live_runtime.py` was not run for this version. It uses the real provider and costs money.
  The last record is from 2026-09-15 and 2026-09-17 on macOS, for version 1.0.0. The folder `validation/` keeps those records as history.
- No test ran on macOS, on a cluster, with MPI or with a GPU for this version.
- The optional test of an external plugin, `tests/check_installed_ralph.py`, was not run.

## Limits

The tests show that the workflow tools work on the measured machine. They do not show that a project is right.
Each project must run its own scientific acceptance. The tests do not predict the speed of feature work.
Use the timing of real loops to measure that.

## Reproduce

```sh
python3 run_tests.py
python3 tests/live_runtime.py --timeout 180
```

The first command makes no call to a provider. The second command uses the provider and can cost money.
