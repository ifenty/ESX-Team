# ESX validation record

## Current master — version 1.0.0

Measured 2026-09-17 on the versioned single-master installer and upgrader:

| Check | Result |
|---|---|
| Complete portable suite | **212 tests PASS**, eight modules |
| Install/upgrade transaction tests | 10 tests PASS |
| Fresh install and `ESX-team-local` records | PASS |
| Project-owned file preservation | PASS |
| Clean three-way framework merge | PASS |
| Overlap, corrupt baseline and unversioned-master refusal | PASS |
| Agent JSON request and optimistic concurrency refusal | PASS |

The suite makes no network calls. Upgrade tests use disposable projects and a
disposable master, verify that a rejected plan writes nothing, and confirm that
an adopted customized installation remains unchanged until a newer master version
can be reconciled. Receiving projects still require their configured structural
and scientific acceptance suites after an upgrade.

## Initial framework qualification

Measured 2026-09-15T23:23:31.776612+00:00 on macOS-26.7-x86_64-i386-64bit, Python 3.10.12.

| Check | Result |
|---|---|
| Portable regression suite | **170 tests PASS**, five modules, 55.04 seconds |
| Exact candidate, baseline, docs and closeout evidence | 57 tests PASS |
| Final verification, failed turns and partial-iteration continuation | 17 tests PASS |
| Deployment, project configuration and complete scientific closeout | 34 tests PASS |
| Stop handler, finite budgets, cancellation and loop isolation | 30 tests PASS |
| Retained runtime, footer capture and explicit identity context | 32 tests PASS |
| Actual Claude provider and peer transport smoke | **Seven checks PASS** |
| Separate configured diffusion deployment | Doctor PASS; scientific EXECUTED PASS, then REUSED EVIDENCE |

## Exercised behavior

The suite deploys independent disposable projects, including paths containing
spaces. Scientific tests execute a periodic finite-difference diffusion model
against an independent discrete Fourier oracle and conservation checks. An
injected nonconservative coefficient is detected. Configuration uses declared
source/test roots, input bytes, environment and toolchain probes.

Negative cases exercise missing or modified evidence, source/input drift,
changed reviewer results, incomplete role calls, duplicated identities, failed
fresh runs, timeout cleanup of descendant processes, unsupported workflow
amendments, omitted source files, documentation drift and invalid loop state.
Partial iterations preserve original baselines and exact earlier completions;
final scientific approval requires current iteration evidence. Final verification
starts only after candidate/review/documentation readiness and has one run owner.

The live smoke uses the installed Claude CLI in a disposable configured project.
It verifies two-turn remembered context, actual role tools and file edits, a
retained Bob correction, Bob's direct message to the same Richard, and Richard's
recorded response. The public test marker survives correction. Scratch-only
permissions authorize those bounded tools. The deployment template preserves
receiving-project permission policy. Provider failures remain failed evidence.

Two setup attempts also exercised failure handling: a role refused an inconsistent
smoke brief, and a reviewer exceeded the timeout while discovering assignment
context. The delivered smoke creates a real harness issue and explicit navigation
commands. The runtime supplies measured identity and baseline directly. The
reported live PASS is from the final delivered runtime configuration.

## Reproduce

```sh
python3 ESX-Team/run_tests.py
python3 ESX-Team/tests/live_runtime.py --timeout 180
```

The first command makes no provider calls. The second uses the configured Claude
provider and preserves artifacts under its printed scratch path. It may incur
normal provider usage charges. The complete offline log is
[validation/offline-tests.log](validation/offline-tests.log). The portable
[qualification record](validation/qualification.json) contains counts, actual
runtime event identities, timing and SHA-256 hashes of tested source/fixture files.
[README.md](README.md) supplies deployment and standalone science commands.

## Qualification boundary

These checks establish the portable workflow mechanisms on the measured macOS
runtime and the small diffusion example. They do not establish scientific
correctness for a receiving project or predict feature-development throughput.
Use actual loop timing and issue outcomes to measure operational improvement.

Each deployment needs its own tools, models, permissions, external inputs and
scientific acceptance. Linux/POSIX is supported by the implementation; Linux,
MPI/GPU, remote scheduler and full-data qualification were not exercised here.
The optional external-plugin compatibility script is separate from the tested
project-owned ESX loop. No external notifications or commits were made by these
qualification tests.
