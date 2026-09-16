"""Local, run-scoped context records. No model calls or Herdr control."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile


RELAY_SECTIONS = ("Message", "Evidence", "Next action")
SUMMARY_SECTIONS = (
    "Goal and constraints", "Decisions and rationale", "Corrections and rejected claims",
    "Open questions and disagreements", "Work and validation", "Next action", "Sources",
)
KINDS = ("request", "question", "response", "result", "correction", "note")
ROLES = ("lead", "worker")


class InvalidRecord(Exception):
    pass


def directory(path: Path) -> None:
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise InvalidRecord(f"not a real directory: {path}")


def checked_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if (
        not relative or parts.is_absolute() or ".." in parts.parts
        or "\\" in relative or str(parts) != relative
        or any(ord(c) < 32 for c in relative)
    ):
        raise InvalidRecord(f"invalid relative file path: {relative!r}")
    path = root
    for part in parts.parts[:-1]:
        path = path / part
        directory(path)
    path = root / relative
    if not stat.S_ISREG(path.lstat().st_mode):
        raise InvalidRecord(f"not a regular file: {path}")
    return path


def session(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise InvalidRecord("invalid run id")
    root = Path.cwd() / ".crew"
    directory(root)
    root = root / run_id
    directory(root)
    checked_file(root, "task.md")
    checked_file(root, "state.md")
    return root


def require_active(root: Path) -> None:
    result = subprocess.run(
        [str(Path(__file__).with_name("state-root.sh"))],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode:
        raise InvalidRecord("state-root.sh could not validate the authority root")
    state = Path(json.loads(result.stdout)["state_root"])
    current = checked_file(state, ".current").read_text(encoding="utf-8")
    if current not in (root.name, root.name + "\n"):
        raise InvalidRecord("requested session is not the active run")


def identifier(number: int) -> str:
    return f"{number:06d}"


def sections(body: str, required: tuple[str, ...]) -> None:
    """Check the readable shape, not the truth or completeness of its claims."""
    found = []
    values: dict[str, list[str]] = {}
    current = None
    fence = None
    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(\x60{3,}|~{3,})(.*)$", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        elif line.startswith("## ") and line[3:] in required:
            current = line[3:]
            found.append(current)
            values[current] = []
            continue
        if current:
            values[current].append(line)
    if fence or found != list(required) or any(not "\n".join(values[h]).strip() for h in required):
        raise InvalidRecord("draft must contain each required section once, in order, with content: "
                            + ", ".join(required))


def draft(root: Path, relative: str, required: tuple[str, ...]) -> str:
    body = checked_file(root, relative).read_bytes().decode("utf-8")
    if "\r" in body or "\x00" in body:
        raise InvalidRecord("draft must be UTF-8 text with LF line endings")
    body = body.rstrip("\n")
    if body.endswith("STATUS: done"):
        body = body[:-len("STATUS: done")].rstrip("\n")
    sections(body, required)
    return body


def encode(title: str, fields: dict[str, str], body: str) -> bytes:
    header = "\n".join(f"- {key}: {value}" for key, value in fields.items())
    return f"# {title}\n\n{header}\n\n{body}\n\nSTATUS: done\n".encode("utf-8")


def decode(root: Path, relative: str, title: str, keys: tuple[str, ...],
           required: tuple[str, ...]) -> tuple[dict[str, str], bytes]:
    raw = checked_file(root, relative).read_bytes()
    text = raw.decode("utf-8")
    if "\r" in text or not text.endswith("\n\nSTATUS: done\n"):
        raise InvalidRecord(f"incomplete record: {relative}")
    try:
        heading, metadata, body = text[:-len("\n\nSTATUS: done\n")].split("\n\n", 2)
    except ValueError as error:
        raise InvalidRecord(f"invalid record: {relative}") from error
    lines = metadata.splitlines()
    if heading != "# " + title or len(lines) != len(keys):
        raise InvalidRecord(f"invalid metadata: {relative}")
    fields = {}
    for key, line in zip(keys, lines):
        prefix = f"- {key}: "
        if not line.startswith(prefix) or not line[len(prefix):]:
            raise InvalidRecord(f"invalid {key}: {relative}")
        fields[key] = line[len(prefix):]
    if fields["Session"] != root.name:
        raise InvalidRecord(f"record belongs to another session: {relative}")
    sections(body, required)
    return fields, raw


def inventory(root: Path, folder: str, prefix: str = "") -> list[int]:
    path = root / folder
    if not os.path.lexists(path):
        return []
    directory(path)
    result = []
    for entry in path.iterdir():
        if entry.name.startswith("."):
            continue
        match = re.fullmatch(re.escape(prefix) + r"([0-9]{6,})\.md", entry.name)
        if not match or match[1] != identifier(int(match[1])) or int(match[1]) < 1:
            raise InvalidRecord(f"unexpected published record: {entry}")
        checked_file(root, f"{folder}/{entry.name}")
        result.append(int(match[1]))
    return sorted(result)


def relays(root: Path) -> list[tuple[dict[str, str], bytes]]:
    ids = inventory(root, "relay")
    if ids != list(range(1, len(ids) + 1)):
        raise InvalidRecord("relay history has a gap")
    records = []
    for number in ids:
        name = f"relay/{identifier(number)}.md"
        fields, raw = decode(
            root, name, f"Crew relay {identifier(number)}",
            ("Session", "Author", "Recipient", "Kind", "Responds to", "Created"),
            RELAY_SECTIONS,
        )
        if fields["Author"] not in ROLES or fields["Recipient"] not in ROLES or fields["Kind"] not in KINDS:
            raise InvalidRecord(f"invalid participant or kind: {name}")
        reply_target(root, fields["Responds to"], number - 1)
        records.append((fields, raw))
    return records


def reply_target(root: Path, relative: str, last: int) -> None:
    if relative == "task.md" or re.fullmatch(r"(?:report|review)-[1-9][0-9]*\.md", relative):
        checked_file(root, relative)
        return
    match = re.fullmatch(r"relay/([0-9]{6,})\.md", relative)
    if match and match[1] == identifier(int(match[1])) and 1 <= int(match[1]) <= last:
        checked_file(root, relative)
        return
    raise InvalidRecord("Responds to must name task.md, a report/review, or an earlier relay in this run")


def source_digest(records: list[tuple[dict[str, str], bytes]], through: int) -> str:
    digest = hashlib.sha256()
    for number, (_, raw) in enumerate(records[:through], 1):
        digest.update(f"{identifier(number)}:{len(raw)}:".encode("ascii"))
        digest.update(raw)
    return digest.hexdigest()


def summary(root: Path, records: list[tuple[dict[str, str], bytes]]) -> tuple[int, str | None]:
    ids = inventory(root, "summaries", "through-")
    if not ids:
        return 0, None
    through = ids[-1]
    name = f"summaries/through-{identifier(through)}.md"
    fields, _ = decode(
        root, name, f"Crew summary through {identifier(through)}",
        ("Session", "Author", "Covers", "Source SHA-256", "Created"), SUMMARY_SECTIONS,
    )
    if (
        fields["Author"] != "lead" or through > len(records)
        or fields["Covers"] != f"000001..{identifier(through)}"
        or fields["Source SHA-256"] != source_digest(records, through)
    ):
        raise InvalidRecord("latest summary has invalid coverage or its source relays changed; "
                            "inspect originals with read-plan --after 0")
    return through, name


def publish(root: Path, relative: str, content: bytes) -> None:
    """Expose a complete record without replacing an existing file."""
    require_active(root)
    parent = (root / relative).parent
    parent.mkdir(exist_ok=True)
    directory(parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".publish-", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        require_active(root)
        os.link(temporary, root / relative)
    finally:
        temporary.unlink(missing_ok=True)


def positive(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return int(value)


def cursor(value: str) -> int:
    if value == "0":
        return 0
    return positive(value)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="relay.sh",
        description="Publish local context records or print a read-only continuation plan. "
                    "Run from the workspace used by run-init.sh. File arguments are run-relative.",
        epilog="Exit 0: success (never a work verdict); 1: invalid/unavailable evidence or "
               "publication failure; 2: invalid CLI arguments. No model or Herdr calls.",
    )
    commands = result.add_subparsers(dest="command", required=True)
    append = commands.add_parser("append", help="publish one completed relay from a Markdown draft")
    append.add_argument("run_id")
    append.add_argument("--author", choices=ROLES, required=True)
    append.add_argument("--to", choices=ROLES, required=True)
    append.add_argument("--kind", choices=KINDS, required=True)
    append.add_argument("--reply-to", required=True)
    append.add_argument("--file", required=True, help="draft path relative to the run directory")
    compact = commands.add_parser("publish-summary", help="publish a lead-authored summary; no LLM invocation")
    compact.add_argument("run_id")
    compact.add_argument("--through", type=positive, required=True)
    compact.add_argument("--file", required=True, help="draft path relative to the run directory")
    plan = commands.add_parser("read-plan", help="list files to read; does not emit their contents or mark them read")
    plan.add_argument("run_id")
    plan.add_argument("--after", type=cursor, help="last relay still understood in this context; 0 selects all originals")
    plan.add_argument("--budget-bytes", type=positive, help="optional continuation UTF-8 byte budget; advisory only")
    plan.add_argument("--json", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        root = session(args.run_id)
        if args.command != "read-plan":
            require_active(root)
        records = relays(root)
        if args.command == "append":
            reply_target(root, args.reply_to, len(records))
            body = draft(root, args.file, RELAY_SECTIONS)
            number = len(records) + 1
            relative = f"relay/{identifier(number)}.md"
            content = encode(f"Crew relay {identifier(number)}", {
                "Session": root.name, "Author": args.author, "Recipient": args.to,
                "Kind": args.kind, "Responds to": args.reply_to,
                "Created": datetime.now(timezone.utc).isoformat(),
            }, body)
            publish(root, relative, content)
            print(f".crew/{root.name}/{relative}")
        elif args.command == "publish-summary":
            if not 1 <= args.through <= len(records):
                raise InvalidRecord("summary coverage must end at an existing relay")
            prior = inventory(root, "summaries", "through-")
            if prior and args.through <= prior[-1]:
                raise InvalidRecord("a new summary must cover additional relays; append a correction relay first")
            body = draft(root, args.file, SUMMARY_SECTIONS)
            relative = f"summaries/through-{identifier(args.through)}.md"
            content = encode(f"Crew summary through {identifier(args.through)}", {
                "Session": root.name, "Author": "lead",
                "Covers": f"000001..{identifier(args.through)}",
                "Source SHA-256": source_digest(records, args.through),
                "Created": datetime.now(timezone.utc).isoformat(),
            }, body)
            publish(root, relative, content)
            print(f".crew/{root.name}/{relative}")
        else:
            after, selected_summary = (args.after, None) if args.after is not None else summary(root, records)
            if after > len(records):
                raise InvalidRecord("read position is beyond this session's history")
            paths = ["task.md", "state.md"]
            if os.path.lexists(root / "dismissed.md"):
                checked_file(root, "dismissed.md")
                paths.append("dismissed.md")
            continuation = ([selected_summary] if selected_summary else []) + [
                f"relay/{identifier(n)}.md" for n in range(after + 1, len(records) + 1)
            ]
            sizes = {path: checked_file(root, path).stat().st_size for path in paths + continuation}
            reading_bytes = sum(sizes[path] for path in continuation)
            if args.after is not None and args.budget_bytes is not None:
                covered, latest = summary(root, records)
                budget_paths = ([latest] if latest else []) + [
                    f"relay/{identifier(n)}.md" for n in range(covered + 1, len(records) + 1)
                ]
                budget_size = sum(checked_file(root, path).stat().st_size for path in budget_paths)
            elif args.after is not None:
                budget_size = None
            else:
                budget_size = reading_bytes
            output = {
                "session": root.name,
                "mode": "incremental" if args.after is not None else "reentry",
                "after": after, "latest_relay": len(records), "summary": selected_summary,
                "files": [{"path": f".crew/{root.name}/{path}", "bytes": sizes[path]}
                          for path in paths + continuation],
                "reading_bytes": reading_bytes,
                "compaction": {
                    "budget_bytes": args.budget_bytes,
                    "continuation_bytes": budget_size,
                    "suggested": None if args.budget_bytes is None else budget_size > args.budget_bytes,
                },
            }
            if args.json:
                print(json.dumps(output, sort_keys=True))
            else:
                print(f"Session: {root.name} ({output['mode']}); latest relay: {identifier(len(records))}")
                for entry in output["files"]:
                    print(f"{entry['path']} ({entry['bytes']} bytes)")
                suggested = output["compaction"]["suggested"]
                print("Compaction: " + ("manual; no budget configured" if suggested is None else
                                      "consider at the next coherent handoff" if suggested else "not suggested"))
                print("Read the listed files and referenced evidence. This plan is not a read receipt or work verdict.")
        return 0
    except (InvalidRecord, OSError, UnicodeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"relay: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
