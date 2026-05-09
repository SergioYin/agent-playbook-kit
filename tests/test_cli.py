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

    def test_cli_init_creates_starter_with_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "custom-playbook.toml"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["init", "--output", str(output)])

            self.assertEqual(status, 0)
            self.assertTrue(output.exists())
            self.assertIn("[project]", output.read_text(encoding="utf-8"))
            self.assertIn(f"Created {output}", stdout.getvalue())

    def test_cli_init_refuses_existing_output_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "agent-playbook.toml"
            output.write_text("existing", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                status = main(["init", "--output", str(output)])

            self.assertEqual(status, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")
            self.assertIn("Refusing to overwrite", stderr.getvalue())

    def test_cli_init_migrates_existing_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory() as td, contextlib.chdir(td):
            Path("AGENTS.md").write_text(
                """# Agent Instructions

## Project

Payment API for account billing.

## Principles

- Prefer focused patches.
- Explain validation gaps.

## Commands

- Setup: `python -m pip install -e .`
- Test: `python -m unittest discover -s tests -v`

## Constraints

- Do not commit secrets or build output.
""",
                encoding="utf-8",
            )
            output = Path("agent-playbook.toml")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["init"])

            raw = output.read_text(encoding="utf-8")
            data = load_playbook(output)
            self.assertEqual(status, 0)
            self.assertIn("Created agent-playbook.toml from AGENTS.md", stdout.getvalue())
            self.assertEqual(data["project"]["summary"], "Payment API for account billing.")
            self.assertEqual(data["commands"]["setup"], "python -m pip install -e .")
            self.assertEqual(data["commands"]["test"], "python -m unittest discover -s tests -v")
            self.assertIn("Prefer focused patches.", data["principles"]["items"])
            self.assertIn("Do not commit secrets or build output.", data["boundaries"]["forbidden"])
            self.assertFalse([i for i in validate(data, raw) if i.level == "error"])

    def test_cli_init_migrates_cursor_rules(self) -> None:
        with tempfile.TemporaryDirectory() as td, contextlib.chdir(td):
            rules = Path(".cursor/rules")
            rules.mkdir(parents=True)
            (rules / "python.mdc").write_text(
                """---
description: Python rules
alwaysApply: true
---

## Commands

- Lint: `python -m compileall src tests`
""",
                encoding="utf-8",
            )

            status = main(["init"])
            data = load_playbook(Path("agent-playbook.toml"))

            self.assertEqual(status, 0)
            self.assertEqual(data["commands"]["lint"], "python -m compileall src tests")
            self.assertEqual(data["context"]["important_paths"], [".cursor/rules/python.mdc"])

    def test_cli_init_redacts_secret_looking_migrated_text(self) -> None:
        with tempfile.TemporaryDirectory() as td, contextlib.chdir(td):
            fake_value = "abcdefghijklmnopqrstuvwxyz" + "123456"
            Path("CLAUDE.md").write_text(
                "# Project\n\n"
                + f"Use token={fake_value} for nothing; this should not migrate.\n",
                encoding="utf-8",
            )

            status = main(["init"])
            raw = Path("agent-playbook.toml").read_text(encoding="utf-8")

            self.assertEqual(status, 0)
            self.assertIn("[REDACTED]", raw)
            self.assertNotIn(fake_value, raw)

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

    def test_cli_diff_exit_code_reports_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["diff", str(playbook), "--out", str(out), "--exit-code"])

            output = stdout.getvalue()
            self.assertEqual(status, 1)
            self.assertIn("--- /dev/null", output)
            self.assertIn(f"+++ {out / 'AGENTS.md'}", output)
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

    def test_cli_diff_exit_code_reports_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
            data = load_playbook(playbook)
            render(data, out, ["agents"])
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["diff", str(playbook), "--out", str(out), "--exit-code"])

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

    def test_cli_diff_exit_code_validation_errors_return_two(self) -> None:
        raw = DEFAULT_PLAYBOOK + '\nleak = "token=abcdefghijklmnopqrstuvwxyz123456"\n'
        with tempfile.TemporaryDirectory() as td:
            playbook = Path(td) / "agent-playbook.toml"
            out = Path(td) / "out"
            playbook.write_text(raw, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = main(["diff", str(playbook), "--out", str(out), "--exit-code"])

            self.assertEqual(status, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("ERROR: possible secret detected", stderr.getvalue())
            self.assertFalse((out / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()
