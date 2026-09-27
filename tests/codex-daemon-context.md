# Codex CLI command-runner context probe

Observed on September 27, 2026 with Codex CLI 0.157.1 on macOS. This probe
uses an invented variable in disposable empty directories; it does not control
Herdr or read Crew runtime state.

An existing shared app-server was running before the probes. Each new CLI was
started with `CREW_CONTEXT_PROBE` set in its launcher environment, then asked to
run `printf 'CREW_CONTEXT_PROBE=%s\n' "${CREW_CONTEXT_PROBE:-<unset>}"`
through its shell tool exactly once.

| New CLI launch | Shell-tool output |
| --- | --- |
| `CREW_CONTEXT_PROBE=daemon_comparison codex` | `CREW_CONTEXT_PROBE=<unset>` |
| `CREW_CONTEXT_PROBE=from_test_terminal codex --no-daemon` | `CREW_CONTEXT_PROBE=from_test_terminal` |

The observed Herdr-pane conversation's command runner also lacked `HERDR_ENV`
and `HERDR_PANE_ID` after `codex resume --no-daemon`; process inspection placed
the runner under the original detached app-server. The synthetic probe confirms
the same loss without relying on Herdr-specific variables. The probe directories
were removed after both CLI sessions exited.

This does not validate a fresh `--no-daemon` launch inside Herdr or establish
that a resumed daemon-owned conversation can move its command runner. A shared
daemon may also retain another client's terminal variables, so the presence of
`HERDR_ENV` alone is not an identity check. The related Codex reports
[openai/codex#44902](https://github.com/openai/codex/issues/44902) and
[openai/codex#48500](https://github.com/openai/codex/issues/48500) concern
hooks; they do not resolve this shell-tool path.

Herdr's [Codex SessionStart hook](https://github.com/herdrdev/herdr/blob/fff6c820aa45f4eabb9b2e0456326dc74cca5a25/src/integration/assets/codex/herdr-agent-state.sh)
also obtains its target `pane_id` from `HERDR_PANE_ID`. Its reported native
session ID cannot independently recover the originating pane when that variable
is absent or inherited from a different client. Crew therefore accepts an
explicitly selected lead pane ID for this case; the helper validates the live
Herdr agent and keeps the selected ID in the partner ownership receipt.
