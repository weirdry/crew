# Contributing to Crew

This document defines Crew's branch, commit, review, validation, and release
rules. Contributors can follow the complete workflow from this repository.

## Branch strategy

Crew uses a simplified Gitflow model with linear integration and release history.

| Branch | Role |
| --- | --- |
| `main` | Validated release branch and the source for distribution |
| `dev` | Development and integration branch for the next release; no deployment target |
| Work branches | Isolated feature, fix, refactoring, documentation, test, or maintenance work |

All changes reach `main` through promotion from `dev`. Do not implement changes
directly on `main`, including hotfixes, unless the maintainer explicitly directs
an exception. CI triggers do not redefine branch roles.

When adopting this workflow in an existing checkout with only `main`, initialize
`dev` from the current `main` history. Publishing that branch is a separate
maintainer action. The remote commands below apply only after `origin/dev`
exists; preserve existing history when establishing the branch.

## Direct development or a pull request

Direct commits to `dev` are allowed. They are often appropriate for small fixes,
documentation, and routine maintenance, but are not restricted to those types.

Use a dedicated work branch and pull request when a change is substantial,
risky, benefits from review, or should be discussed independently. Start work
branches from the latest `origin/dev` and target `dev` for integration PRs.

Use descriptive, purpose-based branch names with prefixes such as `feature/`,
`fix/`, `refactoring/`, `docs/`, `test/`, or `chore/`. For example,
`fix/partner-ownership` describes the work. Keep issue-tracker identifiers in
the PR body rather than branch names or commit subjects.

## Commit messages

Every commit follows Conventional Commits:

```text
type(scope): imperative summary

- Explain the resulting behavior and why it is needed.
- Add relevant details that the diff does not explain.
```

The scope is optional. When present, use a short, lowercase, kebab-case name
such as `crew`, `helpers`, `tests`, or `repo`. Separate the body from the subject
with a blank line; use a body for non-trivial rationale or consequences.

| Type | Use |
| --- | --- |
| `feat` | New user- or consumer-facing capability |
| `fix` | Bug fix |
| `docs` | Documentation-only change |
| `refactor` | Internal restructuring without a behavior change |
| `test` | Test-only change |
| `build` | Build system, dependency, or packaging change |
| `ci` | CI configuration change |
| `chore` | Repository maintenance not covered by another type |
| `perf` | Performance improvement |
| `revert` | Reversion of an earlier commit |

Examples:

```text
docs(repo): define the contribution workflow
fix(helpers): preserve partner ownership during attach
test(crew): cover a changed approval target
```

For an actual breaking contract change, use `!` after the type or scope and
explain the break in a `BREAKING CHANGE:` footer. Classify the affected boundary
using the release rules below; a refactor alone does not establish a released
compatibility obligation. Keep commits focused and independently understandable.

## Development setup and validation

The [README](README.md) describes installation and live-use requirements. The
offline helper suite needs `sh`, `python3`, and the POSIX utilities used by the
helpers. It does not need a Herdr server, network access, or package installation.
See [tests/README.md](tests/README.md) for the fixture model and coverage limits.

Crew currently uses its native shell test entry point. There is no root Just
interface, repository-managed Git hook, or hosted CI workflow. Use the actual
commands below and report local results separately from hosted or live evidence.
If repository-managed hooks are introduced, enable them as documented and do
not bypass them with `git commit --no-verify`.

For every change, inspect the complete diff, including new files, and check
whitespace before committing or handing off:

```sh
git diff --check
git diff --cached --check
```

For helper or test changes, check shell syntax and run the offline suite from
the repository root:

```sh
for crew_script in skills/crew/scripts/*.sh tests/run.sh; do
  sh -n "$crew_script" || exit 1
done
tests/run.sh
```

The suite creates disposable fixtures under `/var/tmp`; its state-root checks
deliberately reject the normal system temporary directory. Use an environment
that permits those fixture writes, and report a sandbox restriction as blocked
validation rather than weakening the checks.

Documentation-only changes need a content, relative-link, and whitespace review.
Run the suite as well when documentation changes a helper's behavioral contract.
Add deterministic regression cases for changed helper behavior. Mutation tests
must target temporary script copies through `tests/run.sh <scripts-directory>`;
never mutate helpers used by installed sessions as a test technique.

Rerun the applicable checks after a rebase and before opening or updating a PR.
The offline suite does not prove live permission-dialog handling, sandbox
isolation, installation, or model-specific behavior. When a change needs live
validation, record the actual Herdr and agent versions, scenario, outcome, and
unverified limits. Use synthetic workspaces and keep real session artifacts local.

## Direct commits to dev

After the remote development branch exists:

```sh
git switch dev
git pull --ff-only origin dev

# Make the scoped change and run the applicable validation above.
git add <changed-paths>
git commit
git push origin dev
```

Stage only the intended change. Do not force-push `dev` or `main`.

## Pull request workflow

1. Fetch the current remote state and create a work branch from `origin/dev`.
2. Make focused changes with Conventional Commits.
3. Rebase onto updated `origin/dev` when necessary and rerun applicable checks.
4. Push the work branch and open a PR targeting `dev`.
5. Complete the repository-local [PR template](.github/pull_request_template.md).
6. Finish review and all applicable required checks before integration.
7. Integrate with rebase merge.

