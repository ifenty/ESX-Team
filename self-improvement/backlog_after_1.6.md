# Backlog after 1.6

Proposed by the 1D_Mixing_Model and MITgcm_new_runoff coordinators during the 1.6.0
work and deferred. Each item names the measured problem it answers.

- **Detached dispatch.** `agent_runtime.py start --detach` returns the session and
  event ids at once, so the coordinator need not background the start command.
- **One-command closeout.** `closeout.py assemble` builds the final packet, runs final
  verification, fills the typed skeleton, rebinds the receipt and runs the doctor,
  stopping at the first judgment only the coordinator can supply. Two closeouts took
  about 15 manual steps each.
- **Premise review.** For a new algorithm or interface, a short code-free review of the
  brief's premises and supported input classes before implementation. One issue spent
  four rounds discovering a premise that could not hold.
- **Scoped re-approval.** When a round's diff touches nothing in a reviewer's declared
  scope, carry that approval forward with a recorded confirmation instead of a full
  review turn. One reviewer re-approved five times with no findings. Needs care so
  independent review is not weakened.
- **Witness registry.** Reviewers' witness scripts live in a per-issue directory and
  `verify.py --suite witnesses` reruns them every round.
- **Cost per round.** `--next`, the heartbeat and the retrospective report spend per role
  and per round, so growth of a retained session's cost is visible.
- **Owner-decision checklist** at `--prepare` for new features: inputs, defaults, units,
  scope and failure behaviour, asked before the first dispatch.
- **Shared kit lessons.** A lessons file shipped with the template, drawn from both
  projects' ledgers.
- **Lessons applied.** Closeout asks for one line per triggered lesson: how it was
  applied, or why not. (1.6.0 prints the lessons at `--prepare`.)
- **Screen status cadence** is guidance plus the `wake` helper; no gate enforces it.
- **Heavy role commands** have no kit-level memory bound; a role command once used 24 GB.
- **Slack receipt links** are not checked against the channel and timestamp they claim.
- **Advance guard threshold.** 6 advances within 120 s would not have caught a measured
  incident of 5 in 87 s; 4 within 120 s would, at some risk of pausing a healthy loop.
