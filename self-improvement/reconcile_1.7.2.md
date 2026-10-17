# Release 1.7.2: per-hunk reconciliation of the runoff pilot's framework edits

The pilot project (`MITgcm_new_runoff`) is installed at kit 1.6.3 and carries edits in `tools/esx/`.
A normal three-way upgrade against kit 1.7.1 conflicted in seven FRAMEWORK-owned files (18 hunks).
The kit is the master: for each hunk this file records what the pilot changed relative to the 1.6.3
baseline, what the kit changed, and the verdict that lets "resolve the project hunk to the kit side"
lose nothing the project needs.

Method (read-only on the project; work in `/tmp` copies):

```
base     = <project>/ESX-team-local/objects/<manifest files[F].baseline_sha256>
current  = <project>/F
incoming = ESX-Team/template/F
git merge-file -p -L project -L baseline -L kit current base incoming
```

Verdicts: KIT-CONTAINS (the kit already implements the pilot's behaviour), PORT (a real defect from the
pilot's `open-ESX-team-issues.md` or `esx-fix.md`, now implemented in the kit with a test that fails on
1.7.1), DROP (obsolete, superseded or harmless to lose, with evidence).

## Hunk table (against kit 1.7.1, the 18 hunks)

| # | File | Pilot change vs baseline | Kit change vs baseline | Verdict | Where |
|---|------|--------------------------|------------------------|---------|-------|
| 1 | agent_runtime.py (dispatch `start`) | passes the issue's workflow kind to `team_retrospective.require_followup(root, issue, kind)` after reading `issue-start.json` (part of the pilot's blocking/advisory process-debt feature, esx-fix.md C, which lives in the pilot's `team_retrospective.py`) | adds per-dispatch role model resolution (`resolve_model`) after the unchanged two-argument call | DROP (kit text) | The kind argument only matters for a `kind:`-scoped blocker. `--prepare` and `--check-start` (pilot-local `loop_gate.py` edits that merge cleanly and call `require_followup(..., kind)`) already enforce kind scope before any dispatch, so the dispatch-time call is redundant. With the pilot's `team_retrospective.py` kept, the two-argument call is valid (`kind=None`; scopes `all` and `issue:` still apply). No ledger entry or pilot test covers dispatch-time kind forwarding. |
| 2 | brief.py `figures_section` | lists `doc_contract.listed(found)` | adds `found['warnings']` lines (bare small figures) | PORT | Kit `brief.py` now uses `doc_contract.listed(found)` and keeps the warnings, because kit `stale_lines` gains `hits_sample` (hunk 7). Test `StaleListingTests.test_brief_reads_the_listing_through_listed`. |
| 3 | brief.py `interface_errors` loop | `COMMAND_PATTERN.findall` | `finditer`, skipping a path used as `--target`/`--doc` value | KIT-CONTAINS | Kit 1.6.7 `interface_errors`; the kit is stricter on the same false-refusal class (TEAM-BRIEF-ORIENTATION-SELFCOLLISION-001, PROPOSED in the pilot ledger). |
| 4 | brief.py constants | `PACKET_SLOT` only | `PACKET_SLOT` and `ORIENT_SLOT` | KIT-CONTAINS | Kit 1.6.7 (`ORIENT_SLOT`), a superset. |
| 5 | brief.py `citation_errors` | `target.open('rb')` inside `sum` | `with target.open('rb')` | KIT-CONTAINS | The kit closes the handle; same behaviour. |
| 6 | brief.py `build` (check) | strips `PACKET_SLOT` from the instructions | strips `PACKET_SLOT` and `ORIENT_SLOT` | KIT-CONTAINS | Superset (orientation command is paths, not orders). |
| 7 | brief.py `build` (return) | substitutes `PACKET_SLOT` | substitutes both slots | KIT-CONTAINS | Superset. |
| 8 | doc_contract.py `stale_lines` | returns `hits_sample` instead of `hits` when truncated, adds `limit`, adds `listed()` (TEAM-DOCCONTRACT-STALE-HITS-TRUNCATION-001: a figure of 199 reached permanent prose from counting `hits[:200]`; true total 335) | adds `warnings` | PORT | Kit `stale_lines` returns `figures, lines, limit, truncated, warnings` and `hits` or `hits_sample`; `listed()` added. Tests `StaleListingTests`. Existing kit callers read `hits` only on untruncated results. |
| 9 | doc_contract.py `stale` command | prints the total beside a truncated listing | prints each warning | PORT | Both messages now print (truncation first, then warnings). Test `test_cli_states_the_total_beside_a_truncated_listing`. |
| 10 | loop_gate.py `kind_contradiction` docstring | text citing `framework_test_paths` and a corrected "likely, not certain" history | shorter text with the same "informs, closeout decides" claim | KIT-CONTAINS | Code identical (kit 1.6.7 `kind_contradiction`, notice only). The `framework_test_paths` sentence is true after hunk 13. |
| 11 | loop_gate.py `prepare` comment | longer history of the notice-not-refusal decision | shorter comment | KIT-CONTAINS | Same code path (`self.notices`). |
| 12 | loop_gate.py `_next_instruction` active-iteration branch | prints `UNCAPTURED COMPLETION` from `defective_completions` | prints the pending final-verification notice | PORT | Kit `loop_gate.py` gains `record_error`, `Gate.defective_completions` and the call, placed before the verification notice. Covers TEAM-BRIEF-UNVALIDATED-INTERFACE-001 (notice), TEAM-GATE-DEFECT-NOTICE-NOT-SUPERSEDED-001 and TEAM-GATE-CONSULTATION-NOTICE-PERMANENT-001. Tests `UncapturedCompletionTests`. The pilot's separate `consultation` footer status (agent_runtime/footer_contract) merges cleanly and stays local. |
| 13 | project.py `config` | validates `framework_test_paths` (list, inside `test_paths`, not executed by a non-`structural` suite) | validates `documentation_paths` | PORT | Kit `project.py` gains the validation and the identical `selected()` clause (a clean-merged hunk, identical on both sides). esx-fix.md F1. Tests `FrameworkTestPathsTests`. README config row added. |
| 14 | ralph_stop.py (verification hold, long-run branch) | plain "launched by this session" message | same message plus `group_notice(root)` (pending scientific groups) | KIT-CONTAINS | Kit 1.7.0 message is a superset. The 1.6.4 port of the pilot's `verification_running` block sat in a different place than the pilot's copy, so the clean three-way merge would have defined five functions twice. The kit now keeps that block where the pilot has it (directly before `native_running`; code motion only). Test `RalphStopAlignmentTests`. |
| 15 | verify.py `_load` | refuses a record whose `outcome` is not `pass` or that did not run every command | adds grouped-record logic and a rerun hint | PORT | Both kept in the kit. |
| 16 | verify.py `_run` signal arm comment | explains why the `InterruptedError` arm must precede `OSError` | arm already first (kit 1.6.5) with a shorter comment | PORT (comment + logic in hunk 17) | The reordering itself is KIT-CONTAINS (1.6.5); the kit now carries the pilot's wording. |
| 17 | verify.py `_run` command loop | classifies each ending from the runner's own state (`classify`: crash signals are failures; SIGTERM/INT/HUP/KILL/QUIT interruptions; other signals and launch failures infrastructure; real timeouts `RunTimedOut`; exit 124 or 128+N is a plain failure), records `outcome`, `termination`, `reason`, `completed_commands`, `planned_commands`, `ended_at`, `failure_lines`; `RunTimedOut`/`RunInfrastructure`; "no failure-marked line was observed" wording (esx-fix.md B; TEAM-VERIFY-SIGNAL-MISCLASSIFIED-001) | `interrupted`/`timed_out` flags, raises the original signal exception | PORT with two deliberate differences | (a) A signal received by the runner is still raised as an `InterruptedError` (kit 1.6.5 and `test_release_165` rely on it): `RunInterrupted` is now both a `ValueError` and an `InterruptedError`, and the record says `outcome: interrupted` with the signal number. A `KeyboardInterrupt` is re-raised as itself. (b) The kit keeps its 1.6.5 rule that a pytest session which started and exited with a positive status without its summary line is an interruption (`interruption()`), applied after `classify` and only to exit status greater than zero; the pilot dropped it. `final_verification.py` gains `INFRASTRUCTURE` and `TIMED_OUT` statuses and the corrected wording (clean-merged in the project, identical text now in the kit). Tests `VerificationOutcomeTests`; `test_verify_rerun` updated for the new wording. |
| 18 | verify.py `execute` signal handler | puts the signal number on the exception | handler unchanged; adds a comment that handlers go in before the child starts | PORT | Kit handler records `signum`; the 1.6.5 comment is kept. |

