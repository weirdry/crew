# Collaboration procedure

## Phases

Every row also reads the current shared relay context. Before advancing, apply the
relay handoff check in the Supervision loop, including when an artifact is already complete.

| # | Actor | Reads | Writes | Exit condition |
| --- | --- | --- | --- | --- |
| 0 | lead + user | user request | `task.md` | The user request authorizes the recorded scope; clarify only missing decisions. Scope is now frozen. |
| 1 | worker | `task.md`, repo | `plan-check.md` | Artifact present (may be `없음`). Required for shared machinery; see below. |
| 2 | worker | `task.md` | code, `report-1.md` | Artifact present with `STATUS: done` |
| 3 | worker | own diff | appended to `report-<n>.md` | A `## Phase 3 self-review` heading exists and the last line is still `STATUS: done`. Keep this cheap. |
| 4 | lead | `git diff`, `task.md` | `review-<n>.md` | Verdict recorded |
| 5 | worker | `review-<n>.md`, `dismissed.md` | code, `report-<n+1>.md` | Artifact present with `STATUS: done` |
| 6 | lead | new `git diff` | `review-<n+1>.md` | `approve` → stop. `block` → round += 1, return to 5. |

Round 1 spans phases 2 through 4. Use the round number for `<n>` in `report-<n>.md` and
`review-<n>.md`. A `block` in phase 4 starts round 2 at phase 5. After each later `block`,
increment the round before returning to phase 5. Round cap is **3**. If the increment would
start round 4, do not return to phase 5. Stop, copy every unresolved finding that caused the
`block`, including its `withdraw_if` condition, into `state.md`, and hand them to the user. Do
not keep iterating.

Run phase 1 whenever the change touches something an existing component already reads, calls,
or depends on — a helper script, a file another script consumes, or a rule another section cites.
Skip it only for an isolated edit with no consumer.

Phase 1 findings are objections against frozen scope, not authority to reopen it. The lead
takes them to the user as proposed amendments; neither agent disposes of one alone. Append each
accepted amendment to `task.md` under `## Amendments`, where it supersedes any earlier clause of
that file it conflicts with, `## Out of scope` included. Record each rejected finding in
`dismissed.md`. From the phase 2 prompt onward, follow the dismissal discipline under
"Review discipline" whenever that file is non-empty.

Limit phase 3 to mechanical breakage; reserve independent review for phase 4.

In phase 4 review the diff against **the user's original request**, not only against your own
`task.md`.

## Review discipline

Apply this symmetrically to the lead's reviews and every worker objection.

Every finding uses this shape:

```
- id: R1
  severity: blocker | major | nit
  location: <file:line> or <task.md clause>
  failure: <specific input or state> → <specific wrong outcome>
  withdraw_if: <condition that retracts this finding>
```

Enforced rules:

- A finding with no concrete `failure` is discarded. Discomfort is not a finding.
- A `blocker` with no `withdraw_if` is invalid. A blocker must be falsifiable and satisfiable.
- At most 5 findings per review, at most 2 blockers. Rank by severity.
- Every review ends with exactly one standalone line: `Verdict: approve`,
  `Verdict: approve-with-nits`, or `Verdict: block`. Write that line as plain text, with the
  spelling and capitalization shown, and place the rationale above it. Keep punctuation,
  explanations, and examples off the final verdict line.
- Use `approve-with-nits` only when no blocker remains. Send the nits to the still-live worker
  as one final pass that does not consume a round, and allow at most one such pass. If the
  worker is already gone, record the nits under `Deferred nits` in the current `review-<n>.md`
  and finish the run.
- An approval must list what was actually inspected: files read, commands run, tests executed.
  An approval with no evidence of inspection is invalid; redo the review.
- Dismissed findings go to `dismissed.md` with a one-line reason. They are closed. Attach
  `dismissed.md` to every later worker prompt and state that closed items may not be re-raised.
- Objections are input, not veto. Record the reason and proceed.
- Frozen scope may not be reopened by either agent. Scope changes go to the user.

## Finishing

- A run stopped at the round cap with unresolved blockers or at an unanswered class-(b)
  escalation has no terminal verdict. Keep `<state>/.current` and use the run directory's `state.md` as the resume
  point; do not enter the remaining Finishing steps.
- Read `<state>/worker.json` and report the retained partner's `worker_name` and `worker_pane_id`.
  Do not close it or remove its receipt at Finishing.
- End the named run:

  ```bash
  <crew-skill-dir>/scripts/run-finish.sh "$run_id"
  ```

  Partner liveness does not gate run completion; nothing reads the audit copy.
- Without the finishing helper, apply the same approval-copy and pointer checks:

  ```bash
  IFS= read -r current_run < "$state/.current"
  test "$current_run" = "$run_id" || exit 1
  test -d ".crew/$run_id" || exit 1
  python3 - "$state/$run_id/approvals.jsonl" ".crew/$run_id/approvals.audit.jsonl" <<'PY' || exit 1
  from pathlib import Path
  import os, stat, sys
  source, audit = map(Path, sys.argv[1:])
  if os.path.lexists(source):
      if not stat.S_ISREG(source.lstat().st_mode):
          raise SystemExit("approval record is not a regular file")
      data = source.read_bytes()
      if os.path.lexists(audit):
          if not stat.S_ISREG(audit.lstat().st_mode) or audit.read_bytes() != data:
              raise SystemExit("approval audit already exists with different or unsafe content")
      else:
          with audit.open("xb") as handle:
              handle.write(data)
              handle.flush()
              os.fsync(handle.fileno())
  PY
  IFS= read -r current_run < "$state/.current"
  test "$current_run" = "$run_id" || exit 1
  rm "$state/.current"
  ```

- Keep the partner open. Retirement is never an implicit Finishing step.
- Leave the run directory in place; it is the audit trail. Tell the user its path.
- Report: rounds used, final verdict, files changed, retained partner name and pane id, dismissed
  findings, and anything escalated but never answered.
- Never run `herdr server stop`. Never close panes, tabs, or workspaces you did not create.
