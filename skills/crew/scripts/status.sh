#!/bin/sh
# Exit statuses:
#   0  Help or a snapshot without attention was printed; never a run verdict.
#   1  The snapshot was printed with missing, inconsistent, or unavailable evidence.
#   2  Invalid arguments.

set -u

case "$#:${1-}" in
  0:|1:--json) ;;
  1:--help)
    printf '%s\n' 'usage: status.sh [--json | --help]'
    exit 0
    ;;
  *)
    printf '%s\n' 'usage: status.sh [--json | --help]' >&2
    exit 2
    ;;
esac

script_dir=${0%/*}
[ "$script_dir" != "$0" ] || script_dir=.

python3 - "$script_dir" "${1-}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import subprocess
import sys


helpers = Path(sys.argv[1]).resolve()
snapshot = {
    "workspace": None,
    "state_root": None,
    "run": {"availability": "unavailable", "id": None, "phase": None, "round": None},
    "partner": {"record": "unavailable", "name": None, "kind": None, "pane_id": None,
                "lead_pane_id": None, "observation": "not-queried", "agent_status": None},
    "artifacts": {"latest_report": None, "latest_completed_report": None, "latest_review": None},
    "attention": [],
}


def attention(code: str, message: str, next_check: str) -> None:
    snapshot["attention"].append({"code": code, "message": message, "next_check": next_check})


def read_file(path: Path) -> tuple[str, str | None]:
    """Read regular UTF-8 records only; never follow a record symlink or print its contents."""
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return "unavailable", None
        return "present", path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "absent", None
    except (OSError, UnicodeError):
        return "unavailable", None


def directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def prose(text: str) -> list[str]:
    """Keep standalone evidence lines outside fenced code and HTML comments."""
    lines = []
    fence = None
    comment = False
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if (
                marker and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence) and not marker[2].strip()
            ):
                fence = None
            continue
        if not comment and marker:
            fence = marker[1]
            continue
        # Do not join text around a comment into a new metadata or verdict line.
        commented_line = comment
        remaining = line
        while remaining:
            if comment:
                _, end, remaining = remaining.partition("-->")
                if not end:
                    break
                comment = False
            else:
                token = re.search(r"<!--|`+", remaining)
                if not token:
                    break
                remaining = remaining[token.end():]
                if token[0] == "<!--":
                    comment = commented_line = True
                else:
                    # A literal comment opener in an inline code span is harmless.
                    end = re.search(r"(?<!`)" + re.escape(token[0]) + r"(?!`)", remaining)
                    if end:
                        remaining = remaining[end.end():]
        if not commented_line:
            lines.append(line)
    return lines


def field(lines: list[str], name: str, pattern: str) -> str | None:
    candidates = [line for line in lines if re.match(rf"^- {name}:", line)]
    match = (
        re.fullmatch(rf"- {name}:\s*({pattern})(?:\s+[-—].*)?\s*", candidates[0])
        if len(candidates) == 1 else None
    )
    return match[1] if match else None


def read_run(state_root: Path, cwd: Path) -> tuple[Path | None, list[str]]:
    availability, pointer = read_file(state_root / ".current")
    run = snapshot["run"]
    run["availability"] = availability
    if availability == "absent":
        return None, []
    if availability != "present" or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\n?", pointer or ""
    ):
        run["availability"] = "unavailable"
        attention(
            "run-pointer-unavailable",
            "The active-run pointer is unreadable or invalid.",
            "Inspect the external .current record; do not replace it automatically.",
        )
        return None, []
    run["id"] = pointer.rstrip("\n")
    run_dir = cwd / ".crew" / run["id"]
    if not directory(cwd / ".crew") or not directory(run_dir):
        attention(
            "run-directory-unavailable",
            "The active run directory is missing or unsafe to inspect.",
            "Check the working directory and the recorded run directory.",
        )
        return None, []
    availability, text = read_file(run_dir / "state.md")
    if availability != "present":
        attention(
            "run-state-unavailable",
            "The active run has no readable state.md.",
            "Inspect the run artifacts before deciding its phase or round.",
        )
        return run_dir, []
    lines = prose(text)
    phase = field(lines, "Phase", r"[0-6]|Finishing")
    round_value = field(lines, "Round", r"[0-3] of 3")
    run["phase"] = int(phase) if phase and phase.isdecimal() else phase
    run["round"] = int(round_value[0]) if round_value else None
    if phase is None or round_value is None:
        attention(
            "run-progress-unknown",
            "The recorded phase or round is missing, ambiguous, or unsupported.",
            "Read state.md and the phase rules; the summary does not infer progress from prose.",
        )
    elif phase != "Finishing":
        allowed_rounds = {0: (0,), 1: (0,), 2: (1,), 3: (1,), 4: (1,), 5: (2, 3), 6: (2, 3)}
        if run["round"] not in allowed_rounds[run["phase"]]:
            attention(
                "run-progress-inconsistent",
                "The recorded phase and round contradict the run protocol.",
                'Check state.md: phases 0-1 precede round 1, phases 2-4 use round 1, and phases '
                '5-6 use rounds 2-3.',
            )
    return run_dir, lines


def read_partner(state_root: Path, state_lines: list[str]) -> None:
    partner = snapshot["partner"]
    availability, text = read_file(state_root / "worker.json")
    partner["record"] = availability
    if availability == "absent":
        if snapshot["run"]["phase"] not in (None, 0, "Finishing"):
            attention(
                "partner-record-absent",
                "The recorded phase has no partner receipt.",
                "Check the run notes and external worker.json before contacting a worker.",
            )
        return
    try:
        receipt = json.loads(text) if availability == "present" else None
        identity = ("worker_name", "worker_kind", "worker_pane_id", "lead_pane_id")
        valid = (isinstance(receipt, dict) and receipt.get("version") == 1
                 and all(
                     isinstance(receipt.get(key), str)
                     and re.fullmatch(r"[A-Za-z0-9_-]+", receipt[key]) for key in identity
                 )
                 and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", receipt["worker_name"]))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        partner["record"] = "unavailable"
        attention(
            "partner-record-unavailable",
            "The partner receipt is unreadable or invalid.",
            "Inspect external worker.json; do not infer an identity from pane position.",
        )
        return
    partner.update({"name": receipt["worker_name"], "kind": receipt["worker_kind"],
                    "pane_id": receipt["worker_pane_id"], "lead_pane_id": receipt["lead_pane_id"]})
    for label, key in (("Worker", "name"), ("Pane", "pane_id")):
        recorded = field(state_lines, label, r"[A-Za-z0-9_-]+")
        if recorded and recorded != "none" and recorded != partner[key]:
            attention(
                "run-partner-mismatch",
                f"The recorded {label.lower()} disagrees with the partner receipt.",
                "Compare state.md with worker.json before resuming work.",
            )
    partner["observation"] = "unavailable"
    try:
        result = subprocess.run(
            ["herdr", "agent", "get", partner["name"]],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode:
            for output in (result.stdout, result.stderr):
                try:
                    payload = json.loads(output)
                except ValueError:
                    continue
                if (
                    isinstance(payload, dict) and isinstance(payload.get("error"), dict)
                    and payload["error"].get("code") == "agent_not_found"
                ):
                    partner["observation"] = "absent"
                    attention(
                        "partner-absent",
                        "The recorded partner is not present in Herdr.",
                        'Check the recorded pane and run artifacts; absence does not authorize '
                        'replacement or retirement.',
                    )
                    return
            raise ValueError("unavailable")
        agent = json.loads(result.stdout)["result"]["agent"]
        if not isinstance(agent, dict):
            raise ValueError("invalid response")
        if any(
            agent.get(source) != partner[target]
            for source, target in (("name", "name"), ("agent", "kind"), ("pane_id", "pane_id"))
        ):
            partner["observation"] = "mismatch"
            attention(
                "live-partner-mismatch",
                "The live identity does not match the recorded partner.",
                "Verify the recorded name, kind, and pane before taking any action.",
            )
            return
        status = agent.get("agent_status")
        if status not in ("working", "blocked", "idle", "done", "unknown"):
            raise ValueError("unsupported state")
        partner.update({"observation": "live", "agent_status": status})
        if status in ("blocked", "unknown"):
            attention(
                "worker-" + status,
                "The worker reports " + status + ".",
                'Inspect the worker directly and follow the supervision rules; status inspection '
                'sends no input.',
            )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        attention(
            "herdr-unavailable",
            "The partner state could not be verified through Herdr.",
            "Check Herdr availability and repeat the read-only inspection.",
        )


def read_artifacts(run_dir: Path) -> None:
    artifacts = snapshot["artifacts"]
    reports = {}
    # The existing run protocol has exactly three rounds; no historical run inventory is needed.
    for round_number in range(1, 4):
        for kind in ("report", "review"):
            filename = f"{kind}-{round_number}.md"
            path = run_dir / filename
            availability, text = read_file(path)
            if availability == "absent":
                continue
            entry = {"path": f".crew/{run_dir.name}/{filename}", "round": round_number,
                     "availability": availability}
            if kind == "report":
                entry.update({"complete": None, "self_review_complete": None})
            else:
                entry["verdict"] = None
            artifacts["latest_" + kind] = entry
            if availability != "present":
                attention(
                    "artifact-unavailable",
                    f"{filename} is unreadable or unsafe to inspect.",
                    "Inspect the named artifact; its contents are not included in this summary.",
                )
                continue
            lines = prose(text)
            if kind == "report":
                try:
                    result = subprocess.run(
                        [str(helpers / "artifact-done.sh"), str(path)],
                        capture_output=True, timeout=5,
                    )
                    if result.returncode not in (0, 1):
                        raise ValueError("artifact check failed")
                    entry["complete"] = result.returncode == 0
                    entry["self_review_complete"] = entry["complete"] and any(
                        line.rstrip() == "## Phase 3 self-review" for line in lines
                    )
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    attention(
                        "artifact-check-unavailable",
                        f"The completion check for {filename} failed.",
                        'Check artifact-done.sh and the report; do not infer completion from '
                        'worker state.',
                    )
                reports[round_number] = entry
                if entry["complete"]:
                    artifacts["latest_completed_report"] = entry
            else:
                # Interpret explicit verdict lines, excluding findings and quoted examples.
                verdicts = []
                for line in lines:
                    explicit = line.replace("**", "").replace("`", "").rstrip()
                    match = re.fullmatch(
                        r"(?:- )?(?:Verdict:\s*)?(approve-with-nits|approve|block)", explicit
                    )
                    if match:
                        verdicts.append(match[1])
                if len(verdicts) == 1:
                    entry["verdict"] = verdicts[0]
                else:
                    attention(
                        "review-verdict-unknown",
                        f"{filename} has no single explicit verdict line.",
                        'Read the review; the summary does not infer a verdict from findings or '
                        'prose.',
                    )
    run = snapshot["run"]
    phase, round_number = run["phase"], run["round"]
    if phase == 3:
        report = reports.get(round_number)
        if not report or not report["self_review_complete"]:
            attention(
                "self-review-unconfirmed",
                "The current round has no completed phase-3 self-review evidence.",
                "Check its report for the self-review heading and final STATUS: done line.",
            )
    elif phase in (4, 6) or (
        phase in (2, 5) and snapshot["partner"]["agent_status"] in ("idle", "done")
    ):
        report = reports.get(round_number)
        if not report or not report["complete"]:
            attention(
                "report-unconfirmed",
                "The recorded phase requires a completed current-round report, "
                "but none is confirmed.",
                "Inspect the expected report and follow the existing missing-artifact rule.",
            )
    review = artifacts["latest_review"]
    if review and review["verdict"] == "block":
        attention(
            "review-block",
            f"Review round {review['round']} records block.",
            "Compare that review with the recorded phase and round; "
            "it may be an earlier rework request.",
        )


def inspect() -> None:
    try:
        result = subprocess.run(
            [str(helpers / "state-root.sh")], capture_output=True, text=True, timeout=5,
        )
        if result.returncode:
            raise ValueError("invalid root")
        state = json.loads(result.stdout)
        cwd, state_root = Path(state["cwd"]), Path(state["state_root"])
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        attention(
            "state-root-unavailable",
            "The workspace or external state root failed validation.",
            "Check the working directory and CREW_STATE_DIR using state-root.sh.",
        )
        return
    snapshot.update({"workspace": str(cwd), "state_root": str(state_root)})
    run_dir, state_lines = read_run(state_root, cwd)
    read_partner(state_root, state_lines)
    if run_dir:
        read_artifacts(run_dir)


def shown(value: object) -> str:
    return "unknown" if value is None else str(value)


inspect()
if sys.argv[2] == "--json":
    print(json.dumps(snapshot, sort_keys=True))
else:
    run, partner, artifacts = snapshot["run"], snapshot["partner"], snapshot["artifacts"]
    print("Crew status (read-only snapshot)")
    print("Workspace:", shown(snapshot["workspace"]))
    print("State root:", shown(snapshot["state_root"]))
    print("Run:", "none" if run["availability"] == "absent" else shown(run["id"]))
    print("Run pointer:", run["availability"])
    print(f"Recorded progress: phase {shown(run['phase'])}; round {shown(run['round'])} of 3")
    print(
        f"Partner record: {partner['record']}; {shown(partner['name'])} "
        f"({shown(partner['kind'])}), pane {shown(partner['pane_id'])}"
    )
    print("Recorded lead pane:", shown(partner["lead_pane_id"]))
    print(
        f"Live observation: {partner['observation']}; "
        f"agent status {shown(partner['agent_status'])}"
    )
    for label, key in (
        ("Latest report", "latest_report"),
        ("Latest completed report", "latest_completed_report"),
        ("Latest review", "latest_review"),
    ):
        item = artifacts[key]
        if item is None:
            print(label + ": none observed")
        elif key == "latest_review":
            print(f"{label}: {item['path']}; verdict {shown(item['verdict'])}")
        else:
            print(
                f"{label}: {item['path']}; complete {shown(item['complete'])}; "
                f"self-review complete {shown(item['self_review_complete'])}"
            )
    for item in snapshot["attention"]:
        print(f"Attention [{item['code']}]: {item['message']}")
        print("  Next check:", item["next_check"])
    if not snapshot["attention"]:
        print("Attention: none observed. This snapshot is not a completion verdict.")
raise SystemExit(1 if snapshot["attention"] else 0)
PY