(Rows 15 to 18 are the four verify.py hunks; rows 2 to 7 are the six brief.py hunks. Numbering is by
reading order, not by git's conflict order.)

After the ports, the merge reproduction gives 1 + 6 + 2 + 3 + 1 + 1 + 5 = 19 conflict hunks for the same seven
files (verify.py has one more: the pilot's comment on `PYTEST_SUMMARY` says the pattern is never used to
classify, which is no longer true in the kit),
and in every one the kit side is a superset of the project's behaviour. The second pass is the check that
matters: resolve each conflicting hunk to the kit side (`git merge-file --theirs`), then merge again;
all seven files merge cleanly (exit status 0).

## Semantic collisions found in hunks that merge cleanly

1. ralph_stop.py: duplicate definitions of `verification_running`, `parent_pid`, `session_process`,
   `descends_from` and `untracked_runs` (kit 1.6.4 and the pilot had inserted identical blocks at
   different places, which git merges as two insertions). Fixed in the kit by moving the block (above).
2. verify.py: the pilot replaced `interruption()` with `classify` and the kit keeps `interruption()` and its test.
   A first attempt (kit adds `classify` next to an unchanged `interruption()`) produced a corrupt function
   with no conflict marker: git applied the tail of the pilot's replacement to the kit's `interruption()`,
   leaving `classify` statements (and a `NameError` on `where`) inside it. The kit now carries `classify` at
   the pilot's location with the pilot's text (an identical change on both sides) and defines the retained
   `interruption()` elsewhere with its own wording, so nothing in it can be matched to the baseline lines.
   Checked: resolving the remaining hunks to the kit side gives exactly the kit's `verify.py`.
3. final_verification.py: the pilot's clean-merged hunks reference `verify.RunInfrastructure` and
   `verify.RunTimedOut`, which only exist in the kit after hunk 17. The kit's `final_verification.py`
   now contains the same hunks (the three-way merge then sees identical changes).
4. agent_runtime.py (hunk 1): the dispatch-time kind forwarding is dropped; see the table.

## Pilot edits that stay local (merge cleanly, not ported)

These are not defects in the kit and need no kit change; they remain as the project's local edits and
will merge cleanly while the kit leaves those lines alone: the blocking/advisory process-debt feature and
lightweight reflection (esx-fix.md C: `team_retrospective.py`, `self_improvement.py`, the matching
`loop_gate.py` lines), the closeout metadata shape checks (`loop_lifecycle.metadata_problems`), the
`consultation` footer status, `project.record_paths` and `project.acceptance_scope`
(TEAM-DOCINVENTORY-LEDGER-UNINVENTORIED-001, TEAM-ACCEPTANCE-POLICY-EDIT-STRANDS-APPROVALS-001),
`doc_contract.latest_orientation`, `latest_seal`, `stale_targets` and the navigate `--map` fix
(TEAM-LOOPGATE-CHECKSTART-CORRECTION-ROUND-001, TEAM-FOOTER-ORIENTATION-FRESHNESS-001,
TEAM-DOCCONTRACT-NAVIGATE-REUSE-MAP-001), the notification backoff and deferred notice
(TEAM-NOTIFY-OUTAGE-NO-BACKOFF-001), the provider-pause early-lift guard (TEAM-PAUSE-EARLY-LIFT-001),
the `ast.dump` digest fix (TEAM-DOCCONTRACT-AST-DUMP-DIGEST-001) and the `assess-transition` evidence
format (TEAM-TRANSITION-EVIDENCE-001). Several are real defects the kit does not yet fix; adopting them
is future kit work, tracked here so that a later change to those lines is expected to conflict.

## What was not verified

The simulated project upgrade (copy the project to `/tmp/proj_sim`, resolve to the kit side, preview, apply
and run the project's own tests) could not be run in this session: copying the project was refused by the
session's permission classifier. The per-file equivalent above (merge, resolve to kit, merge again, parse)
was run on copies of the seven files and the manifest baselines only.
