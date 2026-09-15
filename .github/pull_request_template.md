<!--
Write the title and body in English. Use a Conventional Commit title, e.g. `fix(helpers): preserve partner ownership`.
Keep tracker identifiers in the history section rather than branch names or commit subjects.
Target dev; prepare independently understandable commits for rebase integration and fast-forward promotion.
Follow CONTRIBUTING.md. Remove instructional comments, empty placeholders, and inapplicable optional sections.
Check only completed, applicable items; mark others N/A with a reason or remove them.
-->

## Summary

<!-- Explain the problem and resulting behavior in one short paragraph. -->

## Scope & non-goals

<!-- State the included work and relevant boundaries. -->

## Type of change

- [ ] Feature (`feat`)
- [ ] Fix (`fix`)
- [ ] Refactor (`refactor`)
- [ ] Performance (`perf`)
- [ ] Chore / build / tooling (`chore`, `build`)
- [ ] CI (`ci`)
- [ ] Docs (`docs`)
- [ ] Tests (`test`)
- [ ] Revert (`revert`)

## What changed

<!-- One bullet per affected area; explain what a reviewer should inspect. -->

-

## Key decisions

<!-- Record significant decisions and their reasons. Omit for a mechanical change. -->

## Verification

<!-- List actual commands and outcomes. For helper changes: shell syntax checks and `tests/run.sh`.
For documentation-only changes: content, relative links, and staged/unstaged whitespace checks.
Keep local tests, hosted CI, live agent behavior, and distribution evidence separate. State unperformed checks.
-->

- [ ] Applicable syntax and whitespace checks pass
- [ ] Offline helper tests pass; changed behavior has deterministic regression coverage
- [ ] Live Herdr / agent behavior verified where affected, with versions and scenario recorded

<details>
<summary>Screenshots / recordings (when relevant)</summary>

<!-- Use synthetic scenarios only. Remove this block when not applicable. -->

</details>

## Risks & rollback

<!-- Remove for documentation-only or other changes without runtime or distribution impact.
For externally visible or cross-component contract changes, include the applicable line and concrete evidence:
Boundary classification: unreleased — corrected in place.
Boundary classification: released — compatibility required because <specific consumer, stored state, or deployment evidence>.
Do not infer migrations or mixed-version rollout work from an unreleased implementation change.
-->

- **Affected failure mode:** <!-- What could fail for a lead, partner, or installed skill? -->
- **Recovery:** <!-- How to recover within the established lifecycle; consider active symlink installations. -->
- **Breaking changes:** none <!-- Or identify the exact affected contract and consumers. -->
- **Stored state / user data:** none <!-- Or describe the impact and any explicitly authorized handling. -->
- **Environment / configuration / permissions:** none <!-- Or describe affected variables, paths, or authority boundaries. -->

## Pre-integration checklist

- [ ] Self-reviewed the complete diff; no leftover debug code or unrelated changes
- [ ] Applicable checks are reproducible from a clean checkout
- [ ] No secrets, private session data, or runtime artifacts committed; fixtures are synthetic
- [ ] README, skill instructions, and helper/test documentation updated where affected
- [ ] Workflow, ownership, approval, lifecycle, or distribution changes include matching documentation and evidence
- [ ] Branch is current with `dev`; commits are ready for rebase integration

## Repository authority and history (optional)

<!-- Link repository-owned contracts, evidence, decisions, and relevant prior PRs or issues.
External planning systems provide coordination context, not authority or runtime evidence.
-->

-
