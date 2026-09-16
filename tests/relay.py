#!/usr/bin/env python3
"""Synthetic sequential continuation and refusal tests for relay.sh."""

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from case import snapshot_tree


SCRIPTS = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "skills/crew/scripts"
)
MESSAGE = """## Message
Should the synthetic export retain UTC? Local time is only a proposal.

## Evidence
task.md requires UTC. This is a question, not approval to change scope.

## Next action
Lead: clarify before the worker changes the export.
"""
ANSWER = """## Message
Retain UTC. The local-time proposal is rejected. The user constraint is unchanged.

## Evidence
task.md and relay/000001.md.

## Next action
Worker: implement UTC output and report actual verification.
"""
CORRECTION = """## Message
Correction: the earlier report overstated validation. Only the UTC unit check ran;
the browser result is still unknown. Do not claim the export is complete.

## Evidence
relay/000002.md; report-1.md records only a unit check.

## Next action
Lead: retain the missing browser verification as unresolved.
"""
SUMMARY = """## Goal and constraints
Export timestamps in UTC as required by task.md.

## Decisions and rationale
Lead retained UTC in relay/000002.md because task.md requires it.

## Corrections and rejected claims
The local-time proposal in relay/000001.md was rejected by relay/000002.md.

## Open questions and disagreements
Browser output has not been checked. It remains unknown.

## Work and validation
Only a synthetic UTC unit check was reported. No browser or live agent validation.

## Next action
Worker must verify the browser result before claiming completion.

## Sources
task.md; relay/000001.md; relay/000002.md; report-1.md.
"""


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="crew-relay-test-", dir="/var/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / ".git").mkdir()
        self.environment = os.environ.copy()
        self.environment["CREW_STATE_DIR"] = str(self.base / "state")
        # Any accidental Herdr call fails and is logged.
        fixture = self.base / "herdr.json"
        fixture.write_text('{"responses": []}\n')
        self.log = self.base / "herdr-calls.jsonl"
        self.environment.update({
            "PATH": str(Path(__file__).parent / "bin") + os.pathsep + self.environment["PATH"],
            "HERDR_STUB_FIXTURE": str(fixture),
            "HERDR_STUB_CALL_LOG": str(self.log),
            "HERDR_STUB_STATE": str(self.base / "herdr-state.json"),
        })
        result = subprocess.run(
            [str(SCRIPTS / "state-root.sh")], cwd=self.workspace, env=self.environment,
            capture_output=True, text=True, check=True,
        )
        self.state = Path(json.loads(result.stdout)["state_root"])
        self.state.mkdir(parents=True)
        (self.state / ".current").write_text("run-1\n")
        self.run = self.make_run("run-1")
        self.run.joinpath("draft.md").write_text(MESSAGE)
        self.run.joinpath("summary-draft.md").write_text(SUMMARY)
        self.run.joinpath("report-1.md").write_text("UTC unit check passed. Browser unverified.\n")
        self.before_authority = snapshot_tree(self.state)

    def tearDown(self):
        self.assertFalse(self.log.exists(), "relay operations must never call Herdr")

    def make_run(self, name):
        run = self.workspace / ".crew" / name
        run.mkdir(parents=True)
        run.joinpath("task.md").write_text("# Task\n\nExport timestamps in UTC.\n")
        run.joinpath("state.md").write_text("# Crew state\n\n- Phase: 2\n- Round: 1 of 3\n")
        return run

    def call(self, *args, status=0, read_only=False):
        before = snapshot_tree(self.workspace), snapshot_tree(self.state)
        result = subprocess.run(
            [str(SCRIPTS / "relay.sh"), *args], cwd=self.workspace, env=self.environment,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        if read_only:
            self.assertEqual(before, (snapshot_tree(self.workspace), snapshot_tree(self.state)))
        return result

    def append(self, body=MESSAGE, reply="task.md", author="worker", kind="question", run="run-1"):
        target = self.workspace / ".crew" / run
        target.joinpath("draft.md").write_text(body)
        result = self.call(
            "append", run, "--author", author, "--to", "lead" if author == "worker" else "worker",
            "--kind", kind, "--reply-to", reply, "--file", "draft.md",
        )
        return self.workspace / result.stdout.strip()

    def two_relays(self):
        first = self.append()
        second = self.append(ANSWER, reply="relay/000001.md", author="lead", kind="response")
        return first, second

    def compact(self, through=2):
        return self.call("publish-summary", "run-1", "--through", str(through), "--file", "summary-draft.md")

    def plan(self, *options, run="run-1"):
        return json.loads(self.call("read-plan", run, "--json", *options, read_only=True).stdout)

    def paths(self, plan):
        return [entry["path"].split("/run-1/")[-1] for entry in plan["files"]]

    def test_exchange_is_sequential_attributable_and_does_not_compact(self):
        first, second = self.two_relays()
        self.assertIn("- Author: worker\n- Recipient: lead\n- Kind: question", first.read_text())
        self.assertIn("- Responds to: relay/000001.md", second.read_text())
        self.assertTrue(second.read_bytes().endswith(b"\n\nSTATUS: done\n"))
        self.assertFalse((self.run / "summaries").exists())
        self.assertEqual(self.before_authority, snapshot_tree(self.state))

    def test_incremental_reading_and_fresh_reentry(self):
        self.two_relays()
        fresh = self.plan()
        increment = self.plan("--after", "1")
        self.assertEqual(self.paths(fresh), ["task.md", "state.md", "relay/000001.md", "relay/000002.md"])
        self.assertEqual(self.paths(increment), ["task.md", "state.md", "relay/000002.md"])
        self.assertEqual(self.paths(self.plan("--after", "2")), ["task.md", "state.md"])
        self.assertEqual(fresh["mode"], "reentry")
        self.assertIsNone(fresh["compaction"]["suggested"])

    def test_summary_then_correction_preserves_continuation_and_originals(self):
        first, second = self.two_relays()
        originals = {p: p.read_bytes() for p in (first, second)}
        self.compact()
        self.append(CORRECTION, reply="relay/000002.md", kind="correction")
        fresh = self.plan()
        self.assertEqual(self.paths(fresh), [
            "task.md", "state.md", "summaries/through-000002.md", "relay/000003.md",
        ])
        packet = "\n".join((self.workspace / item["path"]).read_text() for item in fresh["files"])
        for required in ("UTC", "rejected", "still unknown", "Only", "Next action", "relay/000002.md"):
            self.assertIn(required, packet)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})
        self.assertEqual(self.paths(self.plan("--after", "1")),
                         ["task.md", "state.md", "relay/000002.md", "relay/000003.md"])

    def test_successive_summary_covers_full_prefix_and_preserves_previous(self):
        self.two_relays()
        self.compact()
        previous = (self.run / "summaries/through-000002.md").read_bytes()
        self.append(CORRECTION, reply="relay/000002.md", kind="correction")
        self.run.joinpath("summary-draft.md").write_text(
            SUMMARY.replace("Only a synthetic UTC", "relay/000003.md corrects the validation claim. Only a synthetic UTC")
        )
        self.compact(3)
        self.assertEqual(self.plan()["summary"], "summaries/through-000003.md")
        self.assertIn("- Covers: 000001..000003", (self.run / "summaries/through-000003.md").read_text())
        self.assertEqual(previous, (self.run / "summaries/through-000002.md").read_bytes())
        self.assertEqual(len(list(self.run.glob("relay/*.md"))), 3)

    def test_budget_is_advisory_read_only_and_uses_fresh_packet(self):
        self.two_relays()
        size = self.plan()["reading_bytes"]
        self.assertFalse(self.plan("--budget-bytes", str(size))["compaction"]["suggested"])
        low = self.plan("--after", "2", "--budget-bytes", str(size - 1))
        self.assertEqual(low["reading_bytes"], 0)
        self.assertEqual(low["compaction"]["continuation_bytes"], size)
        self.assertTrue(low["compaction"]["suggested"])
        self.assertFalse((self.run / "summaries").exists())
        self.compact()
        plan = self.plan("--budget-bytes", "1")
        summary_size = (self.run / "summaries/through-000002.md").stat().st_size
        self.assertEqual(plan["compaction"]["continuation_bytes"], summary_size)
        self.assertEqual(len(list(self.run.glob("summaries/*.md"))), 1)

    def test_sessions_remain_separate_and_finished_runs_are_readable(self):
        self.two_relays()
        other = self.make_run("run-2")
        (self.state / ".current").write_text("run-2\n")
        self.append("## Message\nDifferent task.\n## Evidence\ntask.md\n## Next action\nRead task.\n", run="run-2")
        self.assertEqual(self.plan(run="run-2")["latest_relay"], 1)
        self.assertEqual(self.plan()["latest_relay"], 2)
        self.assertFalse((other / "summaries").exists())
        self.call("append", "run-1", "--author", "lead", "--to", "worker", "--kind", "note",
                  "--reply-to", "task.md", "--file", "draft.md", status=1, read_only=True)
        (self.state / ".current").unlink()
        self.assertEqual(self.plan()["latest_relay"], 2)

    def test_future_and_cross_session_replies_are_refused(self):
        self.make_run("run-2")
        for reply in ("relay/000001.md", "../run-2/task.md", ".crew/run-2/task.md", "/etc/passwd"):
            with self.subTest(reply=reply):
                self.call("append", "run-1", "--author", "lead", "--to", "worker", "--kind", "note",
                          "--reply-to", reply, "--file", "draft.md", status=1, read_only=True)
        self.assertFalse((self.run / "relay").exists())

    def test_worker_needs_the_leads_state_setting_for_publication(self):
        self.append()
        configured = self.environment["CREW_STATE_DIR"]
        other_state = self.base / "different-worker-state"
        self.environment["CREW_STATE_DIR"] = str(other_state)
        try:
            result = self.call("append", "run-1", "--author", "worker", "--to", "lead",
                               "--kind", "question", "--reply-to", "task.md", "--file", "draft.md",
                               status=1, read_only=True)
            self.assertIn("active-run pointer not found at", result.stderr)
            self.assertIn(str(other_state), result.stderr)
            self.assertIn("CREW_STATE_DIR", result.stderr)
            self.assertIn("lead", result.stderr)
            self.assertNotIn("[Errno", result.stderr)
            self.assertEqual(self.plan()["latest_relay"], 1)
            self.assertFalse(other_state.exists())
        finally:
            self.environment["CREW_STATE_DIR"] = configured
        self.append()
        self.assertEqual(self.plan()["latest_relay"], 2)
        self.assertEqual(self.before_authority, snapshot_tree(self.state))

    def test_workspace_paths_explain_the_run_relative_argument_contract(self):
        record = self.append()
        printed_path = str(record.relative_to(self.workspace))
        for reply, draft in ((printed_path, "draft.md"), ("task.md", ".crew/run-1/draft.md")):
            with self.subTest(reply=reply, draft=draft):
                result = self.call("append", "run-1", "--author", "lead", "--to", "worker",
                                   "--kind", "response", "--reply-to", reply, "--file", draft,
                                   status=1, read_only=True)
                self.assertIn("file arguments are relative to the run directory", result.stderr)
                self.assertIn(printed_path if reply == printed_path else draft, result.stderr)
                self.assertNotIn("[Errno", result.stderr)
        self.append(ANSWER, reply="relay/000001.md", author="lead", kind="response")
        self.assertEqual(self.plan()["latest_relay"], 2)

    def test_missing_response_target_has_a_contextual_error(self):
        result = self.call("append", "run-1", "--author", "worker", "--to", "lead",
                           "--kind", "correction", "--reply-to", "report-2.md", "--file", "draft.md",
                           status=1, read_only=True)
        self.assertIn("response target does not exist in this run", result.stderr)
        self.assertIn("report-2.md", result.stderr)
        self.assertNotIn("[Errno", result.stderr)
        self.assertFalse((self.run / "relay").exists())

    def test_invalid_cursor_is_not_silently_reinterpreted(self):
        self.append()
        self.call("read-plan", "run-1", "--after", "2", status=1, read_only=True)
        for value in ("-1", "abc"):
            self.call("read-plan", "run-1", "--after", value, status=2, read_only=True)

    def test_summary_coverage_cannot_overwrite_or_skip_beyond_history(self):
        self.two_relays()
        self.compact()
        for through in ("1", "2", "3"):
            self.call("publish-summary", "run-1", "--through", through, "--file", "summary-draft.md",
                      status=1, read_only=True)

    def test_changed_sources_refuse_summary_but_allow_explicit_originals(self):
        first, _ = self.two_relays()
        self.compact()
        first.write_bytes(first.read_bytes().replace(b"Local time", b"Local zone"))
        self.call("read-plan", "run-1", status=1, read_only=True)
        plan = self.plan("--after", "0")
        self.assertIsNone(plan["summary"])
        self.assertIn("relay/000001.md", self.paths(plan))

    def test_missing_or_partial_relay_is_visible_as_failure(self):
        first, second = self.two_relays()
        original = second.read_bytes()
        second.write_bytes(original.removesuffix(b"STATUS: done\n"))
        self.call("read-plan", "run-1", status=1, read_only=True)
        second.write_bytes(original)
        first.unlink()
        self.call("read-plan", "run-1", status=1, read_only=True)

    def test_incomplete_latest_summary_does_not_fall_back_silently(self):
        self.two_relays()
        self.compact()
        target = self.run / "summaries/through-000002.md"
        target.write_bytes(target.read_bytes().removesuffix(b"STATUS: done\n"))
        self.call("read-plan", "run-1", status=1, read_only=True)
        self.assertEqual(self.plan("--after", "0")["latest_relay"], 2)

    def test_draft_sections_and_line_endings(self):
        for body in (MESSAGE.replace("## Evidence", "## Missing"), "~~~\n" + MESSAGE + "~~~\n",
                     MESSAGE + "\n~~~\n", MESSAGE.replace("\n", "\r\n")):
            with self.subTest(body=body):
                self.run.joinpath("draft.md").write_bytes(body.encode())
                self.call("append", "run-1", "--author", "worker", "--to", "lead", "--kind", "question",
                          "--reply-to", "task.md", "--file", "draft.md", status=1, read_only=True)

    def test_relay_preserves_inline_completion_text(self):
        body = MESSAGE.rstrip("\n") + "\nEnd the report with the exact line STATUS: done"
        for ending in ("", "\n", "\n\nSTATUS: done", "\n\nSTATUS: done\n"):
            with self.subTest(ending=ending):
                record = self.append(body + ending, author="lead", kind="request")
                published = record.read_text().split("\n\n", 2)[2]
                self.assertEqual(published, body + "\n\nSTATUS: done\n")
                self.assertEqual(self.paths(self.plan())[-1], f"relay/{record.name}")

    def test_summary_preserves_inline_completion_text(self):
        self.two_relays()
        body = SUMMARY.rstrip("\n") + "\nreport-1.md must end with STATUS: done"
        self.run.joinpath("summary-draft.md").write_text(body + "\n")
        self.compact()
        record = self.run / "summaries/through-000002.md"
        published = record.read_text().split("\n\n", 2)[2]
        self.assertEqual(published, body + "\n\nSTATUS: done\n")
        self.assertEqual(self.plan()["summary"], "summaries/through-000002.md")

    def test_symlinked_draft_and_destination_are_refused(self):
        target = self.base / "outside.md"
        target.write_text(MESSAGE)
        draft = self.run / "draft.md"
        draft.unlink()
        draft.symlink_to(target)
        self.call("append", "run-1", "--author", "worker", "--to", "lead", "--kind", "question",
                  "--reply-to", "task.md", "--file", "draft.md", status=1, read_only=True)
        draft.unlink()
        draft.write_text(MESSAGE)
        (self.run / "relay").symlink_to(self.base, target_is_directory=True)
        self.call("append", "run-1", "--author", "worker", "--to", "lead", "--kind", "question",
                  "--reply-to", "task.md", "--file", "draft.md", status=1, read_only=True)
        self.assertEqual(target.read_text(), MESSAGE)

    def test_symlinked_records_and_session_are_refused(self):
        first = self.append()
        target = self.base / "record.md"
        first.rename(target)
        first.symlink_to(target)
        self.call("read-plan", "run-1", status=1, read_only=True)
        (self.workspace / ".crew/alias").symlink_to(self.run, target_is_directory=True)
        self.call("read-plan", "alias", status=1, read_only=True)

    def test_hidden_unpublished_draft_is_not_delivered(self):
        self.append()
        (self.run / "relay/.publish-interrupted").write_text("partial")
        self.assertEqual(self.plan()["latest_relay"], 1)

    def test_read_plan_does_not_expose_contents_or_write_read_receipts(self):
        self.append(MESSAGE.replace("Local time", "SYNTHETIC_PRIVATE_SENTINEL"))
        (self.run / "dismissed.md").write_text("Keep this finding closed.\n")
        result = self.call("read-plan", "run-1", "--json", read_only=True)
        self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", result.stdout)
        self.assertIn("dismissed.md", self.paths(json.loads(result.stdout)))
        self.assertEqual(self.before_authority, snapshot_tree(self.state))

    def test_concurrent_publication_never_overwrites(self):
        command = [
            str(SCRIPTS / "relay.sh"), "append", "run-1", "--author", "worker", "--to", "lead",
            "--kind", "question", "--reply-to", "task.md", "--file", "draft.md",
        ]
        children = [
            subprocess.Popen(command, cwd=self.workspace, env=self.environment,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        outputs = [child.communicate(timeout=15) for child in children]
        successes = [out[0].strip() for child, out in zip(children, outputs) if child.returncode == 0]
        self.assertGreaterEqual(len(successes), 1)
        self.assertEqual(len(set(successes)), len(successes))
        self.assertEqual(self.plan()["latest_relay"], len(successes))
        self.assertFalse(list((self.run / "relay").glob(".publish-*")))
        for child in children:
            self.assertIn(child.returncode, (0, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
