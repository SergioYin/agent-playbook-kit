from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_playbook_kit.cli import DEFAULT_PLAYBOOK, load_playbook, main, render, validate


class AgentPlaybookTests(unittest.TestCase):
    def test_default_playbook_validates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "agent-playbook.toml"
            path.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            data = load_playbook(path)
            issues = validate(data, path.read_text(encoding="utf-8"))
            self.assertFalse([i for i in issues if i.level == "error"])

    def test_secret_detection_returns_error(self) -> None:
        raw = DEFAULT_PLAYBOOK + '\nleak = "GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz"\n'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "agent-playbook.toml"
            path.write_text(raw, encoding="utf-8")
            data = load_playbook(path)
            issues = validate(data, raw)
            self.assertTrue(any(i.level == "error" for i in issues))

    def test_render_writes_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            data = load_playbook(playbook)
            written = render(data, out, ["agents", "claude", "cursor"])
            self.assertEqual(len(written), 3)
            self.assertTrue((out / "AGENTS.md").exists())
            self.assertTrue((out / "CLAUDE.md").exists())
            self.assertTrue((out / ".cursor/rules/agent-playbook.mdc").exists())

    def test_cli_check_example(self) -> None:
        self.assertEqual(main(["check", "examples/agent-playbook.toml"]), 0)

    def test_cli_diff_reports_additions_for_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["diff", str(playbook), "--out", str(out), "--target", "agents"])

            output = stdout.getvalue()
            self.assertEqual(status, 0)
            self.assertIn("--- /dev/null", output)
            self.assertIn(f"+++ {out / 'AGENTS.md'}", output)
            self.assertIn("+# Agent Instructions: example-service", output)
            self.assertFalse((out / "AGENTS.md").exists())

    def test_cli_diff_reports_no_changes_for_matching_generated_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            data = load_playbook(playbook)
            render(data, out, ["agents"])
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["diff", str(playbook), "--out", str(out)])

            self.assertEqual(status, 0)
            self.assertEqual(stdout.getvalue(), "No changes.\n")

    def test_cli_diff_validation_errors_fail(self) -> None:
        raw = DEFAULT_PLAYBOOK + '\nleak = "token=abcdefghijklmnopqrstuvwxyz123456"\n'
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(raw, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = main(["diff", str(playbook), "--out", str(out)])

            self.assertEqual(status, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("ERROR: possible secret detected", stderr.getvalue())
            self.assertFalse((out / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
