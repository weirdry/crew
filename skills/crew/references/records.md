# Run records and completion evidence

## Run directory

All data moves through files. The terminal carries control signals only.

In the commands below, `<crew-skill-dir>` is the directory containing this `SKILL.md`. Resolve
it from the loaded skill location; keep the shell cwd at the repository where the run belongs.

The lead-only authority state root, called `<state>` below, is
`${CREW_STATE_DIR:-$HOME/.crew}/<workspace-key>/`, where `<workspace-key>` is the partner name
without `crew-`. The helpers derive the key from the canonical cwd, validate the resolved root
outside the repository and worker-writable temporary roots, and refuse an unusable root.

Create `<cwd>/.crew/<run-id>/` where `<run-id>` is `date +%Y%m%d-%H%M%S`. The run directory
must live inside the working tree. Keeping the authority root outside that tree is necessary
for a workspace-scoped sandbox, but its location alone does not prove a worker cannot write it.

Initialize the run with the helper. It resolves the real Git exclude file before writing run
state, including when the cwd is below the repository root or `.git` is a linked-worktree file.
It prints the run id. It refuses with exit status 6 when `<state>/.current` already exists and
prints the run it preserved. On exit 6, read the named run's `state.md` before deciding: resume
a genuinely open run; treat the pointer as abandoned only when its lead died. Pass
`--replace-current` only after the user explicitly approves abandoning that run; its directory
remains untouched.

```bash
<crew-skill-dir>/scripts/run-init.sh
```

Only after that explicit approval, run the override instead:

```bash
<crew-skill-dir>/scripts/run-init.sh --replace-current
```

To perform the same steps by hand, resolve `<state>` with the same validator, resolve the exclude
path through Git, add `.crew/` only when absent, create the timestamped directory, write the
state fields shown in the file table, and then update `<state>/.current`:

```bash
state_json=$(<crew-skill-dir>/scripts/state-root.sh) || exit
state=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["state_root"])' "$state_json") || exit
mkdir -p "$state"
exclude_file=$(git rev-parse --path-format=absolute --git-path info/exclude) || exit
if ! grep -Fqx '.crew/' "$exclude_file" 2>/dev/null; then
  # Start a new line even when the existing file has no trailing newline.
  printf '\n%s\n' '.crew/' >> "$exclude_file" || exit 1
fi
if [ -e "$state/.current" ]; then
  IFS= read -r current_run < "$state/.current"
  printf 'current_run=%s\noutcome=current-exists\n' "$current_run" >&2
  exit 6
fi
run_id=$(date +%Y%m%d-%H%M%S)
mkdir -p .crew
mkdir ".crew/$run_id"
printf '%s\n' '# Crew state' '' \
  '- Phase: 0 — scope not frozen' '- Round: 0 of 3' \
  '- Worker: none' '- Pane: none' > ".crew/$run_id/state.md"
(set -C; printf '%s\n' "$run_id" > "$state/.current")
```

The noclobber write catches a concurrent creator after the manual precheck. If it fails, leave
the existing pointer untouched, remove only the run directory just created by this attempt,
and stop. Do not perform a manual replacement; use the helper's explicit override path.

Every shell invocation starts fresh, so the run id has to survive on disk. Resolve `<state>` and
read the active run back from `<state>/.current` afterwards:

```bash
IFS= read -r run_id < "$state/.current"
```

Files the loop writes — lead authority under `<state>`, worker and review artifacts in the run
directory, and the inert approval audit copied there at Finishing:

| File | Written by | Purpose |
| --- | --- | --- |
| `<state>/.current` | lead | Active run id; present from initialization through an open run, removed after terminal Finishing |
| `<state>/worker.json` | `worker-start.sh` | Workspace partner identity, controller ownership and session used by attach and guarded retirement |
| `<state>/<run-id>/approvals.jsonl` | `approval.sh` | Run-scoped exact approvals plus inert set-grant proposals and granted sets |
| `.crew/<run-id>/approvals.audit.jsonl` | `run-finish.sh` | Inert terminal copy of the approval record; never read as authority |
| `.crew/<run-id>/task.md` | lead | Frozen scope; contents specified in "What `task.md` must contain" below |
| `.crew/<run-id>/plan-check.md` | worker | Pre-implementation objections; required when the change touches shared machinery |
| `.crew/<run-id>/report-<n>.md` | worker | What it did, what it checked, open questions |
| `.crew/<run-id>/review-<n>.md` | lead | Structured findings and verdict |
| `.crew/<run-id>/dismissed.md` | lead | Closed findings with one-line reasons; never reopened |
| `.crew/<run-id>/state.md` | lead | Current phase, round number, worker name, pane id |

