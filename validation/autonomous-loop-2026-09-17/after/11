# ESX framework map

Use this map for workflow code and docs/code_map.md for the project's science.
Read the named owner, its caller and the nearest regression before changing a
mechanism. Python symbols can be inspected with tools/esx/orient.py without
importing scientific code. Paths below are relative to the project root.

| Mechanism | Owning source | Contract | Kit regression |
|---|---|---|---|
| Configuration, paths, signatures | tools/esx/project.py | esx/project.json | test_framework.py |
| Scope, reviews, failure recovery | tools/esx/workflow_policy.py | .claude/ESX-team/ARCHITECT.md | test_execution.py |
| Iteration preparation and closeout | tools/esx/loop_gate.py | devel-loop/loop_contract.md | test_framework.py, test_execution.py |
| Runtime sessions, resumes, peer delivery | tools/esx/agent_runtime.py | devel-loop/execution.md | test_runtime.py, live_runtime.py |
| Native role completion capture | tools/esx/hooks.py | devel-loop/issue_json_schema.md | test_runtime.py |
| Finite loop state and Stop decisions | tools/esx/loop_control.py, tools/esx/ralph_stop.py | devel-loop/loop_contract.md | test_ralph.py |
| Hook ownership | tools/esx/check_ralph_hook.py | devel-loop/loop_contract.md | test_ralph.py |
| Scientific/focused runs, logs, cache | tools/esx/verify.py | devel-loop/verification.md | test_framework.py, test_execution.py |
| Reviewed final candidate and run ownership | tools/esx/final_verification.py | devel-loop/verification.md | test_execution.py |
| Baseline, navigation and documentation | tools/esx/doc_contract.py, tools/esx/doc_inventory.py | devel-loop/documentation_contract.md | test_evidence.py |
| Exact candidate bytes, comparison, extraction | tools/esx/issue_candidates.py | devel-loop/execution.md | test_evidence.py |
| Closeout imports, continuation, diagnosis, timings | tools/esx/workflow_records.py | devel-loop/execution.md | test_evidence.py, test_execution.py |
| Issue/lesson history and links | tools/esx/records.py, tools/esx/audit.py | devel-loop/issue_json_schema.md | test_framework.py |

Regression names identify files under tests/ in the distribution kit. Each test
creates a disposable configured project. The receiving project supplies its own
scientific acceptance suite and test routes. Keep this map accurate when an owning
module, contract or regression route changes. Read-only analysis cannot establish
that an unexecuted scientific oracle passes.

## Review packet and runtime recovery

| Mechanism | Owning source | Contract | Kit regression |
|---|---|---|---|
| Staged review packets and read-only readiness | tools/esx/workflow_handoff.py | devel-loop/recovery.md | test_workflow_recovery.py, test_execution.py |
| Assessed session transitions and hook diagnostics | tools/esx/runtime_recovery.py | devel-loop/recovery.md | test_runtime.py, test_workflow_recovery.py |
| Real retained-session instruction refresh | tools/esx/agent_runtime.py | devel-loop/recovery.md | live_runtime_transition.py (opt-in) |

A running retained assignment prevents packet readiness and final verification.
The final wrapper can bind current acceptance to unchanged measured scientific
execution; receipts retain the original execution evidence.

## Autonomous operation and communication

| Mechanism | Owning source | Contract | Kit regression |
|---|---|---|---|
| Project slash command and start/continue | .claude/commands/esx-loop.md, tools/esx/loop_control.py | devel-loop/loop_contract.md | test_autonomous_loop.py |
| Routine decision authority | .claude/ESX-team/ARCHITECT.md | Autonomous loop authority section | test_autonomous_loop.py |
| Required event collection and delivery receipts | tools/esx/notifications.py | devel-loop/communication.md | test_autonomous_loop.py |

The notification utility records events and actual provider responses. Arch sends
through the authorized provider tool. Pending events route back to delivery;
recorded provider failures remain visible while scientific work proceeds.
