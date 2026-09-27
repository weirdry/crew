---
name: crew
description: "Run an explicit, bounded collaboration between different model kinds in Herdr, with visible workers, shared assignments, independent review, and durable handoffs. Use only when the user asks to use Crew. The lead does not need to run inside a Herdr pane. Do not use for same-model delegation."
---

# Crew

Crew organizes a repeatable collaboration that the user can watch and intervene in.
You are the **lead**: scope, delegate, supervise, review, and decide whether the
agreed work is complete. A worker of a **different model kind** implements it in
Herdr. A run has frozen scope and at most three review rounds. The workspace
partner can remain open across runs; finishing never retires it.

## Read before acting

1. [Collaboration contract](references/collaboration.md): roles, assignments,
   evidence, decisions, and handoff.
2. [Execution binding](references/execution.md): controller ownership, Herdr
   session, worker launch, reuse, and explicit handoff of older records.
3. [Records](references/records.md) and [workflow](references/workflow.md): run
   initialization, artifact completion, phases, review, and finishing.
4. Before contacting a worker, read [supervision](references/supervision.md),
   including permission classification, state-root protection, and uncertain sends.
5. For substantive clarifications or context recovery, read the
   [relay contract](references/relay.md). Relays do not replace reports or reviews.

These are parts of one procedure, not optional alternative workflows.

## Start

- Establish the authorized task, acceptance criteria, and limits. Do not ask for
  permission already given. Record the starting Git commit and dirty paths; preserve
  existing work. The worker is the sole source editor during a Crew run.
- Establish your model kind from the host and choose the other supported kind
  (`codex` or `claude`). Never infer model kind from a focused terminal.
- Use a stable **controller ID** for this lead session. A host-provided session ID
  (for example `CODEX_THREAD_ID` when available) is suitable. Otherwise generate a
  UUID once and retain it in lead context. It is a coordination identity, not a
  credential or proof of the model. Do not regenerate it on each command.
- Select the intended **named Herdr session** using read-only `herdr session list`.
  If selection is ambiguous, ask which session to use. Do not start a new server
  by guessing its name. A missing `HERDR_ENV` or lead pane ID is not a blocker.
- Resolve `<crew-skill-dir>` from this loaded skill. Keep the cwd at the project.
  `run-init.sh` creates the run; on an existing pointer, read and resume the open
  run. Abandonment requires explicit user approval.
- Write `task.md` using [the assignment template](templates/assignment.md), then
  start/attach through `worker-start.sh` with the binding in execution.md. Without
  a selected workspace, Crew creates a dedicated visible partner workspace. With
  `--workspace`, it creates a partner tab there. It never uses the UI focus.
- A different recorded owner requires an explicit handoff; do not claim it just
  because its pane disappeared. Establish the old lead has stopped issuing work
  and obtain the user's authorization before `--handoff-from`.

## Execute and review

Follow the phase table in [workflow.md](references/workflow.md):

`scope → plan check when needed → implement → self-check → lead review → bounded rework`

An assignment names inputs, allowed writes/actions, output and evidence, completion
and stop conditions, and decision owner. Normal work within the assignment proceeds
automatically. Scope expansion and new external authority return to the user.

Use the bound `scripts/herdr.sh` for all partner interaction. On every invocation
of that helper, `approval.sh`, or `answer-dialog.sh`, supply the same
`CREW_CONTROLLER_ID`; tool shells may not preserve environment between calls.
All of these use the partner receipt's session. Never substitute raw ambient Herdr
commands for a refused binding.

Completion requires the expected artifact and exact `STATUS: done` terminator;
self-check additionally requires its named heading. Terminal idle/settled state is
an observation only. The lead reviews the actual diff and evidence against both
the user's request and `task.md`. Keep findings, worker responses, and lead
resolution separate. Preserve rejected findings and their reasons.

Native model permissions remain authoritative. Approval-record reuse is allowed
only after the exact worker's shell and edit paths are shown unable to alter the
external state without authorization. An unproven protection boundary means
one-shot user escalation. Never resend an uncertain key delivery automatically.

## Finish or hand off

Record the current phase/round, assignment, artifacts, unresolved findings,
decisions, and next action so another lead can resume without private chat.
Keep the existing relay originals and approval authority records. `state.md`
summarizes progress; it does not confer permission or certify completion.

An approved terminal verdict allows `run-finish.sh <run-id>` to preserve the audit
and release the active-run pointer. Unresolved blockers at round 3 or unanswered
escalations leave the run open. Report the outcome and record paths to the user.

Retire the partner only when explicitly requested, through `worker-stop.sh` with
the recorded controller and session. Never stop the Herdr server as run cleanup.
