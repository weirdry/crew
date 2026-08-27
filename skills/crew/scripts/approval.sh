#!/bin/sh
# Exit statuses:
#   0  The extracted approval was recorded, matched the run record, or matched --expect-b64.
#   1  The extracted approval was not recorded or did not match --expect-b64.
#   2  Wrong arguments or an invalid expected-command token.
#   3  The active run or workspace partner ownership receipt was absent or invalid.
#   4  Herdr state or a complete supported approval confirmation could not be read.
#   5  The approval record could not be read or appended safely.

set -u

case "${1-}:$#" in
  record:2|check:2)
    ;;
  check:4)
    if [ "$3" != --expect-b64 ]; then
      printf '%s\n' 'usage: approval.sh record <worker> | approval.sh check <worker> [--expect-b64 <token>]' >&2
      exit 2
    fi
    ;;
  *)
    printf '%s\n' 'usage: approval.sh record <worker> | approval.sh check <worker> [--expect-b64 <token>]' >&2
    exit 2
    ;;
esac

python3 - "$@" <<'PY'
from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import json
import os
import re
import subprocess
import sys


def fail(message: str, status: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(status)


def trim_region(lines: list[str], start: int, end: int) -> tuple[int, int]:
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def is_option(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:[❯›>]\s*)?(?:\d+[.):]|(?:yes|no|allow|deny|approve|cancel|continue|proceed)\b)",
            line,
            re.IGNORECASE,
        )
    )


def is_confirmation(line: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:do you want to|would you like to|are you sure|"
            r"allow\b.*\?|approve\b.*\?|run\b.*\?|execute\b.*\?).*$",
            line,
            re.IGNORECASE,
        )
    )


def is_rule(line: str) -> bool:
    value = line.strip()
    return len(value) >= 10 and set(value) <= set("-─━╌═")


def extract_approval(frame: str) -> dict[str, object]:
    lines = frame.splitlines()
    if not lines:
        fail("cannot extract approval: empty visible frame", 4)

    confirmation = None
    option_start = None
    for candidate in range(len(lines) - 1, -1, -1):
        if not is_confirmation(lines[candidate]):
            continue
        options = [index for index in range(candidate + 1, len(lines)) if is_option(lines[index])]
        if len(options) >= 2:
            confirmation = candidate
            option_start = options[0]
            break

    if confirmation is None or option_start is None:
        fail("cannot extract approval: confirmation or option list is absent", 4)

    question = lines[confirmation].strip().lower()

    if "would you like to make the following edits?" in question:
        region_start, region_end = trim_region(lines, confirmation + 1, option_start)
        destinations: list[str] = []
        for line in lines[region_start:region_end]:
            if not line.strip():
                continue
            destination = re.match(r"^\s*Destination:\s*(\S.*)$", line, re.IGNORECASE)
            if destination:
                value = destination.group(1).rstrip()
                if "…" in value or "[truncated]" in value.lower() or "<truncated>" in value.lower():
                    fail("cannot extract edit approval: destination contains a truncation marker", 4)
                destinations.append(value)
                continue
            if re.match(r"^\s*(?:Description|Reason):(?:\s.*)?$", line, re.IGNORECASE):
                continue
            fail("cannot extract edit approval: metadata contains an unbounded continuation row", 4)

        if not destinations:
            fail("cannot extract edit approval: destination metadata is absent", 4)
        destinations = sorted(set(destinations))

        rules = [index for index in range(0, confirmation) if is_rule(lines[index])]
        if not rules:
            fail("cannot extract edit approval: operation boundary is absent", 4)
        action_lines = lines[rules[-1] + 1 : confirmation]
        operations_by_destination: dict[str, str] = {}
        for line in action_lines:
            action = re.match(
                r"^\s*•\s+([A-Za-z]+)\s+(.+?)\s+\([+-]\d+\s+[+-]\d+\)\s*$",
                line,
            )
            if action:
                operations_by_destination[action.group(2).rstrip()] = action.group(1).lower()
                continue
            if re.match(
                r"^\s*•\s+(?:Added|Edited|Deleted|Moved|Renamed|Created|Removed|Updated)\b",
                line,
                re.IGNORECASE,
            ):
                fail("cannot extract edit approval: operation marker is incomplete", 4)

        if not operations_by_destination:
            fail("cannot extract edit approval: operation marker is absent", 4)
        if any(destination not in operations_by_destination for destination in destinations):
            fail("cannot extract edit approval: destination operation marker is absent", 4)
        if any(operations_by_destination[destination] != "edited" for destination in destinations):
            fail("cannot extract edit approval: operation is not a content modification", 4)

        return {
            "kind": "edit",
            "key": {"destinations": destinations, "operation": "modify"},
        }

    command_start = None
    command_end = None

    if "would you like to run the following command?" in question:
        region_start, region_end = trim_region(lines, confirmation + 1, option_start)
        for index in range(region_start, region_end):
            if lines[index].lstrip().startswith("$ "):
                command_start = index
                command_end = region_end
                break
    else:
        rules = [index for index in range(0, confirmation) if is_rule(lines[index])]
        if len(rules) >= 2:
            region_start, region_end = trim_region(lines, rules[-2] + 1, rules[-1])
            headers = [
                index
                for index in range(region_start, region_end)
                if lines[index].strip().lower() in {"bash", "bash command", "shell command"}
            ]
            if headers:
                command_start, command_end = trim_region(lines, headers[-1] + 1, region_end)

    if command_start is None or command_end is None or command_start >= command_end:
        fail("cannot extract approval: complete command region is absent", 4)

    command_lines = lines[command_start:command_end]
    if any("…" in line or "[truncated]" in line.lower() or "<truncated>" in line.lower() for line in command_lines):
        fail("cannot extract approval: command region contains a truncation marker", 4)

    if command_lines[0].lstrip().startswith("$ "):
        prefix = len(command_lines[0]) - len(command_lines[0].lstrip())
        command_lines[0] = command_lines[0][prefix + 2 :]

    rendered = "\n".join(line.rstrip() for line in command_lines)
    if not rendered:
        fail("cannot extract approval: command region is empty", 4)
    return {"kind": "command", "key": rendered}


