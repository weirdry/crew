# Changelog

## 0.1.4

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
- Accept an explicitly selected lead pane and named Herdr session in worker
  start and stop helpers. Codex command runners refuse inherited `HERDR_*`
  values without that selection, since a shared daemon can omit or reuse
  another client's values. Herdr validates the selected live lead before worker
  creation, and retirement still checks the recorded lead and worker identity.
  `HERDR_ENV` is a pane-local hint, not a Herdr API requirement. Automatic
  Codex thread-to-pane binding remains an upstream client-context gap; a
  special `codex --no-daemon` launch is no longer a Crew prerequisite.
- Refresh packaged installation examples to the verified published v0.1.3 tag.
  The managed installer and retained-state formats are unchanged.

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
