#!/bin/sh
# Exit statuses:
#   0  The extracted approval was recorded, matched, proposed, or granted.
#   1  The extracted approval did not match or a grant/proposal was refused.
#   2  Wrong arguments or an invalid expected/proposal token.
#   3  The active run or workspace partner ownership receipt was absent or invalid.
#   4  Herdr state or a complete supported approval confirmation could not be read.
#   5  The approval record could not be read or appended safely.

set -u

usage() {
  printf '%s\n' \
    'usage: approval.sh record <worker> | approval.sh check <worker> [--expect-b64 <token> [--grant-b64 <token>]] | approval.sh propose <worker> --root <dir> [--ops create,modify] | approval.sh grant <worker> --proposal <digest>' >&2
  exit 2
}

case "${1-}:$#" in
  record:2|check:2)
    ;;
  check:4)
    [ "$3" = --expect-b64 ] || usage
    ;;
  check:6)
    [ "$3" = --expect-b64 ] && [ "$5" = --grant-b64 ] || usage
    ;;
  propose:4)
    [ "$3" = --root ] || usage
    ;;
  propose:6)
    [ "$3" = --root ] && [ "$5" = --ops ] || usage
    ;;
  grant:4)
    [ "$3" = --proposal ] || usage
    ;;
  *)
    usage
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


SAFE_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
COMMAND_TEMPLATE = "rm -rf -- {path}"
GRANT_OPERATIONS = ("create", "modify")


