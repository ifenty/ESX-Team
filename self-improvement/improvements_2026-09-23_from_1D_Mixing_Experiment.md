# ESX-Team improvements sourced from 1D_Mixing_Experiments (2026-09-23)

**Source**: a diagnostic report on ESX-Team performance over the last 10 loop
iterations in the `1D_Mixing_Model` project (`/Users/ifenty/ProjectsNotBox/1D_Mixing_Experiments/1D_Mixing_Model`),
covering issues 1DMIX-024/026/027/028/030/031/032/033/035, spanning ~27 hours
of wall-clock and 49 agent dispatches ($122.15, 337.7 minutes). That report
identified 7 problems. This document determines which are properties of the
**ESX-Team framework itself** (and therefore fixable once, here, for every
project that uses it) versus properties specific to that one project's own
domain (MITgcm/Fortran capture instrumentation, Docker builds), and specifies
the exact fix for each generalizable one.

Evidence for every claim below was re-derived directly against this
framework's own `template/tools/esx/*.py` source and `tests/test_framework.py`
fixtures — not merely restated from the source project's report.

## Summary table

| # | Problem | Generalizable? | Disposition |
|---|---|---|---|
| 1 | Discarded review identities (bookkeeping gap) | **Yes** | Fixed here (defaults + docs) |
| 2 | Scientific-signature-drift gate forces full reclassification | **Yes** | Documented here (no gate-logic change — see rationale) |
| 3 | Footer-convention ambiguity (`candidate_signature`, `documentation_review.status`, `independent_check.evidence`) | **Yes** | Fixed here (new CLI, new guide, clearer errors) |
| 4 | Stale/duplicated Fortran instrumentation across experiment directories | **Yes, once reframed** | Fixed here (generic `mirrored_paths` config + audit check) — added 2026-09-23, second pass, at owner's explicit request |
| 5 | Regression invisible because pytest masks a script's own `sys.path` bug | Partially — the *pattern* generalizes, the instance doesn't | Noted as guidance only (see below) |
| 6 | Disk-space near-miss from unbounded Docker/capture accumulation | **No** | Project-specific (MITgcm/Docker domain) |
| 7 | No self-assessment step; `lessons_learned.md` mechanism exists but unused | **Yes** | Fixed here (loop nudge + contract doc) |

---

## Problem 1 — Discarded review identities cost 22% of all dispatches

**Evidence from the source project**: across 9 issues / 49 dispatches, 11
dispatches (22%, $24.40, 50.1 minutes) were full redos of a role under a
**different agent identity** at `correction_round=0` — not corrections, full
discards. Confirmed pattern: 1DMIX-030 had 5 distinct Richard identities and
2 distinct Bob identities all at round 0; 1DMIX-032 had 4 distinct Richard
identities and 2 distinct Bob identities.

**Root cause, confirmed against this framework's own source**: a completed,
substantively-correct review is only "reusable" across a re-`--prepare` of
the same issue if `workflow_policy.py::known_completion_iteration()` finds it
referenced in a **prior loop_history.jsonl row's `subagents` field**
(`loop_gate.py:52`'s `require(hist and (hist[-1]['id'], hist[-1]['timestamp']) == ...)`
already forces every iteration boundary through a manually-built history
entry). The mechanism to build that entry (`workflow_records.py prepare_done`)
requires an explicit `--select` file naming the exact `dispatch_event_id`s to
carry forward. **A command that auto-generates that exact `--select` payload
already exists** — `workflow_records.py selections --start issue-start.json`
(`workflow_handoff.py:214-238`) lists every dispatch for the active issue,
tagged `selection_scope: 'history'` vs `'current'`. It was never used, even
once, across the entire 27-hour session — its existence was not discoverable
from any doc the acting agent actually read.

A second, independent contributor: `prepare_done()`'s draft output leaves
`scope_decisions`, `milestone`, `lessons`, `rules_updated`, `rules_updated_na`,
`git` and `communication` either absent or `null`
(`workflow_records.py::prepare_done`, the `'preparation': {'pending': [...]}`
block). None of these are populated with a schema-valid default, so building
*any* draft — even a trivial "partial, nothing to report" checkpoint —
requires reverse-engineering `workflow_policy.py::validate_scope_decisions`,
`check_milestone`, and `check_done`'s git/communication `require()` calls one
`ValueError` at a time. This made the "just record a partial checkpoint and
move on" path — the documented, correct way to preserve dispatch reusability —
more expensive than skipping it, which is exactly what happened.