def valid_approval(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"kind", "key"}:
        return False
    kind = value.get("kind")
    key = value.get("key")
    if kind == "command":
        return isinstance(key, str) and bool(key)
    if kind != "edit" or not isinstance(key, dict) or set(key) != {"destinations", "operation"}:
        return False
    destinations = key.get("destinations")
    return (
        key.get("operation") == "modify"
        and isinstance(destinations, list)
        and bool(destinations)
        and all(isinstance(destination, str) and bool(destination) for destination in destinations)
        and destinations == sorted(set(destinations))
    )


verb = sys.argv[1]
worker = sys.argv[2]
expected_token = sys.argv[4] if len(sys.argv) == 5 else None
expected = None
if expected_token is not None:
    try:
        expected_text = base64.b64decode(
            expected_token.encode("ascii"), altchars=b"-_", validate=True
        ).decode("utf-8")
        expected = json.loads(expected_text)
        if not valid_approval(expected):
            raise ValueError("token does not contain a typed approval key")
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        fail(f"invalid expected-command token: {error}", 2)

cwd = Path.cwd()
current_path = cwd / ".crew" / ".current"
try:
    current_lines = current_path.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeError) as error:
    fail(f"cannot read active run: {error}", 3)
if len(current_lines) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", current_lines[0]):
    fail("invalid .crew/.current", 3)

run_id = current_lines[0]
run_dir = cwd / ".crew" / run_id
receipt_path = cwd / ".crew" / "worker.json"
try:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    fail(f"cannot read workspace partner ownership receipt: {error}", 3)
if (
    not isinstance(receipt, dict)
    or receipt.get("version") != 1
    or receipt.get("worker_name") != worker
    or not isinstance(receipt.get("worker_pane_id"), str)
    or not receipt["worker_pane_id"]
):
    fail("worker does not match the workspace partner ownership receipt", 3)

try:
    agent_result = subprocess.run(
        ["herdr", "agent", "get", worker],
        check=False,
        capture_output=True,
        text=True,
    )
except (OSError, UnicodeError) as error:
    fail(f"cannot read worker state: {error}", 4)
if agent_result.returncode != 0:
    fail("cannot read worker state", 4)
try:
    agent = json.loads(agent_result.stdout)["result"]["agent"]
except (json.JSONDecodeError, KeyError, TypeError) as error:
    fail(f"invalid worker state: {error}", 4)
if agent.get("pane_id") != receipt["worker_pane_id"] or agent.get("agent_status") != "blocked":
    fail("cannot extract approval: workspace partner is not blocked in its recorded pane", 4)

try:
    read_result = subprocess.run(
        ["herdr", "agent", "read", worker, "--source", "visible", "--lines", "200", "--format", "text"],
        check=False,
        capture_output=True,
        text=True,
    )
except (OSError, UnicodeError) as error:
    fail(f"cannot read visible frame: {error}", 4)
if read_result.returncode != 0:
    fail("cannot read visible frame", 4)

approval = extract_approval(read_result.stdout)
canonical = json.dumps(approval, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
encoded = base64.urlsafe_b64encode(canonical.encode("utf-8")).decode("ascii")
digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

print(f"approval_kind={approval['kind']}")
print(f"command_sha256={digest}")
print(f"command_b64={encoded}")

if expected_token is not None:
    if approval == expected:
        print("outcome=expected-match")
        raise SystemExit(0)
    print("outcome=expected-mismatch")
    raise SystemExit(1)

record_path = run_dir / "approvals.jsonl"
relative_record = record_path.relative_to(cwd)

if verb == "record":
    entry = {"kind": approval["kind"], "key": approval["key"], "sha256": digest}
    try:
        with record_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        fail(f"cannot append approval record: {error}", 5)
    print(f"approval_record={relative_record}")
    print("outcome=recorded")
    raise SystemExit(0)

entries: list[dict[str, object]] = []
if record_path.exists():
    try:
        for number, line in enumerate(record_path.read_text(encoding="utf-8").splitlines(), 1):
            entry = json.loads(line)
            if not isinstance(entry, dict) or not valid_approval(
                {"kind": entry.get("kind"), "key": entry.get("key")}
            ):
                fail(f"invalid approval record entry at line {number}", 5)
            entries.append(entry)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read approval record: {error}", 5)

print(f"approval_record={relative_record}")
if any(entry["kind"] == approval["kind"] and entry["key"] == approval["key"] for entry in entries):
    print("outcome=match")
    raise SystemExit(0)
print("outcome=no-match")
raise SystemExit(1)
PY
