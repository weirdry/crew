# Working in Crew

This file is the single source of repository-wide agent instructions. Maintain
shared rules here; keep tool-specific entry documents as references to this file.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before substantive repository changes.
Use the repository-local [PR template](.github/pull_request_template.md) when
opening or substantially updating a pull request.

- Follow the documented `dev` integration and fast-forward `main` promotion flow.
- Manage Crew project development and maintenance through GitHub Issues. Follow
  the [issue workflow](CONTRIBUTING.md#issue-management) and use the repository-local
  [work template](.github/ISSUE_TEMPLATE/work.md) when creating or updating issues.
- Write repository documentation, commit messages, issues, pull requests, comments,
  and status updates in English, following the
  [working language policy](CONTRIBUTING.md#working-language).
- Read the affected skill instructions, helpers, and test documentation together.
- Preserve lead authority, partner ownership, approval identity, and lifecycle
  checks when changing the collaboration protocol.
- Protect active symlink installations; use isolated copies for mutation tests.
- Keep local tests, hosted CI, live agent behavior, and distribution evidence
  distinct. Record what remains unverified.
- Classify compatibility needs using actual installed consumers and stored state.
  Preserve correctness invariants and avoid speculative compatibility layers.
- Keep real session data and runtime state out of Git. Do not reset or rewrite
  user state as incidental development cleanup.