### Fix implemented here

1. **`tools/esx/workflow_records.py::prepare_done()`** now seeds
   `scope_decisions=[]`, `milestone={"logged": False, "reason": "No milestone applicable."}`,
   `lessons=[]`, `rules_updated=[]`, `rules_updated_na="No rule changes needed this iteration."`,
   `git={"committed": False, "reason": "Not committed; pending explicit owner authorization."}`,
   `communication={"status": "pending", "detail": "Arch will record authorized delivery or its disposition."}`
   as *valid, ready-to-use* defaults rather than absent/`null` fields. Callers
   that have a real decision for any of these fields still overwrite them; the
   defaults only remove the "guess the schema" tax for the common case where
   the true answer already matches the default (e.g. "no commit yet",
   "no milestone this round"). `'preparation'`'s `pending` list narrows
   accordingly, so the caller can still see which fields still need a
   *substantive* decision (`outcome`, `summary`, `tests_status`,
   `verification`) versus which are already filled with a safe default.
2. **`devel-loop/recovery.md`/`devel-loop/execution.md`** now open the
   "build a review/closeout packet" recipe with an explicit, unmissable
   step: *"First, run `workflow_records.py selections --start <issue-start.json>`
   to list every dispatch already recorded for this issue — build your
   `--select` file from this output, not from a manual `dispatch_log.jsonl`
   search."*

**Expected outcome**: the mechanical, `event_id`-hunting cause of discarded
identities should approach zero — `selections` cannot omit a real completed
dispatch the way a manual grep can. The remaining friction (choosing *which*
of several candidate identities is current) becomes a judgment call, not a
data-loss risk. Re-measuring this same dispatch-log statistic after the next
10-iteration window in any project should show near-zero "N distinct
identities at round 0 for one role" cases.

---

## Problem 2 — The scientific-signature-drift gate forces full review cycles for zero-code-change closures

