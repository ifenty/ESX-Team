# ESX work loop

ESX provides a project-owned Ralph-style continuation loop. Its Stop hook owns
`.claude/esx-loop.local.md`; an installed Ralph plugin has a separate state file.
The launcher refuses overlapping active loop states. No global plugin changes
are needed. Each loop has a finite iteration budget and explicit termination evidence.

## Activate the deployment

Complete esx/project.json, esx/project_profile.md and docs/code_map.md, add the
actual source and tests, and run `python3 tools/esx/loop_gate.py --doctor`.
Follow [runtime qualification](execution.md#qualify-the-runtime) before agent work.
In the main Claude session run:

```text
/esx-loop
/esx-loop --max-iterations 30
/esx-loop status
/esx-loop cancel
```

The project command calls `tools/esx/loop_control.py run`, then immediately drives
`--next` under [Arch's autonomous authority](../.claude/ESX-team/ARCHITECT.md#autonomous-loop-authority).
It uses the environment in the project profile. A fresh loop defaults to 30
iterations. Reinvocation continues an active loop with its existing budget and
assignments. The default continuation text is [autonomous_prompt.md](autonomous_prompt.md).
The command never starts the external Ralph plugin or another Claude session.

For shell operation use `python3 tools/esx/loop_control.py run`, `status` or
`cancel`. Shell activation arms the Stop hook; Claude must then execute `--next`.
The lower-level `start --prompt-file PATH --max-iterations N` remains available
for an explicitly customized prompt. All commands use the project's interpreter.

Read [communication.md](communication.md). Required notifications are queued from
loop state and validated records. `--next` directs Arch to drain unattempted
events before proceeding; a concrete delivery failure permits continued work.
Run `notifications.py pending` after preparation, record edits and validation.
Before no-work completion, the gate queues a final summary and waits for its
attempt. At the budget limit the Stop hook allows one notification-only finalization
turn, then terminates. This extra turn cannot run issue work or extend the work
budget; its saved marker bounds it even when the provider fails. Cancellation queues its reason. Hook-enforced
termination also retains a terminal event for later delivery if Claude cannot
send it before stopping. Pending events survive cancellation and restart.

The gate emits the completion token only with active ESX state and no actionable
issues. Blocked issues can remain. The Stop handler searches assistant text from
the current user turn for the exact tagged promise. Tool results, thinking blocks
and promises from earlier turns cannot fulfill it. Transcript errors preserve
bounded continuation; invalid state suspends visibly with the original bytes
archived. Iteration limits and cancellation retain termination reasons. State
writes and cancellation use a shared lock. Retained role sessions cannot advance
the parent loop. See `.claude/esx-loop-exit.log` and `.claude/esx-loop*` archives
when diagnosing termination. Never edit a counter to conceal failed progress.

## One iteration

1. Run --next; read the selected issue, priority, applicable lessons and map.
2. Run --prepare before issue edits. Preserve the first issue baseline across
   corrections and partial iterations. Deliver queued start communication, record its result, then --check-start.
3. Dispatch the required roles using [retained sessions](execution.md). Use focused
   checks, import actual completion records and communicate findings immediately.
4. Maintain source/docs/map, seal the documentation plan, and capture the candidate.
   Obtain current independent review. Resolve findings or disposition separate scope.
5. Assemble a review packet with exact completion events. For a scientific change,
   the assigned owner uses final_verification.py after readiness passes. Preserve
   its result and receipt. A failed attempt cannot reuse an earlier approval result.
6. Move an accepted issue into closed_issues.md, or retain partial/blocked work with
   its next step and dependency. Complete issue-done.json using the start timestamp.
7. Run --check-done. PASS saves the complete closeout in durable history.
8. Drain required authorized notifications, retaining provider receipts or concrete
   errors in the outbox. If issue-done communication fields change, rerun --check-done
   to refresh the matching history entry atomically.
9. Continue through --next. An interruption resumes existing assignments and
   evidence. After two unsuccessful correction rounds, complete the required
   diagnosis checkpoint before another dependent iteration.

```sh
python3 tools/esx/loop_gate.py --prepare PROJECT-001 --kind scientific_change \
  --priority 'The boundary defect invalidates the next required experiment.' \
  --map docs/code_map.md#pipeline \
  --target 'src/model.py::step' --target 'tests/test_model.py::<module>' \
  --doc docs/model_contract.md \
  --use 'Trace boundary updates into their independent conservation oracle.'
```

Replace example paths with actual project anchors. Preparation prints bounded
source excerpts on stderr and the start record on stdout. Add --risk for each
applicable review criterion. Preparation refuses to overwrite an active iteration;
validated partial closeout permits the next iteration while retaining the original
baseline and initial signatures. A diagnosis supplied as a JSON object argument to --diagnosis must
contain an executed reproduction, hashed evidence and the next bounded decision.

The gate checks scope, identities, current reviews, verification provenance,
documentation coverage, map freshness, issue/lesson records and Git/communication
dispositions. Arch and Richard retain responsibility for scientific adequacy,
authorization and semantic risk. Structural validation does not establish these judgments.
