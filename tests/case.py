#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


class CaseFailure(Exception):
    pass


def replace(value: Any, values: dict[str, str]) -> Any:
    if isinstance(value, str):
        for key, replacement in values.items():
            value = value.replace("{" + key + "}", replacement)
        return value
    if isinstance(value, list):
        return [replace(item, values) for item in value]
    if isinstance(value, dict):
        return {replace(key, values): replace(item, values) for key, item in value.items()}
    return value


def file_content(spec: Any) -> bytes:
    if isinstance(spec, str):
        return spec.encode("utf-8")
    if isinstance(spec, dict) and set(spec) == {"json"}:
        return (json.dumps(spec["json"], sort_keys=True) + "\n").encode("utf-8")
    if isinstance(spec, dict) and set(spec) == {"base64"}:
        return base64.b64decode(spec["base64"])
    raise CaseFailure(f"invalid file specification: {spec!r}")


def write_setup(workspace: Path, setup: dict[str, Any]) -> None:
    for relative in setup.get("dirs", []):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    for relative, content in setup.get("files", {}).items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_content(content))
    for relative, target in setup.get("symlinks", {}).items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
    for relative, mode in setup.get("modes", {}).items():
        (workspace / relative).chmod(int(mode, 8))


def read_calls(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    calls = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            call = json.loads(line)
        except json.JSONDecodeError as error:
            raise CaseFailure(f"invalid call log line {number}: {error}") from error
        if not isinstance(call, list) or not all(isinstance(item, str) for item in call):
            raise CaseFailure(f"invalid call log line {number}")
        calls.append(call)
    return calls


def check_contains(label: str, actual: str, expected: list[str]) -> None:
    for fragment in expected:
        if fragment not in actual:
            raise CaseFailure(f"{label} missing {fragment!r}")


def check_calls(calls: list[list[str]], expected: dict[str, Any]) -> None:
    call_keys = {"calls_exact", "calls_contains", "calls_absent_prefix", "call_counts"}
    if not call_keys.intersection(expected):
        raise CaseFailure("case has no call-log assertion")
    if "calls_exact" in expected and calls != expected["calls_exact"]:
        raise CaseFailure(f"calls differ: {calls!r}")
    for call in expected.get("calls_contains", []):
        if call not in calls:
            raise CaseFailure(f"call missing: {call!r}")
    for prefix in expected.get("calls_absent_prefix", []):
        if any(call[: len(prefix)] == prefix for call in calls):
            raise CaseFailure(f"forbidden call prefix present: {prefix!r}")
    for count_spec in expected.get("call_counts", []):
        argv = count_spec["argv"]
        count = sum(call == argv for call in calls)
        if "count" in count_spec and count != count_spec["count"]:
            raise CaseFailure(f"call count for {argv!r} was {count}")
        if "min" in count_spec and count < count_spec["min"]:
            raise CaseFailure(f"call count for {argv!r} was below {count_spec['min']}")
        if "max" in count_spec and count > count_spec["max"]:
            raise CaseFailure(f"call count for {argv!r} was above {count_spec['max']}")


def check_response_use(fixture: dict[str, Any], state_path: Path) -> None:
    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    for response in fixture.get("responses", []):
        if response.get("optional", False):
            continue
        key = json.dumps(response["argv"], ensure_ascii=False, separators=(",", ":"))
        count = state.get(key, 0)
        if count < len(response["results"]):
            raise CaseFailure(f"unused declared response for {response['argv']!r}")


def check_files(workspace: Path, expected: dict[str, Any]) -> None:
    for relative, content in expected.get("files", {}).items():
        path = workspace / relative
        if not path.is_file():
            raise CaseFailure(f"expected file missing: {relative}")
        wanted = file_content(content)
        if path.read_bytes() != wanted:
            raise CaseFailure(f"file content differs: {relative}")
    for relative, wanted in expected.get("json_files", {}).items():
        path = workspace / relative
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CaseFailure(f"cannot read JSON file {relative}: {error}") from error
        if actual != wanted:
            raise CaseFailure(f"JSON content differs: {relative}")
    for relative in expected.get("absent", []):
        if os.path.lexists(workspace / relative):
            raise CaseFailure(f"path should be absent: {relative}")


def restore_permissions(root: Path) -> None:
    for directory, directories, _ in os.walk(root):
        Path(directory).chmod(stat.S_IRWXU)
        for name in directories:
            (Path(directory) / name).chmod(stat.S_IRWXU)


def run_case(scripts_dir: Path, case_path: Path) -> str:
    raw = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = raw.get("id", case_path.stem)
    temporary = Path(tempfile.mkdtemp(prefix=f"crew-test-{case_id}-", dir="/var/tmp"))
    try:
        workspace = temporary / raw.get("workspace_basename", "workspace")
        workspace.mkdir(parents=True)
        normalized = re.sub(r"[^a-z0-9]+", "-", workspace.name.lower()).strip("-") or "workspace"
        normalized = normalized[:14].rstrip("-_") or "workspace"
        digest = hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()[:12]
        workspace_key = f"{normalized}-{digest}"
        state = (temporary / "state" / workspace_key).resolve(strict=False)
        command = raw.get("command", "")
        values = {
            "cwd": str(workspace.resolve()),
            "derived_name": f"crew-{workspace_key}",
            "state": str(state),
            "command_b64": base64.urlsafe_b64encode(command.encode("utf-8")).decode("ascii"),
            "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        }
        case = replace(raw, values)
        setup = case.get("setup", {})
        write_setup(workspace, setup)

        fixture = {"responses": case.get("herdr", [])}
        fixture_path = temporary / "herdr-fixture.json"
        fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
        call_log = temporary / "herdr-calls.jsonl"
        state_path = temporary / "herdr-state.json"

        script = scripts_dir / case["script"]
        if not script.is_file():
            raise CaseFailure(f"script is absent: {script}")

        environment = os.environ.copy()
        environment["CREW_STATE_DIR"] = str(state.parent)
        environment.update(case.get("env", {}))
        environment["PATH"] = str(Path(__file__).parent / "bin") + os.pathsep + environment.get("PATH", "")
        environment["HERDR_STUB_FIXTURE"] = str(fixture_path)
        environment["HERDR_STUB_CALL_LOG"] = str(call_log)
        environment["HERDR_STUB_STATE"] = str(state_path)
        completed = subprocess.run(
            [str(script), *case.get("args", [])],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=case.get("timeout", 15),
            check=False,
        )

        expected = case["expect"]
        if completed.returncode != expected["status"]:
            raise CaseFailure(
                f"status {completed.returncode}, expected {expected['status']}; "
                f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
            )
        check_contains("stdout", completed.stdout, expected.get("stdout_contains", []))
        check_contains("stderr", completed.stderr, expected.get("stderr_contains", []))
        for pattern in expected.get("stdout_regex", []):
            if re.search(pattern, completed.stdout, re.MULTILINE) is None:
                raise CaseFailure(f"stdout did not match {pattern!r}")
        for pattern in expected.get("stderr_regex", []):
            if re.search(pattern, completed.stderr, re.MULTILINE) is None:
                raise CaseFailure(f"stderr did not match {pattern!r}")
        calls = read_calls(call_log)
        check_calls(calls, expected)
        check_response_use(fixture, state_path)
        check_files(workspace, expected)
        return case_id
    finally:
        restore_permissions(temporary)
        shutil.rmtree(temporary)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: case.py <scripts-directory> <case.json>", file=sys.stderr)
        return 2
    case_path = Path(sys.argv[2])
    fallback_id = case_path.stem
    try:
        case_id = run_case(Path(sys.argv[1]).resolve(), case_path)
    except (CaseFailure, json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as error:
        message = " ".join(str(error).splitlines())
        print(f"FAIL {fallback_id}: {message}")
        return 1
    print(f"PASS {case_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
