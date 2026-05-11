from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    python = sys.executable
    run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        playbook = work / "agent-playbook.toml"
        out = work / "rendered"
        run(
            [
                python,
                "-m",
                "agent_playbook_kit.cli",
                "gallery",
                "python-service",
                "--output",
                str(work / "gallery-playbook.toml"),
            ]
        )
        run([python, "-m", "agent_playbook_kit.cli", "check", str(work / "gallery-playbook.toml")])
        run(
            [
                python,
                "-m",
                "agent_playbook_kit.cli",
                "init",
                "--template",
                "python-cli",
                "--output",
                str(playbook),
            ]
        )
        run([python, "-m", "agent_playbook_kit.cli", "check", str(playbook)])
        run(
            [
                python,
                "-m",
                "agent_playbook_kit.cli",
                "render",
                str(playbook),
                "--out",
                str(out),
                "--target",
                "agents",
                "--target",
                "claude",
                "--target",
                "cursor",
            ]
        )
        run(
            [
                python,
                "-m",
                "agent_playbook_kit.cli",
                "diff",
                str(playbook),
                "--out",
                str(out),
                "--quiet",
                "--target",
                "agents",
                "--target",
                "claude",
                "--target",
                "cursor",
            ]
        )

    print("selfcheck passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
