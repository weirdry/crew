# Changelog

## 0.1.4

- Capture the original worker pane ID in manual dialog handling and compare it
  before interpreting later sequence changes; stop on replacement or refusal.
- Align manual dialog handling with adapter delivery statuses and stop for user
  escalation when an uncertain send leaves the same dialog at the same sequence.
- Isolate all helper Python entry points from workspace modules and Python
  environment overrides, preventing workspace files from running as the lead.
- Distinguish pre-forward refusal from uncertain delivery after a prompt or key
  command; never treat a post-send receipt change or timeout as non-delivery.
- Align relay prompts and notification routing with the controller/session
  contract; document serialized waits, retained history, and legacy control limits.
- Keep fixture runs independent of inherited controller and Herdr variables and
  restore the documented missing-run error status.
- Accept colon-qualified Herdr pane IDs in retained-partner status inspection.
- Report a changed visible approval dialog separately when `state_change_seq`
  does not advance, without resending keys. Both changed-frame and timeout
  results remain uncertain and require lead inspection.
- Record the Codex-led Claude Code live validation, including the observed
  state-root write in auto mode and the one-shot manual-mode approval path.
  Disable approval reuse for the observed Claude configuration by lead rule;
  the live Claude Bash layout still refuses approval extraction. Clarify that
  Crew's pre-execution approval handling applies only to actions surfaced by
  the worker's own permission setting; task scoping and review remain usable.
- Start new Codex workers with workspace-write and on-request approvals, and
  new Claude workers in auto mode with native sandbox and file-edit denial for
  the authority state root. Existing live partners keep their permissions;
  approval reuse still requires a successful live state-root probe. The launch
  arguments have offline coverage and direct Claude CLI smoke evidence, but
  their effective Herdr behavior is not yet verified.
- Separate collaboration roles/assignments and phase decisions from execution
  coordination and Herdr transport. Keep detailed supervision, artifact, approval,
  and review rules in installed references behind a concise skill entry.
- Bind leads to a stable controller ID and explicit Herdr session instead of a
  lead pane. Create visible partner workspaces/tabs without inferring UI focus;
  preserve native worker launch restrictions and exact worker identity checks.
- Introduce controller-owned v2 partner receipts because published v1 receipts
  exist. Require explicit handoff, archive the exact prior receipt,
  and leave run/relay/approval formats unchanged. No automatic state migration.
- Route prompts, dialog replies, approvals and status through the recorded
  session. Refuse competing controllers and serialize partner mutations.
- Pin dialog replies to the initial complete partner receipt through approval
  checks and key delivery, refusing a replacement worker even under the same owner.
- Allow explicit owner handoff to restart a worker only when both the recorded
  agent and pane are confirmed absent; retain the old owner on failed startup.
- Publish complete handoff archives atomically without overwrite so an interrupted
  write does not leave a partial final archive that prevents retry.
- Refresh packaged installation examples to the verified published v0.1.3 tag.
  The managed installer is unchanged.

The changed send helper has synthetic regression coverage but has not been rerun
against a live consecutive-dialog sequence.

## 0.1.3

- Preserve the active-run pointer when the documented manual approval-audit copy
  fails, and reliably exclude `.crew/` in the manual initialization example.
- Align the phase-1 prompt with the required plan-check artifact, completion
  marker and path-only response. Make the relay walkthrough accessible from an
  installed skill through a published repository link.
- Refresh packaged installation examples to the verified published v0.1.2 tag
  alongside these skill corrections. Collaboration helpers, the managed
  installer and retained-state formats are unchanged.

Live Herdr behavior and fresh-agent comprehension remain unverified.

## 0.1.2

- Point installation examples and the installer smoke test at the verified
  published v0.1.1 release. Collaboration helpers and installers are unchanged.

## 0.1.1

- Make the existing Skills CLI the primary installation path, using an explicit
  published Crew tag without manual archive download or a new bootstrap tool.
- Explain source-pinned updates, installation ownership and the Codex installer's
  Git-method requirement. Preserve the managed archive installer and its checks.
- Add isolated installation coverage for the documented third-party tool path.

Collaboration helpers and the managed installer are unchanged. Live Herdr
acceptance remains unverified.

## 0.1.0

Initial governed release (early development, not a stable 1.0 contract).

- Distribute the Crew procedure, Shell/Python helpers, relay references and
  templates together in one versioned archive.
- Add explicit, verified installation and read-only checks for Codex and Claude
  Code, preserving unmanaged, modified and symlinked installations.
- Retain bounded collaboration, partner ownership, approval handling, status
  inspection, session context relays and on-demand summaries.

Live Claude permission dialogs, sandbox protection, worker relay access and
fresh-agent relay comprehension remain unverified. Offline checks and isolated
installation do not establish live agent acceptance.
