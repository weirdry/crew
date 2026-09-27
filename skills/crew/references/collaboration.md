# Collaboration contract

## Responsibility boundaries

| Boundary | Owns | Does not decide |
| --- | --- | --- |
| Collaboration procedure | Run scope, role, assignment, expected evidence, phase and review decision | Terminal layout or provider sandbox behavior |
| Execution coordination | Controller binding, verified partner identity, lifecycle and bounded supervision | Whether a finding is substantively correct |
| Herdr transport | Explicit session, visible worker, prompt/read/wait/input and placement | Assignment completion or new approval authority |

These are responsibilities within one skill and its helpers, not separate services.
The skill is the host entry point and procedure; it does not require loading the
separate Herdr skill. The transport calls the installed Herdr CLI directly.

## Roles and records

- **User:** authorizes the goal, scope changes, new external actions and ownership
  handoffs; can observe or intervene in Herdr throughout.
- **Lead:** owns scope, assignments, supervision, independent review, disposition,
  and handoff. A specific lead session has a controller ID; its model kind is a
  separate fact. The lead may execute through a daemon with no terminal identity.
- **Worker:** implements within the assignment, supplies evidence, performs a cheap
  self-check, and responds to findings. It does not grant itself new authority,
  dispose of scope objections, or assign replacement workers.
- **Partner:** the retained worker process identified by named Herdr session,
  agent name, model kind and pane. Placement is not lead authority.
- **Run:** a bounded goal and review loop, independent of terminal lifetime.
- **Assignment:** who does what, from which inputs, with which allowed actions,
  expected output/evidence, completion and stop conditions, and decision owner.

`task.md` is the run's assignment; do not introduce a second mutable task database.
Use the [template](../templates/assignment.md). `report-N.md` carries results and
worker responses; `review-N.md` carries independent findings and lead disposition.
Reference finding IDs when responding and record why a finding was accepted,
fixed, withdrawn, or escalated. Never silently erase an earlier finding.
`dismissed.md` preserves rejected objections. `state.md` records the current
phase/round and next action. Relays provide addressed clarification and continuity.

## Evidence and handoff

Distinguish observed results from inferences, proposals and pending decisions.
A passing helper fixture is not proof of live provider sandbox behavior.
The report terminator proves the artifact is ready to review, not that it is correct.

At handoff record: run/assignment, phase and round, current partner binding,
artifact paths, performed checks, unresolved findings, granted authority, next
actor/action, and explicit stop conditions. Read task → state → latest valid
relay summary and tail → referenced original artifacts. Do not copy hidden
reasoning or rely on the preceding lead's private chat.

A new lead ID cannot automatically take a retained partner. After the user approves
handoff and the old lead has stopped issuing work, use the exact previous owner
with `--handoff-from`. Controller IDs prevent accidental cross-session reuse;
they are not authentication against a malicious process with authority-state access.

No general workflow engine, automatic scheduler, extra approval phase, or provider
API backend is needed for this contract. Preserve the bounded phase table.
