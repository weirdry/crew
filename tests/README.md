# Helper script tests

Run the suite from the repository root:

```sh
tests/run.sh
```

The optional argument selects another directory containing the scripts under test. A normal run
defaults to `skills/crew/scripts/`; the alternate directory is used for mutation testing against
temporary copies without changing the installed helpers.

Each JSON file in `tests/cases/` is one case. The runner creates a separate temporary workspace,
writes only the files declared by that case, prepends `tests/bin/` to the existing `PATH`, invokes
the named helper, and checks its status, output, files, and recorded Herdr calls. Temporary
workspaces are removed after each case, including failures.

The `herdr` stub matches the complete subcommand and arguments. A fixture declares ordered
results for repeated identical calls and may attach a deterministic local-file side effect to a
specific result; undeclared calls and exhausted results fail. Every invocation is appended to a
per-case JSON-lines call log, which cases use to pin exact targets and forbidden operations.

Prerequisites are `sh`, `python3`, and the POSIX utilities already used by the production helpers,
including `dirname`. No Herdr server, network access, package installation, or test framework is
needed.

The suite covers `worker-start.sh`, `worker-stop.sh`, `answer-dialog.sh`, `approval.sh`,
`run-finish.sh`, and `artifact-done.sh`. `run-init.sh` is deliberately not covered by this suite.
The Claude-layout approval frame is synthetic and does not verify the branch against a live
Claude permission dialog.
