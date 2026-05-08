from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