`state.md` makes a run resumable if the lead session dies. Update it at every phase boundary.

### Shared context relays

One run is one collaboration session; its retained partner may outlive that session.
Read [Context relays](relay.md) before using the relay helper. It defines the
record formats, publication rules, reading order, and optional compaction policy.

Use `.crew/<run-id>/relay/` for substantive questions, answers, rationale, user corrections,
and unresolved disagreements that the task/report/review artifacts do not already capture.
Each actor publishes its own completed record with `relay.sh append`. Corrections get new
records. Lead-published summaries live in `summaries/`; originals remain intact. A relay's
completion marker never replaces a phase's required report, self-review, or verdict.

On fresh entry or lost context, run `relay.sh read-plan <run-id>`, read its listed files,
and follow evidence references. Use `--after <id>` only while the same context still
understands that prefix of this run. There is no persisted reader cursor to inherit.
The lead links the current next-action relay in `state.md` at phase boundaries.
At every handoff, read new relays and their response chain before advancing the phase,
even when the expected report is present. A later correction can qualify that report.

Compaction is manual by default. `read-plan --budget-bytes <chosen-budget>` can suggest it
from the latest summary plus uncovered relays, without generating anything. Select any
budget from actual client use; there is no fixed token threshold, automatic summary per
handoff, or model invocation in the helper. The lead checks a summary's meaning before
`relay.sh publish-summary`; source hashes check identity, not correctness or approval.

### Inspecting run status

To inspect progress or an interrupted session, run from the same working directory and with the
same `CREW_STATE_DIR` used at initialization:

```bash
<crew-skill-dir>/scripts/status.sh
<crew-skill-dir>/scripts/status.sh --json
<crew-skill-dir>/scripts/status.sh --help
```

The helper only reads the existing state root and current run artifacts, invokes
`artifact-done.sh` for report completion, and queries `herdr agent get` for the recorded partner.
It does not require `HERDR_ENV=1`, create state directories, read approval records or terminal
frames, send input, transfer ownership, or make a completion or recovery decision. Herdr queries
time out after five seconds; missing or unrecognized responses remain unavailable. A partner
without an active run is reported as retained state, not as an unfinished run.

Both output formats distinguish recorded facts from live observations. JSON contains:

| Field | Meaning |
| --- | --- |
| `workspace`, `state_root` | Canonical locations from `state-root.sh`; `null` when validation failed |
| `run` | Pointer availability (`present`, `absent`, `unavailable`), run ID, recorded `phase` and `round` |
| `partner` | Receipt availability, recorded name/kind/worker pane, controller ID and session (legacy lead pane for v1), `observation` (`not-queried`, `live`, `absent`, `unavailable`, `mismatch`), and observed `agent_status` |
| `artifacts.latest_report` | Highest observed report round, relative path, availability, `complete`, and `self_review_complete` |
| `artifacts.latest_report.self_review_complete` | Report completion plus a phase-3 heading. Required only in round 1; `false` on a later report without that heading is not a missing requirement. |
| `artifacts.latest_completed_report` | Highest report round whose last line passes `artifact-done.sh`; an older report is not evidence for the current round |
| `artifacts.latest_review` | Highest observed review round, relative path, availability, and explicit verdict when readable |
| `attention` | Entries with a stable `code`, a bounded message, and a suggested `next_check`; no raw source text |

Unknown scalar facts are `null`; an unobserved report or review is `null`. Receipt availability
stays `unavailable` until inspected; `absent` means the record was checked and does not exist.
The helper reads reports and reviews for the existing three-round protocol, in round order
rather than file modification order. `complete` refers only to a report's final `STATUS: done` marker.
`self_review_complete` additionally requires the exact `## Phase 3 self-review` heading outside
fenced examples and HTML comments. Phase 3 without that evidence is reported as needing attention
even when the implementation report is already complete. Neither field establishes the run's
final verdict.

At phases 4 and 6, the current-round report must already be complete, so a missing or incomplete
report needs attention regardless of the worker's live state. Phases 2 and 5 apply that check
once the worker is idle or done. A lead review still being written is not itself missing evidence.

