# Bounded operation and measured effort

Use small, evidence-led assignments. A text diff of three lines can change science;
classification still follows effect and risk. Use `--budget-kind scientific_small`
with `--kind scientific_change` for a bounded scientific task. This changes its
resource allocation without removing Bob, Richard or scientific acceptance.

## Shared allocations

| Allocation | Minutes | USD | Tool calls | Correction rounds | USD per turn |
|---|---:|---:|---:|---:|---:|
| scientific_small | 30 | 15 | 120 | 1 | 5 |
| scientific_change | 120 | 60 | 500 | 2 | 12 |
| harness_change | 45 | 20 | 180 | 1 | 5 |
| documentation | 30 | 15 | 120 | 1 | 5 |
| investigation | 45 | 20 | 180 | 2 | 5 |

These are ceilings, not spending authorization. Existing owner limits take priority.
For a metered autonomous run, arm the ESX loop and launch one coordinator:

```sh
python3 tools/esx/loop_control.py run
python3 tools/esx/team_driver.py --host claude --usd 30 --minutes 120 --calls 500 --turn-usd 5
```

Use the project's Python environment. Allocations are **nominal expectations, not
caps**: nothing in `team_budget` refuses a launch, a tool call or a correction
round. The loop's own `max_iterations` is the single enforced terminal bound.
The driver owns one retained coordinator session and a shared run ledger. Retained
children, resumes and corrections record against the same run and issue scopes.
Restart uses the original identifiers and deadlines, because a moving baseline
makes measurement meaningless. Never start this driver inside another active
coordinator or run overlapping owners. Interactive `/esx-loop` remains available;
it cannot meter the host session's external bill, and its accounting reports
missing coordinator coverage. Native subagents likewise report unknown costs; use
the retained CLI path when spending must be measured. The Claude adapter is ESX's
supported path. Any alternate host requires separate hook qualification.

Each launch reserves its expected cost before calling the provider, so the
difference from actual usage can be measured. No provider spend cap is passed, so a
turn is never truncated mid-work over a pricing estimate. Known usage settles the
reservation; interrupted or missing usage retains it so a retry cannot
double-count. Every exceeded expectation is recorded under the scope's
`overruns` with its expected value, observed magnitude and first/last observation
time. Effort and elapsed time are separate dimensions and must not be conflated:
`minutes` measures **summed dispatch duration** for the issue, while
`calendar_minutes` measures elapsed time since the scope first dispatched and
therefore includes work done on other issues. An issue carried across iterations
can show a large calendar span with modest effort -- one measured 437 calendar
minutes against 92 minutes of actual dispatch -- so only `minutes` says anything
about how much work an issue took.
Repeated crossings of one dimension update that record rather than growing it, so
monitoring cannot itself become a cost. Retrospectives report these overruns; that
is how a wrong expectation gets corrected.

The hard process timeout still ends a hung turn: that is a liveness guard, not a
cost cap. `agent_runtime.py start/followup` accepts `--timeout`, `--tool-timeout`
(600 seconds by default) and `--max-tool-calls` (60). A timed-out turn records
`source_changed_during_turn`, so recovery reads whether durable work landed instead
of guessing from a bare `failed` status -- resume such a turn with `followup`
rather than restarting it. Bash tools run in separate process groups so one hung
command cannot kill another healthy assignment. Permission checks remain enabled.

To correct an expectation that measurement has shown to be wrong, use
`team_budget.py inspect --issue UUID`, then `team_budget.py extend --authorization
path#sha256` to preview an actual Owner instruction. This unblocks nothing -- there
is nothing to unblock -- it realigns the baseline so later monitoring compares
against something realistic instead of reporting a permanent overrun. The JSON
includes issue, authorized_by=Owner, authorization_id, evidence, reason,
expected_scope_sha256, positive add_minutes and optional nonnegative
add_usd/add_calls/add_corrections. Add `--apply` only with existing authorization.
The same request is idempotent and retains prior spend, unknown charges and calls.

## Short handoffs and evidence reuse

Generate briefs from a design file rather than reconstructing the footer:

```sh
python3 tools/esx/brief.py --role bob --issue UUID --design design.md --output bob-brief.md
python3 tools/esx/verify.py --suite structural --owner arch
python3 tools/esx/brief.py --role richard --issue UUID --design design.md --question 'Check the independent conservation oracle.' --packet review-packet.json --output richard-brief.md
```

A brief gives the actual iteration identity, budget, own-orientation command,
acceptance question and role report template. Run the complete structural suite
before review; current evidence is reused. A retained completion validates nested
orientation and review evidence early, writes `handoff.json`, and saves failed or
partial status honestly. Corrections resume the same identity and carry their
new correction_round. Existing packet helpers retain the exact completion IDs.

Use `loop_lifecycle.py prepare-done --packet ... --verification ... --metadata ...`
for a draft completion from the accepted packet and final_verification result.
Metadata supplies a substantive summary, tests_status, Git and communication
dispositions. This does not accept the issue. Preview/apply `loop_lifecycle.py
promote`, then `loop_gate.py --check-done`. The timestamp stays equal to the start;
closed_at records completion time separately. A successful content-bound start
receipt is required. Preserve partial/blocked work and its next action.

## Accounting and qualification

```sh
python3 tools/esx/team_accounting.py --concise
python3 tools/esx/team_accounting.py --issue UUID --output accounting.json
python3 tools/esx/loop_gate.py --timings
```

Reports reconcile Arch and child provider receipts, repair components, tokens,
corrections, missing costs and timed phases. Overlapping intervals use unions;
summed agent effort is distinguished from elapsed time. Orientation, implementation,
review, verification, closeout, retrospective and coordination are instrumented.
Other waiting can be measured through `team_accounting.phase(..., 'waiting', reason)`.
Unobserved time, native turn duration and host usage remain coverage gaps; reported
USD is not an invoice reconciliation. Do not describe missing values as zero.

After each accepted iteration complete [the measured retrospective](self-improvement/README.md).
Offline protocol/stress tests prove local behavior. A real provider probe establishes
availability; a representative bounded live run is needed to claim actual savings
or production reliability. Scientific qualification remains project-specific.
