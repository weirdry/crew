# Execution binding and retained state

## Controller and transport

The lead supplies a stable session identity and its host's model kind. Every
partner operation targets an explicit Herdr named session. The lead's pane,
`HERDR_ENV`, inherited focus, and process ancestry are not ownership inputs.
Do not change Codex daemon mode or ask the user to locate the lead's pane.

Read `herdr session list` to select an existing session. If more than one could
be intended, ask the user which session. Herdr remains required to execute and
observe workers. Direct CLI use here does not depend on the separate Herdr skill.

```bash
<crew-skill-dir>/scripts/worker-start.sh \
  --controller "$controller_id" --lead-kind codex --session "$session" claude
```

Swap the kinds for a Claude lead. Preserve the controller ID across runs in the
same lead session. Optionally pass `--workspace <workspace-id>` to place a newly
created partner tab in a selected workspace. Without it, creation makes a dedicated
partner workspace with the current project cwd and no focus change. Existing
partners retain their placement. Only Codex and Claude currently have supported
launch profiles. `--create` refuses if the recorded worker is already live.

The helper checks the active run, owner and session, different kinds, retained
name/pane/kind, native launch settings, and completion of startup. It serializes
start, retirement and bound commands per workspace with a local file lock.
Failure cleans up only a newly created pane when its identity remains consistent;
a reused pane is never closed as failure cleanup. An unavailable identity query
leaves the pane for inspection. Never blindly retry an ambiguous launch.

Pass the controller for **each** subsequent tool call (shell environment persistence
is not assumed):

```bash
CREW_CONTROLLER_ID="$controller_id" <crew-skill-dir>/scripts/herdr.sh agent get "$worker"
CREW_CONTROLLER_ID="$controller_id" <crew-skill-dir>/scripts/herdr.sh agent prompt "$worker" "Read the assignment at $prompt and return its requested artifact path."
CREW_CONTROLLER_ID="$controller_id" <crew-skill-dir>/scripts/approval.sh check "$worker"
```

`herdr.sh` supports agent get/read/prompt/wait/send-keys only. It verifies the
recorded controller and worker against the live session before forwarding the
command. Use it for supervision as well as prompts. `answer-dialog.sh` and
`approval.sh` route controller receipts to that same explicit session. Status
inspection is read-only and does not require ownership.

`worker-start.sh`/`worker-stop.sh` return 0 on success, 2 for arguments, 3 for an
invalid run/root or retirement binding, 4 for missing retirement receipt, 10 for
unavailable/invalid state or transport, 11 for owner/session/lock/handoff refusal,
12 for same-kind collaboration, 13 for an already-live `--create`, and 14 for a
retained worker kind mismatch. Read the diagnostic; do not retry mutation merely
because the helper returned nonzero.

## Receipt and compatibility boundary

Published Crew v0.1.3 writes v1 `worker.json` with `lead_pane_id`. Installed copies
and retained v1 receipts are real consumers/state. The controller receipt is v2:

```json
{"version":2,"controller_id":"host-session-id","lead_kind":"codex","session":"work","worker_name":"crew-example","worker_kind":"claude","worker_pane_id":"w1:p2"}
```

The existing path and worker identity remain stable. Run directories, active-run
pointers, approval keys/logs, relays and summaries keep their existing formats.
No startup bulk migration, reset, or approval rewrite occurs.

For v1, status and approval inspection retain their published ambient transport;
the new start/stop path refuses ownership until an explicit handoff. The prior
installed helper may still operate an untouched v1 receipt. It rejects v2 because
v2 no longer contains `lead_pane_id`; do not operate old/new helpers concurrently.
After the user authorizes handoff and confirms the intended session and stopped
old lead, start with its exact owner:

```bash
<crew-skill-dir>/scripts/worker-start.sh \
  --controller "$controller_id" --lead-kind codex --session "$session" \
  --handoff-from "pane:<recorded-lead-pane-id>" claude
```

For another v2 controller, pass its exact `controller_id` instead. Handoff only
attaches a matching **live** partner; it neither creates a replacement nor changes
its permissions. v2 handoff cannot change the recorded Herdr session. v1 did not
record a session, so the user's session selection is part of that handoff decision.
The exact old receipt bytes are preserved as `worker-<sha256>.json` before atomic
replacement. Refusal leaves the original receipt and all run records intact.
These archives are historical evidence, not alternate readers or authority.

This is a bounded one-way transition. Once a workspace uses v2, no v1 writes or
fallback occur there. Remove v1 support only after installed consumers and retained
v1 receipts have been retired or explicitly handed off; no speculative v3 path.
Do not perform any of these actions merely while installing or developing Crew.

## Retire

Only on an explicit user request:

```bash
<crew-skill-dir>/scripts/worker-stop.sh \
  --controller "$controller_id" --lead-kind codex --session "$session"
```

The helper rechecks exact live identity and unchanged receipt before closing the
partner pane, then removes only that receipt. It does not close a lead, another
agent, a workspace, or the server. Run completion keeps the partner and receipt.