def fail(message: str, status: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(status)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encoded_json(value: object) -> str:
    return base64.urlsafe_b64encode(canonical_json(value).encode("utf-8")).decode("ascii")


def digest_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_absolute_path(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("/") or value == "/":
        return False
    segments = value.split("/")[1:]
    return bool(segments) and all(
        segment not in {"", ".", ".."} and SAFE_SEGMENT.fullmatch(segment)
        for segment in segments
    )


def resolved_candidate(value: str) -> Path | None:
    if not safe_absolute_path(value):
        return None
    current = Path(value)
    remaining: list[str] = []
    while not os.path.lexists(current):
        remaining.append(current.name)
        parent = current.parent
        if parent == current:
            return None
        current = parent
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if remaining and not resolved.is_dir():
        return None
    for segment in reversed(remaining):
        resolved /= segment
    return resolved


def is_at_or_below(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def valid_root(value: object, cwd: Path, run_dir: Path) -> Path | None:
    if not safe_absolute_path(value):
        return None
    root = Path(value)
    try:
        resolved = root.resolve(strict=True)
        workspace = cwd.resolve(strict=True)
        active_run = run_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if root != resolved or not resolved.is_dir():
        return None
    if is_at_or_below(workspace, resolved):
        # Defense in depth: active_run is below workspace, so the next check subsumes this case.
        return None
    if is_at_or_below(active_run, resolved):
        return None
    return resolved


def path_covered(value: str, root: Path) -> bool:
    candidate = resolved_candidate(value)
    return candidate is not None and is_at_or_below(candidate, root)


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
        if any(not safe_absolute_path(destination) for destination in destinations):
            fail("cannot extract edit approval: destination is not a safe absolute path", 4)
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
        operations = {operations_by_destination[destination] for destination in destinations}
        if operations == {"added"}:
            operation = "create"
        elif operations == {"edited"}:
            operation = "modify"
        else:
            fail("cannot extract edit approval: operation is not a content modification", 4)

        return {
            "kind": "edit",
            "key": {"destinations": destinations, "operation": operation},
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
        key.get("operation") in GRANT_OPERATIONS
        and isinstance(destinations, list)
        and bool(destinations)
        and all(isinstance(destination, str) and safe_absolute_path(destination) for destination in destinations)
        and destinations == sorted(set(destinations))
    )


def parse_operations(value: str) -> list[str] | None:
    operations = value.split(",")
    if not operations or len(operations) != len(set(operations)):
        return None
    if any(operation not in GRANT_OPERATIONS for operation in operations):
        return None
    return [operation for operation in GRANT_OPERATIONS if operation in operations]


def valid_grant_shape(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("kind") == "command":
        return set(value) == {"kind", "root", "template"} and value.get("template") == COMMAND_TEMPLATE
    if value.get("kind") == "edit":
        operations = value.get("operations")
        return (
            set(value) == {"kind", "operations", "root"}
            and isinstance(operations, list)
            and bool(operations)
            and operations == [operation for operation in GRANT_OPERATIONS if operation in operations]
            and len(operations) == len(set(operations))
            and all(operation in GRANT_OPERATIONS for operation in operations)
        )
    return False


def grant_text(grant: dict[str, object]) -> str:
    root = grant["root"]
    if grant["kind"] == "command":
        return (
            f"Allow command dialogs matching `{COMMAND_TEMPLATE}` where `{{path}}` is one safe "
            f"resolved path at or below `{root}`."
        )
    operations = grant["operations"]
    operation_text = " or ".join(operations)
    return (
        f"Allow edit dialogs for {operation_text} where every destination is one safe resolved "
        f"path at or below `{root}`."
    )


def derive_grant(
    approval: dict[str, object], root_value: object, operations: list[str] | None, cwd: Path, run_dir: Path
) -> dict[str, object] | None:
    root = valid_root(root_value, cwd, run_dir)
    if root is None:
        return None
    if approval["kind"] == "command":
        if operations is not None:
            return None
        command = approval["key"]
        assert isinstance(command, str)
        match = re.fullmatch(r"rm -rf -- (?P<path>/[^\n]*)", command)
        if match is None:
            return None
        candidate = match.group("path")
        if not safe_absolute_path(candidate) or not path_covered(candidate, root):
            return None
        return {"kind": "command", "root": str(root), "template": COMMAND_TEMPLATE}

    if operations is None:
        return None
    key = approval["key"]
    assert isinstance(key, dict)
    operation = key["operation"]
    destinations = key["destinations"]
    if operation not in operations or not all(path_covered(destination, root) for destination in destinations):
        return None
    return {"kind": "edit", "operations": operations, "root": str(root)}


def grant_covers(grant: dict[str, object], approval: dict[str, object], cwd: Path, run_dir: Path) -> bool:
    if not valid_grant_shape(grant) or grant.get("kind") != approval.get("kind"):
        return False
    operations = grant.get("operations") if grant["kind"] == "edit" else None
    return derive_grant(approval, grant.get("root"), operations, cwd, run_dir) == grant


def proposal_payload(approval: dict[str, object], grant: dict[str, object]) -> dict[str, object]:
    return {"approval": approval, "grant": grant, "grant_text": grant_text(grant)}


def valid_stored_approval(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"kind", "key"}:
        return False
    key = value.get("key")
    if value.get("kind") == "command":
        return isinstance(key, str) and bool(key)
    if value.get("kind") != "edit" or not isinstance(key, dict) or set(key) != {"destinations", "operation"}:
        return False
    destinations = key.get("destinations")
    return (
        key.get("operation") in GRANT_OPERATIONS
        and isinstance(destinations, list)
        and bool(destinations)
        and all(isinstance(destination, str) and bool(destination) for destination in destinations)
        and destinations == sorted(set(destinations))
    )


def valid_exact_entry(entry: dict[str, object]) -> bool:
    return "entry_type" not in entry and valid_stored_approval(
        {"kind": entry.get("kind"), "key": entry.get("key")}
    )


def append_entry(record_path: Path, entry: dict[str, object]) -> None:
    try:
        with record_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        fail(f"cannot append approval record: {error}", 5)


def read_entries(record_path: Path) -> list[dict[str, object]]:
    if not record_path.exists():
        return []
    entries: list[dict[str, object]] = []
    try:
        for number, line in enumerate(record_path.read_text(encoding="utf-8").splitlines(), 1):
            entry = json.loads(line)
            if not isinstance(entry, dict):
                fail(f"invalid approval record entry at line {number}", 5)
            entry_type = entry.get("entry_type")
            if entry_type is None:
                if not valid_exact_entry(entry):
                    fail(f"invalid approval record entry at line {number}", 5)
            elif entry_type not in {"proposal", "grant"}:
                fail(f"invalid approval record entry at line {number}", 5)
            entries.append(entry)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read approval record: {error}", 5)
    return entries


verb = sys.argv[1]
worker = sys.argv[2]
expected_token = sys.argv[4] if verb == "check" and len(sys.argv) >= 5 else None
grant_token = sys.argv[6] if verb == "check" and len(sys.argv) == 7 else None
root_argument = sys.argv[4] if verb == "propose" else None
ops_argument = sys.argv[6] if verb == "propose" and len(sys.argv) == 7 else None
proposal_digest = sys.argv[4] if verb == "grant" else None

expected = None
if expected_token is not None:
    try:
        expected = json.loads(
            base64.b64decode(expected_token.encode("ascii"), altchars=b"-_", validate=True).decode("utf-8")
        )
        if not valid_approval(expected):
            raise ValueError("token does not contain a typed approval key")
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        fail(f"invalid expected-command token: {error}", 2)

expected_grant = None
if grant_token is not None:
    try:
        expected_grant = json.loads(
            base64.b64decode(grant_token.encode("ascii"), altchars=b"-_", validate=True).decode("utf-8")
        )
        if not valid_grant_shape(expected_grant):
            raise ValueError("token does not contain a set grant")
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        fail(f"invalid grant token: {error}", 2)

if proposal_digest is not None and not re.fullmatch(r"[0-9a-f]{64}", proposal_digest):
    fail("invalid proposal digest", 2)

if ops_argument is not None:
    parsed_operations = parse_operations(ops_argument)
    if parsed_operations is None:
        fail("invalid grant operations", 2)
else:
    parsed_operations = None

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
approval_digest = digest_json(approval)

print(f"approval_kind={approval['kind']}")
print(f"command_sha256={approval_digest}")
print(f"command_b64={encoded_json(approval)}")

if expected_token is not None:
    if approval != expected:
        print("outcome=expected-mismatch")
        raise SystemExit(1)
    if expected_grant is not None:
        if grant_covers(expected_grant, approval, cwd, run_dir):
            print("outcome=expected-grant-match")
            raise SystemExit(0)
        print("outcome=expected-grant-mismatch")
        raise SystemExit(1)
    print("outcome=expected-match")
    raise SystemExit(0)

record_path = run_dir / "approvals.jsonl"
relative_record = record_path.relative_to(cwd)

if verb == "record":
    entry = {"kind": approval["kind"], "key": approval["key"], "sha256": approval_digest}
    append_entry(record_path, entry)
    print(f"approval_record={relative_record}")
    print("outcome=recorded")
    raise SystemExit(0)

if verb == "propose":
    if approval["kind"] == "command" and ops_argument is not None:
        fail("--ops is valid only for an edit grant", 2)
    if approval["kind"] == "edit" and ops_argument is None:
        fail("--ops is required for an edit grant", 2)
    grant = derive_grant(approval, root_argument, parsed_operations, cwd, run_dir)
    if grant is None:
        fail("current approval is not covered by the proposed grant", 1)
    payload = proposal_payload(approval, grant)
    digest = digest_text(payload["grant_text"])
    for existing in read_entries(record_path):
        existing_grant = existing.get("grant")
        if (
            existing.get("entry_type") == "grant"
            and existing_grant == grant
            and existing.get("grant_text") == payload["grant_text"]
            and isinstance(existing_grant, dict)
            and grant_covers(existing_grant, approval, cwd, run_dir)
        ):
            print(f"approval_record={relative_record}")
            print(f"grant_text={payload['grant_text']}")
            print(f"proposal_sha256={digest}")
            print("outcome=already-granted")
            raise SystemExit(0)
    entry = {"entry_type": "proposal", "proposal": payload, "proposal_sha256": digest}
    append_entry(record_path, entry)
    print(f"approval_record={relative_record}")
    print(f"grant_text={payload['grant_text']}")
    print(f"proposal_sha256={digest}")
    print("outcome=proposed")
    raise SystemExit(0)

entries = read_entries(record_path)

if verb == "grant":
    matching: list[dict[str, object]] = []
    for entry in entries:
        if entry.get("entry_type") != "proposal" or entry.get("proposal_sha256") != proposal_digest:
            continue
        payload = entry.get("proposal")
        if not isinstance(payload, dict) or set(payload) != {"approval", "grant", "grant_text"}:
            continue
        stored_approval = payload.get("approval")
        stored_grant = payload.get("grant")
        stored_text = payload.get("grant_text")
        if (
            not valid_approval(stored_approval)
            or not valid_grant_shape(stored_grant)
            or not isinstance(stored_text, str)
            or stored_text != grant_text(stored_grant)
            or digest_text(stored_text) != proposal_digest
        ):
            continue
        matching.append(payload)
    if not matching or any(payload != matching[0] for payload in matching[1:]):
        fail("proposal digest is absent or ambiguous", 1)
    payload = matching[0]
    stored_grant = payload["grant"]
    assert isinstance(stored_grant, dict)
    stored_operations = stored_grant.get("operations") if stored_grant["kind"] == "edit" else None
    recomputed = derive_grant(approval, stored_grant["root"], stored_operations, cwd, run_dir)
    if approval != payload["approval"] or recomputed != stored_grant or proposal_payload(approval, recomputed) != payload:
        fail("proposal does not match the current approval", 1)
    grant_entry = {
        "entry_type": "grant",
        "grant": stored_grant,
        "grant_text": payload["grant_text"],
        "proposal_sha256": proposal_digest,
    }
    append_entry(record_path, grant_entry)
    print(f"approval_record={relative_record}")
    print(f"grant_text={payload['grant_text']}")
    print(f"proposal_sha256={proposal_digest}")
    print("outcome=grant-recorded")
    raise SystemExit(0)

print(f"approval_record={relative_record}")
for entry in entries:
    if valid_exact_entry(entry) and entry["kind"] == approval["kind"] and entry["key"] == approval["key"]:
        print("outcome=match")
        raise SystemExit(0)
for entry in entries:
    if entry.get("entry_type") != "grant":
        continue
    grant = entry.get("grant")
    text = entry.get("grant_text")
    if (
        isinstance(grant, dict)
        and valid_grant_shape(grant)
        and isinstance(text, str)
        and text == grant_text(grant)
        and grant_covers(grant, approval, cwd, run_dir)
    ):
        print(f"matched_grant_text={text}")
        print(f"grant_b64={encoded_json(grant)}")
        print("outcome=grant-match")
        raise SystemExit(0)
print("outcome=no-match")
raise SystemExit(1)
PY