```sh
git fetch origin
git switch -c fix/partner-ownership origin/dev

# Later, on the same work branch, synchronize before review.
git fetch origin
git rebase origin/dev
```

Do not merge `dev` into a work branch. Do not use merge commits or squash merge.
When rewriting an already-pushed work branch, coordinate with its collaborators
and use `--force-with-lease`. This does not permit rewriting shared branch history.
These are contribution rules; they do not establish GitHub branch protection,
required checks, or repository merge settings by themselves.

### Pull request template requirements

- Write the title and body in English. Use a Conventional Commit title.
- Explain the problem and resulting behavior in Summary. State scope and
  non-goals, select change types, and summarize changes by area.
- List actual verification commands and outcomes. Check only completed,
  applicable items. Mark an inapplicable item `N/A` with a short reason or remove
  it. Keep local tests, hosted CI, live agent behavior, and distribution separate.
- Include risks and recovery for behavior changes. Remove that section for
  documentation-only or other changes without runtime or distribution impact.
  A maintenance label does not exempt a change that affects those boundaries.
- Link repository-owned contracts and evidence when useful. Issue trackers and
  conversations supply coordination context, not executable or runtime proof.
- Remove instructional comments and empty placeholders. Rewrite the title and
  body around the final change when its scope changes.

## Promoting dev to main

Promotion is fast-forward-only. Validate the development revision, then advance
`main` without creating a merge commit:

```sh
git switch dev
git pull --ff-only origin dev

# Run the applicable validation above.

git switch main
git pull --ff-only origin main
git merge --ff-only dev
git push origin main

git switch dev
```

If fast-forward promotion fails, stop and resolve the divergence deliberately.
Do not replace `--ff-only` with a merge commit or force push. Promotion identifies
the release source; it does not prove that an existing installation was updated.

## Release boundaries and installed state

Crew is distributed from this Git repository as a skill and helper scripts;
nothing is published to npm. Existing copies and symlink installations are real
consumers. A symlink loads the files in its target checkout immediately, so an
edit, branch switch, pull, or rebase can affect a running session before a commit.
Use an isolated development checkout or worktree when installed sessions may be
using another checkout. A link to `dev` is an explicit local development choice,
not a shared deployment target for the branch.

Treat commits accumulated on `dev` since the last promotion as unreleased unless
concrete evidence shows an installed consumer or retained state depends on them.
Evolve unreleased contracts in place toward the final target. Do not add version
chains, dual readers, migrations, or mixed-version rollout machinery without a
real compatibility obligation. Preserve ordering, identity, idempotency, and
ownership checks for the correctness properties they protect.

Before adding compatibility work, identify the exact old producer or stored
form, the consumer that still needs it, why both cannot move together, any real
coexistence interval, and the condition for removing the compatibility path.
Report missing evidence and seek explicit maintainer direction before expanding
the change into migration or runtime-state handling.

For an externally visible or cross-component contract change, include one of
these lines in the PR description or final handoff:

- `Boundary classification: unreleased — corrected in place.`
- `Boundary classification: released — compatibility required because <specific consumer, stored state, or deployment evidence>.`

Published tags, versions, and artifacts are immutable. Corrections use a new
release identity. Record the source commit when validating or distributing a
skill copy; report installation and live acceptance separately from promotion.

Treat partner receipts, approval records, active-run pointers, and user artifacts
as non-disposable. Do not delete, reset, rewrite, or migrate them to simplify a
development change. Follow the existing validated lifecycle helpers within the
user's authorized scope; ad hoc state cleanup requires explicit authorization.

## Documentation and evidence

The [skill entry](skills/crew/SKILL.md) owns the agent workflow. The
[helper scripts](skills/crew/scripts/) and [tests](tests/README.md) own executable
behavior and repeatable checks. The [README](README.md) owns installation and
the user-facing overview; this document and the local PR template own contribution
rules. Update the affected owners together when behavior changes.

### Agent entry documents

[RULES.md](RULES.md) is the single source of repository-wide agent instructions.
[AGENTS.md](AGENTS.md) directs agents to read it;
[CLAUDE.md](CLAUDE.md) imports it with `@RULES.md`. Keep both entry documents to
one line and maintain shared instructions only in `RULES.md`. Contribution
procedures remain in this document and are referenced from `RULES.md`.

When adopting another agent tool, add its recognized entry document using the
tool's supported reference mechanism. Verify in a fresh session that the agent
loads `RULES.md`; file and link checks alone do not establish runtime loading.

### Maintaining documentation

Distinguish verified implemented behavior, accepted targets, and open questions.
Use dated validation evidence for observations, and record consequential decisions
in repository-owned documentation when needed. Keep diagram source and generated
views together. Prefer Archify for new or substantially revised engineering
diagrams; use Mermaid with a brief reason when tooling or notation requires it.

Use invented synthetic fixtures in Git. Keep real prompts, transcripts, approval
records, screenshots, credentials, and runtime artifacts out of commits and
public checks. Inspect staged paths and contents; ignore rules alone are not
evidence that a change is safe to publish.

Exceptions require explicit maintainer direction and a repository-local record
of their scope, reason, risk, owner, and review or exit condition.
