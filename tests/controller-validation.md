# Controller refactor validation

## Scope and boundary

September 27, 2026. Initially implemented on `refactoring/collaboration-contract`,
based on `origin/dev` at `b38b749` and carrying the existing launch/profile and
live-validation fixes. The reviewed result is now carried by
`fix/claude-worker-validation` in [PR #13](https://github.com/weirdry/crew/pull/13). The original checkout had an unfinished revert and staged
changes; implementation used a separate worktree. Its original diff was checked
byte-for-byte against the saved baseline and remained unchanged during isolated
development. After authorization to update PR #13, the pending revert was
completed as `0da688a`, then the refactor was transferred with file-byte parity.

Boundary classification: released — compatibility required because published
v0.1.3 and existing installations use v1 partner receipts, and retained v1
receipts were confirmed by read-only metadata inspection. No runtime receipt,
active-run pointer, approval record, installed skill, or live worker was modified.

The new producer writes controller-owned v2 receipts. Legacy receipts require an
explicit matching live-partner handoff and preserve the original bytes in an
immutable content-named archive. New receipts do not preserve a fabricated lead
pane. Run, relay and approval formats are unchanged. See the
[execution contract](../skills/crew/references/execution.md).

## Implemented outcome

- The installed skill entry points to collaboration, execution, record, workflow,
  and supervision contracts, plus a reusable assignment template.
- `partner.py` owns lifecycle and ownership; `herdr_transport.py` owns explicit
  CLI transport and launch profiles. Thin shell entry points remain available.
- A stable controller ID owns the retained worker; session/name/kind/pane identify
  its process. A lead pane and HERDR_ENV are unnecessary.
- Prompt, observation, dialog and approval paths use the recorded session. A
  controller caller cannot fall back to ambient targeting after receipt loss.
- Handoff, conflicting controllers/sessions, changed identity/receipt, and
  uncertain startup preserve ownership boundaries. A local lock serializes
  partner mutations; no daemon, lease service or workflow engine was added.
- Finishing preserves the retained partner. Retirement remains explicit.

## Local evidence

`sh tests/ci.sh` passed:

| Suite | Passed |
| --- | ---: |
| Strict Herdr fixture cases | 171 |
| Relay and summary cases | 23 |
| Controller lifecycle cases | 27 |
| Release/archive/installation cases | 43 |
| Total | 264 |

Shell syntax and release-version policy passed in the same entry point.
The skill-creator quick validator passed in an isolated uv environment with
PyYAML. Local links in the installed skill resolved. Tracked/staged diff whitespace
checks passed; new source files were also inspected. Tests use synthetic data,
stub Herdr and disposable directories. No actual agent is delegated work.

Controller tests cover both supported native launch profiles, execution without
lead-pane environment, workspace placement, reuse, exact worker identity, session
collisions, explicit legacy handoff with byte preservation, refusal to recreate
a missing worker during handoff, changed receipts, symlinks, concurrent operations,
verified retirement, one-shot dialog routing, missing-receipt refusal, status,
and artifact completion followed by retained-partner run finish.

## Evidence limits

No hosted CI, dev integration, release, installation update, or live Herdr/agent
acceptance was performed for this refactor. The prior provider permission findings
in [live-claude-validation.md](live-claude-validation.md) remain applicable. Pinned
launch arguments do not prove enforcement; each effective worker still needs the
state-root shell/edit probe before reusable approvals are trusted.

The synthetic lifecycle is not a model-authored implementation/review run. Live
validation must use an isolated session and state root when separately authorized;
existing user receipts are not disposable fixtures.

Tracking: [issue #14](https://github.com/weirdry/crew/issues/14).