Recorded progress recognizes the existing `- Phase: 0` through `- Phase: 6` or `- Phase: Finishing`
and `- Round: N of 3` lines; phase/round lines may include a description after `—` or `-`.
Phases 0-1 use round 0, phases 2-4 use round 1, and phases 5-6 use rounds 2-3. `Finishing`
can retain any round from 0 through 3. Contradictory combinations remain visible as recorded
facts and produce an attention item; they do not suppress missing-report checks.

Write the final verdict line using the format in [Review discipline](workflow.md#review-discipline).
Inspection recognizes one standalone `approve`, `approve-with-nits`, or `block` line, optionally
preceded by `Verdict:` or `- ` and optionally wrapped in bold (`**`) or inline code. Trailing
whitespace is ignored for verdict lines and self-review headings. Fenced examples, lines
containing HTML comments, ambiguous verdicts, arbitrary prose, and malformed metadata are not
interpreted as decisions. Unrecognized existing notes remain intact and can be read directly;
no state conversion is required.

`review-block` names the review's round. During rework it can refer to an earlier round's
request; this records the verdict and does not imply that the worker is stalled.

Exit 0 means no attention items were observed, including when there is no active run. Exit 1
means the snapshot contains attention items or unavailable evidence; JSON remains available.
`--help` prints usage and exits 0 without inspection. Exit 2 means invalid arguments.
This is a point-in-time, best-effort inspection: records and Herdr may change during the query.
Recheck before acting and follow the normal supervision, ownership, and approval rules.
Do not use status output as authorization to resume or clean up.
For pending conversational context, inspect `relay.sh read-plan <run-id>` separately.
Status inspection continues to report missing phase artifacts even while a relay question
awaits an answer; that question does not establish phase completion.

### What `task.md` must contain

Use [the assignment template](../templates/assignment.md). Include the role, inputs,
allowed reads/writes/actions, expected output/evidence, completion and stop conditions,
and decision owner. Also retain these task sections:

- `# Task` — one paragraph naming the goal and the files that hold the evidence for it.
- `## Acceptance criteria` — numbered, each checkable by reading a file or running a command.
- `## Out of scope` — the categories below, each stated as a prohibition.
- `## Style` — the voice and structure the edit must match.
- `## Deliverable` — the report file and the required closing `STATUS: done` line.

Add `## Context`, `## Item <n>`, or `## Likely files touched` when the work needs them, and
`## Amendments` last when the user accepts a phase 1 finding.

Include the run ID and resolved relay helper/contract paths in `## Context` when delegating.
Also include the exact canonical state parent from `state-root.sh`'s `state_parent` field.
Tell the worker to set `CREW_STATE_DIR` to that value on every relay publication command,
including when the lead uses the default location. Do not assume a new or retained worker
inherits the lead's shell environment. The worker needs read access to the active-run pointer;
this context grants no write access to authority state. Report an access refusal to the lead.
Tell the worker to read the current shared context, publish any substantive clarification
as an addressed relay, and return its path when an answer is needed. Normal report and
review artifacts remain the deliverables; do not duplicate them merely to create messages.

When the run edits a helper the lead uses to supervise it — `approval.sh`, `answer-dialog.sh` —
`task.md` says so in three clauses: the lead will not call that helper during the run and answers
dialogs by hand; the worker proves what refuses, through its own verifier; the lead proves what
sends, in phase 4, on the final source. Without them the worker has no way to satisfy a live
send criterion except by inspecting the lead.

`## Out of scope` names every category that applies to the run, and always these:

- Protected regions of the file under edit: name them explicitly.
- Other files: `README.md`, `LICENSE`, and anything else outside the named target.
- Scope creep inside the target: rewriting or adding beyond what the items require.
- Git operations of any kind.
- Network access of any kind, including package installation.
- Machine configuration.
- Panes the worker did not create.

## Completion is proved by artifacts, not by state

`herdr agent prompt --wait` settles on lifecycle transitions, not on turn boundaries. If the
worker was already busy, a settle can report the *previous* turn finishing. `unknown` never
proves completion either.

Therefore: a phase is complete only when its output file exists **and** its last line is

```
STATUS: done
```

Use the helper for that exact check:

```bash
<crew-skill-dir>/scripts/artifact-done.sh <artifact-path>
```

Exit status 0 is the only completed result. Without the helper, verify that the file exists and
compare its last line byte-for-byte with `STATUS: done`.

On a settled state with no artifact, re-read the pane before deciding.

Ask for the `## Phase 3 self-review` heading by name in the phase 3 prompt; use the phase-table
exit condition instead of the already-true artifact check.
