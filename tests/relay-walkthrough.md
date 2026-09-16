# Synthetic context continuation walkthrough

This scenario exercises the actual helper in a disposable workspace with the
real state-root validator. All task content and records are invented.

Run it from the repository root:

~~~sh
python3 -B tests/relay.py skills/crew/scripts RelayTests.test_summary_then_correction_preserves_continuation_and_originals
~~~

## Scenario and expected outcome

| Step | Record or operation | Observable outcome |
| --- | --- | --- |
| Task | task.md requires UTC timestamps | This user constraint remains a canonical input |
| Worker question | Relay 000001 asks whether local time is acceptable | Its author, recipient, kind, and response to task.md are recorded |
| Lead response | Relay 000002 retains UTC and rejects local time | The response points to 000001 and preserves the reason |
| Optional compaction | The lead publishes a draft through relay 000002 | A summary covers 000001..000002; both originals remain byte-identical |
| Worker correction | Relay 000003 clarifies that only a unit check was reported | Browser verification stays unknown and no completion is claimed |
| Fresh re-entry | read-plan without a cursor | Lists task.md, state.md, the summary through 000002, and relay 000003 |
| Ongoing participant | read-plan --after 1 | Lists canonical task/status plus original relays 000002 and 000003 |

The test reads the listed packet and asserts the UTC constraint, rejected
alternative, unknown browser result, correction, source references, and next
action remain available. Report-1.md is referenced as evidence of the synthetic
unit-check claim; no actual export implementation or browser check runs.

No summary is produced by appending or reading relays. A separate budget test
verifies that an exceeded explicit byte budget only recommends compaction and
that subsequent inspections leave all records unchanged. Further tests cover
successive summaries, changed sources, invalid records, session separation, and
publication collisions.

## Supervision inspection scenario

For a manual review of the skill instructions, suppose a worker publishes a
correction qualifying report-1.md, leaves the report's completion marker in place,
and then blocks on a dialog. Trace the blocked branch in the Supervision loop:
the completed artifact must pass the same relay handoff check as the idle/done
branch. The lead reads the correction before advancing and keeps the phase open
while any resulting work remains pending. A published response does not by itself
establish that the report is corrected. The lead handles the live dialog through
the existing approval rules before prompting a receptive worker to continue.

This is a documentation inspection scenario, not an automated simulation or a
live-agent observation. The phase table, both completion exits, and the relay
contract must agree on this behavior.

## Evidence boundary

This is deterministic file-protocol evidence. The summary is authored as a
fixture; the helper does not generate it. Assertions establish the contents
and paths available to a receiving participant, not a language model's actual
understanding or the general semantic fidelity of summaries. There is no live
Herdr session, agent restart, permission dialog, installation, or distribution
claim in this walkthrough.
