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

## From the 1.6.2 acceptance run

- **Stale-figure sweep is noisy for bare small integers.** A figure such as `46` matched
  namelist values and test constants, not the count it was meant to find. Warn when a
  figure is a number shorter than three digits with no context, say in the documentation
  and the brief rule that figures are written as they appear in prose ("46 rules",
  "26-41 m"), and consider searching only prose files and comments by default.
- **`provider_limit` is stored only on a failed turn.** A limit that surfaced as an
  incomplete turn would be missed; store it for any turn that did not complete.
- **A live pause and resume under a running loop** was covered by unit tests only in the
  acceptance run; exercise it at the next real loop on each project.

## From the 1.6.3 acceptance run

- **Automatic-pause message.** The Stop hook's message for a pause it set itself says
  "until /esx-loop resumes it", which suggests a manual resume is needed. For
  `pause_source: provider_limit` say "until the usage limit resets; it resumes by itself on
  the next working turn (or /esx-loop)".
- **Mistyped-reference messages.** "invalid verification artifact path" is accurate but
  hard to act on; name both values ("the path names <sha in path> but sha256 is <given>"),
  and the same for orientation and documentation references.
- **Owner check behind freshness.** In `footer_contract.reference_errors` a stale evidence
  file hides an owner mismatch; report the owner independently of freshness.
