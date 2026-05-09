from __future__ import annotations

import argparse
import difflib
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*=\s*['\"]?[a-z0-9_\-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
]

DEFAULT_PLAYBOOK = """# agent-playbook.toml: single source for AI coding-agent instructions
[project]
name = "example-service"
summary = "Small web service used to demonstrate agent instructions."
language = "Python"

[commands]
setup = "python -m pip install -e ."
test = "python -m pytest"
lint = "python -m compileall src tests"
run = "python -m example_service"

[principles]
items = [
  "Prefer small, reviewable changes.",
  "Run tests or explain why they could not run.",
  "Never commit secrets, .env files, build caches, or generated credentials."
]

[boundaries]
allowed = ["Edit source, tests, docs, examples, and packaging metadata."]
forbidden = ["Do not alter production credentials or deploy infrastructure.", "Do not add GitHub Actions unless workflow-scope auth is confirmed."]

[context]
architecture = "Keep business logic isolated from CLI glue."
important_paths = ["src/", "tests/", "examples/"]

[handoff]
summary_template = "Summarize changed files, validation commands, and remaining risks."
"""

@dataclass
class Issue:
    level: str
    message: str


@dataclass
class RenderedOutput:
    target: str
    path: Path
    content: str


def load_playbook(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def validate(data: dict[str, Any], raw_text: str) -> list[Issue]:
    issues: list[Issue] = []
    project = data.get("project", {})
    commands = data.get("commands", {})
    if not project.get("name"):
        issues.append(Issue("error", "[project].name is required"))
    if not project.get("summary"):
        issues.append(Issue("warning", "[project].summary helps agents orient quickly"))
    for required in ("setup", "test"):
        if not commands.get(required):
            issues.append(Issue("warning", f"[commands].{required} is recommended"))
    if len(raw_text) > 7000:
        issues.append(Issue("warning", "playbook is large; keep agent instructions concise"))
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(raw_text):
            issues.append(Issue("error", f"possible secret detected near: {match.group(0)[:24]}[REDACTED]"))
    return issues


def bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- Not specified."


def render_agents_md(data: dict[str, Any], target: str) -> str:
    project = data.get("project", {})
    commands = data.get("commands", {})
    principles = as_list(data.get("principles", {}).get("items"))
    boundaries = data.get("boundaries", {})
    context = data.get("context", {})
    handoff = data.get("handoff", {})
    target_note = {
        "agents": "Use this file as the repository-level instruction layer for coding agents.",
        "claude": "Claude Code should read this before planning edits.",
        "cursor": "Cursor should treat these as project rules and prefer linked files over pasted context.",
        "copilot": "Copilot Coding Agent should follow these repository instructions.",
    }.get(target, "Use this as AI-agent guidance.")
    command_lines = "\n".join(f"- `{name}`: `{cmd}`" for name, cmd in commands.items()) or "- Not specified."
    paths = bullet(as_list(context.get("important_paths")))
    return f"""# Agent Instructions: {project.get('name', 'Unnamed project')}

{target_note}

## Project snapshot

- Summary: {project.get('summary', 'Not specified.')}
- Primary language/runtime: {project.get('language', 'Not specified.')}

## Operating principles

{bullet(principles)}

## Commands

{command_lines}

## Context map

- Architecture note: {context.get('architecture', 'Not specified.')}
- Important paths:
{paths}

## Boundaries

Allowed:
{bullet(as_list(boundaries.get('allowed')))}

Forbidden:
{bullet(as_list(boundaries.get('forbidden')))}

## Handoff requirements

{handoff.get('summary_template', 'Summarize changed files, validation, and open risks.')}
"""


def render_outputs(data: dict[str, Any], out_dir: Path, targets: list[str]) -> list[RenderedOutput]:
    mapping = {
        "agents": Path("AGENTS.md"),
        "claude": Path("CLAUDE.md"),
        "cursor": Path(".cursor/rules/agent-playbook.mdc"),
        "copilot": Path(".github/copilot-instructions.md"),
    }
    outputs: list[RenderedOutput] = []
    for target in targets:
        if target not in mapping:
            raise SystemExit(f"Unknown target: {target}")
        rel = mapping[target]
        content = render_agents_md(data, target)
        if target == "cursor":
            content = "---\ndescription: Project AI-agent playbook\nalwaysApply: true\n---\n\n" + content
        dest = out_dir / rel
        outputs.append(RenderedOutput(target, dest, content))
    return outputs


def render(data: dict[str, Any], out_dir: Path, targets: list[str], dry_run: bool = False) -> list[Path]:
    written: list[Path] = []
    for output in render_outputs(data, out_dir, targets):
        dest = output.path
        written.append(dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(output.content, encoding="utf-8")
    return written


def diff_outputs(data: dict[str, Any], out_dir: Path, targets: list[str]) -> list[str]:
    diff_lines: list[str] = []
    for output in render_outputs(data, out_dir, targets):
        new_lines = output.content.splitlines(keepends=True)
        if output.path.exists():
            old_lines = output.path.read_text(encoding="utf-8").splitlines(keepends=True)
            fromfile = str(output.path)
        else:
            old_lines = []
            fromfile = "/dev/null"
        tofile = str(output.path)
        diff_lines.extend(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=fromfile,
                tofile=tofile,
            )
        )
    return diff_lines


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"Refusing to overwrite {path}; pass --force", file=sys.stderr)
        return 2
    path.write_text(DEFAULT_PLAYBOOK, encoding="utf-8")
    print(f"Created {path}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.playbook)
    raw = path.read_text(encoding="utf-8")
    data = load_playbook(path)
    issues = validate(data, raw)
    if not issues:
        print("OK: playbook looks ready")
        return 0
    for issue in issues:
        print(f"{issue.level.upper()}: {issue.message}")
    return 1 if any(i.level == "error" for i in issues) else 0


def cmd_render(args: argparse.Namespace) -> int:
    path = Path(args.playbook)
    raw = path.read_text(encoding="utf-8")
    data = load_playbook(path)
    issues = validate(data, raw)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        for issue in errors:
            print(f"ERROR: {issue.message}", file=sys.stderr)
        return 1
    targets = args.target or ["agents"]
    written = render(data, Path(args.out), targets, args.dry_run)
    action = "Would write" if args.dry_run else "Wrote"
    for path in written:
        print(f"{action}: {path}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    path = Path(args.playbook)
    raw = path.read_text(encoding="utf-8")
    data = load_playbook(path)
    issues = validate(data, raw)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        for issue in errors:
            print(f"ERROR: {issue.message}", file=sys.stderr)
        return 1
    targets = args.target or ["agents"]
    diff_lines = diff_outputs(data, Path(args.out), targets)
    if not diff_lines:
        print("No changes.")
        return 0
    sys.stdout.writelines(diff_lines)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-playbook",
        description="Compile one TOML playbook into AI coding-agent instruction files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Typical flow:
          agent-playbook init
          agent-playbook check agent-playbook.toml
          agent-playbook diff --target agents --target claude --target cursor
          agent-playbook render --target agents --target claude --target cursor
        """),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="create a starter agent-playbook.toml")
    p_init.add_argument("path", nargs="?", default="agent-playbook.toml")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_check = sub.add_parser("check", help="validate a playbook")
    p_check.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_check.set_defaults(func=cmd_check)

    p_render = sub.add_parser("render", help="render instruction files")
    p_render.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_render.add_argument("--out", default=".", help="output directory")
    p_render.add_argument("--target", action="append", choices=["agents", "claude", "cursor", "copilot"], help="render target; may be repeated; defaults to agents")
    p_render.add_argument("--dry-run", action="store_true")
    p_render.set_defaults(func=cmd_render)

    p_diff = sub.add_parser("diff", help="preview instruction file changes")
    p_diff.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_diff.add_argument("--out", default=".", help="output directory")
    p_diff.add_argument("--target", action="append", choices=["agents", "claude", "cursor", "copilot"], help="diff target; may be repeated; defaults to agents")
    p_diff.set_defaults(func=cmd_diff)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