**Evidence**: `loop_gate.py::check_done()` (`loop_gate.py:132-133`):
```python
if source_signature(self.root, scientific=True) != policy['numerical_signature_at_start']:
    require(policy['kind'] == 'scientific_change', 'scientific source/tests/configuration changed: amend workflow kind')
```
`numerical_signature_at_start` is frozen at an issue's **first** `--prepare`
call (`loop_gate.py:67`, inherited across every subsequent re-prepare) and
never refreshed. Any *other*, unrelated `scientific_change` closure that
touches `source_paths`/`test_paths`/`configuration_paths` — which is most
closures — drifts the live signature away from that frozen value. The gate
then requires a full `kind=scientific_change` reclassification (mandatory
Bob+Richard redispatch, `workflow_policy.py:60-61`) before the issue can
close, **even when the issue's own reviewed candidate is provably
unchanged**. This hit at least 3 of the 9 issues in the source project's
window (1DMIX-027, 1DMIX-028, 1DMIX-031), including one iteration whose
entire closeout attempt (a sealed 85-target documentation report, a
structural verification run) had to be discarded and redone — recorded in
that project's `loop_history.jsonl` as an iteration with `iteration: null,
start_timestamp: null`, itself a symptom of the discard.

**Why this is not fixed with a code change here**: the gate exists to catch
*real* scientific drift a reviewer hasn't seen. A per-file "is this drift
attributable to files this issue's own candidate touched" exemption is
possible in principle (the candidate's own default inventory scope — `source
+ test + configuration_paths + FRAMEWORK_PATHS`, confirmed at
`project.py:19,98,110` — is a strict superset of the scientific inventory's
scope, so "candidate signature unchanged since capture" *would* imply "no
scientific file this issue touched has changed"). But correctly bounding the
*time window* that check should span (candidate-capture time vs. the
original `--prepare` time; multiple candidate re-captures across correction
rounds) requires reasoning this framework cannot fully validate from a single
source project's experience without risking a real weakening of the
scientific-integrity guarantee for every other project relying on it. That
tradeoff is deliberately left as a documentation fix, not a logic change,
until it can be validated against more than one project's real usage pattern.

### Fix implemented here

**`devel-loop/loop_contract.md`** gains a new, explicit subsection describing
this exact failure mode by name ("scientific-signature-drift"), stating:
- What triggers it (any other `scientific_change` closure since this issue's
  first `--prepare`).
- The safe, already-proven recovery: a **confirmation-only** Bob+Richard
  redispatch — both agents re-verify from scratch that (a) the issue's own
  candidate is unchanged, (b) its acceptance criterion is otherwise already
  satisfied, and (c) no new source change is needed; this is a real review,
  not rubber-stamping, but it is bounded and fast when there is genuinely
  nothing new to check.
- The proactive mitigation: when starting *any* issue expected to stay open
  across other issues' closures, default to `kind=scientific_change` from the
  first `--prepare` rather than `investigation`/`harness_change`, to avoid the
  reclassification round entirely. (This is the exact adaptation the source
  project's own team converged on for 1DMIX-031 after being burned once on
  1DMIX-027 — now made explicit up front instead of rediscovered per project.)

**Expected outcome**: this does not reduce the *number* of forced
confirmation-only rounds, but should reduce their *cost* — from "rediscover
the recovery path under time pressure" (the 1DMIX-027 case, a fully discarded
iteration) to "follow the documented recipe" (closer to the 1DMIX-031 case, a
single clean redispatch) — combined with Problem 1's fixes making that
redispatch itself faster.

---

## Problem 3 — Footer-convention ambiguity: real fields with no discoverable correct value

**Evidence**: closing one issue (1DMIX-026) alone required **4 separate
correction rounds purely for footer format**, after the substantive review
was already correct:
1. `candidate_signature` — both Bob and Richard reported
   `issue_candidates.py check`'s own content-addressed signature (e.g.
   `2600dcae...`). The gate (`workflow_policy.py::current_review`, consumed by
   `final_verification.py:103`'s `source_signature(root)`) requires a
   **completely different hash scheme** — `project.py::source_signature(root)`
   (e.g. `5d7e6aa0...`). These are two unrelated digests over overlapping but
   differently-structured data (confirmed directly: `issue_candidates.py:18`
   imports `paths as inventory_paths` from `doc_inventory`, a different
   function from `project.py::inventory_paths`, and hashes a differently-shaped
   per-file dict).
2. `documentation_review.status` — Richard wrote `"sealed"` (accurately
   describing the report's own state). `doc_contract.py:484` requires the
   literal string `"confirmed"` (describing the reviewer's act of confirming
   it). This exact synonym confusion recurred multiple times across the
   source project's full history (also hit as `"confirmed_current"` in an
   earlier issue).
3. `independent_check.evidence` — left as `{"path": "", "sha256": ""}` because
   a plain `pytest` invocation has no sealed evidence file of its own;
   `final_verification.py:110`'s `verify.load_evidence()` requires a real,
   content-addressed reference regardless.
4. A `correction_round` dispatch-parameter mismatch against what the agent
   self-reported in its own footer.

**Root cause, confirmed directly**: the artifact every Bob/Richard is told to
use — `esx/templates/agent_report.json` — has **empty placeholder strings**
for every one of these fields (`"candidate_signature": ""`, `"verdict": ""`,
`"documentation_review": {"status": "", ...}`). The role definitions
(`.claude/agents/richard.md:34`, `bob.md`) say only *"Use the common footer
in `esx/templates/agent_report.json`. Preserve actual observed fields"* and,
for `candidate_signature` specifically, *"An approval usable for closure has
... current candidate signature"* — a conceptual description with no
worked example and no runnable command to compute the concrete value.
**The correct values are fully specified — but only inside this framework's
own test fixture** (`tests/test_framework.py:87-92`, its `footer.update(...)`
call), which no dispatched agent ever reads.

Compounding this: there is **no CLI command anywhere in `tools/esx/` that
prints `project.py::source_signature(root)`** — an agent (or Arch) needing
the correct value has no way to get it except writing a throwaway Python
one-liner, which is exactly what happened in the source project.

### Fix implemented here

1. **`tools/esx/project.py`** gains a `signature` CLI subcommand
   (`python3 tools/esx/project.py signature [--scientific]`), printing the
   exact JSON `{"signature": "<64-hex>"}` value required for
   `candidate_signature`. Mirrors the existing `issue_candidates.py`
   subcommand-CLI convention in this same directory.
2. **`esx/templates/agent_report_guide.md`** (new file) documents, field by
   field, for every non-obvious entry in `agent_report.json`: the exact
   command to compute `candidate_signature`
   (`python3 tools/esx/project.py signature`), the exact literal enum values
   for `verdict` (`APPROVE` / `APPROVE_WITH_FIXES` / `REJECT`) and
   `documentation_review.status` (`confirmed`, not `sealed` or any other
   synonym — with an explicit "sealed describes the report; confirmed
   describes your act of confirming it" callout, since this exact confusion
   recurred independently at least twice), and the requirement that
   `independent_check.evidence` be a real reference returned by
   `verify.py`/`final_verification.py`, never a plain command's own
   non-existent evidence. `richard.md` and `bob.md` now reference this guide
   directly next to their existing `agent_report.json` reference.
3. **Clearer `require()` messages** in `workflow_policy.py`/`doc_contract.py`
   for the two literal-enum checks (`documentation_review.status`,
   `verdict`), naming the exact expected value in the error text itself
   rather than surfacing only as a downstream "0 independent approvals"
   symptom several validation layers removed from the actual cause.

**Expected outcome**: eliminates the specific 4 correction rounds seen in
1DMIX-026's closure at the source; each of those 4 causes now has either a
runnable command (#1), a documented worked example (#2), or a self-explaining
error message (#3) available at the point an agent would otherwise guess
wrong. Projected savings: ~20-40 minutes of Arch diagnosis time per
`scientific_change` closure that hits any of these fields for the first time.

---

## Problem 7 — No self-assessment step; the lessons mechanism exists and is entirely unused

**Evidence**: `lessons_learned.md` and `lessons_learned_evidence.md` (both
present in `template/`, both shipped to every project) contained, in the
source project, **only their empty templates** after 3 days and dozens of
closed issues — despite `.claude/ESX-team/ARCHITECT.md` explicitly describing
the mechanism ("A lesson, milestone or domain rule is recorded when
warranted"). `loop_gate.py --next`'s issue-selection logic has no step that
ever looks at the loop's own recent performance (dispatch failure rate,
correction-round counts, discarded-identity rate) — the judgment of "was this
window efficient" is left entirely to an unprompted, easily-skipped
discretionary call, and across an entire multi-day session, it was never
made.

### Fix implemented here

1. **`tools/esx/loop_gate.py`**'s `--next` path now tracks how many
   `loop_history.jsonl` rows have accumulated since `lessons_learned.md` was
   last modified (a cheap `stat()` + count, no new state file). Past a
   configurable threshold (default 10, matching the exact window size this
   report itself used), `--next`'s output includes an explicit, un-skippable
   line: *"N iterations have completed since lessons_learned.md was last
   updated — record a self-assessment (or an explicit 'nothing new this
   window' entry) before continuing."* This does not block work (no gate
   failure); it is a visible nudge in the one place every iteration already
   reads.
2. **`.claude/ESX-team/ARCHITECT.md`** gains one sentence tying this nudge to
   the existing lesson-recording sentence, and one worked example of a
   *process* lesson (as distinct from a *scientific* lesson) — e.g. "N
   distinct agent identities were dispatched for the same role at round 0
   before one was reused" as a metric worth checking periodically, citing
   this document.

**Expected outcome**: converts the lesson mechanism from "exists, unused,
rediscovered from scratch each time" into "surfaced automatically at a
predictable cadence." Success is measurable: the next time this exact kind of
retrospective is run on any ESX-Team project, `lessons_learned.md` should
contain real entries rather than only its template.

---

## Problem 4 (revised) — Stale duplicated source, reframed as a generic mirror-drift check

**Original framing, and why it was initially left out**: the source project's
own vocabulary — "experiment directories," each with a `code_validation/`
copy of shared Fortran instrumentation (`kpp_calc.F`, `kpp_routines.F`,
`ggl90_calc.F`) that must track a canonical `kpp_mods/`/`ggl90_mods/` source —
is MITgcm-specific. This framework has no concept of "experiments" or
Fortran, and teaching it that literal vocabulary would be scope creep, not a
framework improvement. Confirmed directly this session: the source project's
own `lab_sea/code_validation/kpp_calc.F` had drifted (missing 4 prior fixes)
and was entirely missing `kpp_routines.F` — a real, previously-invisible bug,
found only by manual `diff`.

**The reframing** (added at the owner's explicit follow-up request): the
generalizable need underneath "experiment directories" isn't the MITgcm
vocabulary — it's **"a file that must be an exact copy of some other file,
because no import/symlink mechanism is available at that layer, and nothing
currently checks whether the copy has drifted."** That pattern is not
MITgcm-specific — it recurs anywhere a build/deploy step vendors a shared
file (a build system needing a local copy per build target, a monorepo
service copying a shared schema instead of importing it, generated
boilerplate that's supposed to match a template). This framework can check
that pattern generically without knowing anything about *why* a given project
has mirrors.

### Fix implemented here

1. **`esx/project.json`** gains an optional `mirrored_paths` field: a list of
   `{"canonical": path, "mirrors": [path, ...]}` entries. Empty by default —
   zero effect on any project that doesn't configure it. `project.py::config()`
   validates the shape (a nonempty canonical path and a nonempty list of
   mirror paths per entry) but deliberately does *not* check existence there;
   see below for why.
2. **`tools/esx/audit.py::audit_mirrors()`** (new function, wired into the
   existing `audit.check()` — the same function already called at every
   `--prepare`, `--next` and `--check-done`) reads each canonical file's bytes
   once and compares every one of its configured mirrors against them,
   reporting exactly one of: the mirror is missing entirely ("should mirror
   X"), the mirror's bytes have drifted from the canonical source, or the
   canonical file itself is missing. This messaging is more specific than a
   generic "configured input is missing," which is why existence-checking
   lives here rather than in `config()`.
3. **`README.md`**'s configuration reference table gains the `mirrored_paths`
   row.

A project like the source one would configure this once per canonical file:
```json
"mirrored_paths": [
  {"canonical": "MITgcm_to_Python_port_verification/mitgcm_verification_mods/kpp_mods/kpp_calc.F",
   "mirrors": ["MITgcm_to_Python_port_verification/mitgcm_verification_mods/lab_sea/code_validation/kpp_calc.F",
               "MITgcm_to_Python_port_verification/mitgcm_verification_mods/global_oce_latlon/code_validation/kpp_calc.F", "..."]}
]
```
— and the exact `lab_sea/kpp_routines.F` gap found this session would have
been caught automatically at the next `--prepare` or `--next`, before any
agent spent time working against stale instrumentation.

**Expected outcome**: any project that configures `mirrored_paths` gets this
class of bug converted from "found by luck, eventually, via manual `diff`"
to "caught automatically at the next routine gate check." Zero effect on
projects that leave it unconfigured.

## Problems not generalized here

**Problem 6** (Docker build-cache/raw-capture disk accumulation during
MITgcm rebuilds) remains a property of that project's own MITgcm verification
harness — this framework has no concept of "Docker rebuilds" or capture
pipelines, and inventing one here would be scope creep, not a framework
improvement. Left for that project to fix in its own tooling (already scoped
in its own diagnostic report's fix #6).

**Problem 5** (a real `sys.path` regression invisible to `pytest` because a
test file's own import shadowed the bug) generalizes only as a *testing
pattern*, not a code change: "add a subprocess-level smoke test for any
script with a documented CLI `Usage:`, since an in-process test import can
mask a bug in the script's own standalone entry point." This framework's own
`tools/esx/*.py` files are exactly this class of script. No instance of this
specific bug was found in this framework's own tooling during this review,
and `tests/test_framework.py` already exercises several `tools/esx` entry
points via direct import rather than subprocess — worth a dedicated,
separately-scoped audit rather than a speculative fix bundled into this
document. Recorded here as a candidate for a future, focused pass, not
implemented in this round.
