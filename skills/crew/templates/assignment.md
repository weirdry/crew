# Task

State the authorized goal, starting revision/dirty paths, and evidence locations.

## Assignment

- Run:
- Role: worker — implementation and self-check
- Lead / decision owner:
- Worker name and kind:
- Inputs: user request, relevant files, previous findings, relay read plan
- Allowed reads:
- Allowed writes and actions:
- Expected output: report path, changes, checks and evidence, uncertainties
- Completion: expected artifact, exact `STATUS: done`, required self-check heading
- Stop: scope conflict, missing input, permission escalation, round cap

## Acceptance criteria

1. State observable outcomes and how each is checked.

## Out of scope

Name protected files/regions and unapproved Git, network, machine configuration,
other panes, authority-state writes, and unrelated changes. Preserve existing work.

## Context

Include run ID, canonical state parent, resolved relay helper and contract paths,
and relevant original evidence. Worker relay commands explicitly set CREW_STATE_DIR.
Do not give the worker the lead's controller ID as delegated authority.

## Style

State repository conventions relevant to this assignment.

## Deliverable

Name report-N.md and its required content: changes, tests actually run and results,
remaining limits, responses by finding ID, and exact final `STATUS: done`.

## Amendments

Record only user-approved scope changes, retaining the earlier decision and reason.
