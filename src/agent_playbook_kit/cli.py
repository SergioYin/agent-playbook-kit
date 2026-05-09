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

INSTRUCTION_SOURCES = [
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path(".github/copilot-instructions.md"),
]

COMMAND_HINTS = ("setup", "install", "test", "lint", "format", "run", "build", "check")

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


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def toml_string(value: str) -> str:
    value = redact_secrets(value)
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def toml_array(items: list[str]) -> str:
    if not items:
        return "[]"
    rendered = ",\n  ".join(toml_string(item) for item in items)
    return "[\n  " + rendered + "\n]"


def clean_markdown_text(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                lines = lines[index + 1 :]
                break
    return "\n".join(lines).strip()


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = "project"
    current_lines: list[str] = []
    for line in clean_markdown_text(text).splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = match.group(1).strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "\n".join(lines).strip()]


def normalize_heading(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()


def classify_section(heading: str) -> str:
    normalized = normalize_heading(heading)
    if any(word in normalized for word in ("command", "setup", "test", "build", "run", "lint")):
        return "commands"
    if any(word in normalized for word in ("constraint", "boundary", "forbidden", "avoid", "never", "security")):
        return "constraints"
    if any(word in normalized for word in ("principle", "guideline", "practice", "instruction", "rule")):
        return "principles"
    if any(word in normalized for word in ("project", "overview", "summary", "snapshot", "context", "about")):
        return "project"
    return "project"


def extract_list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if match:
            items.append(match.group(1).strip())
    if items:
        return items
    collapsed = re.sub(r"\s+", " ", text).strip()
    return [collapsed] if collapsed else []


def plain_text(text: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_commands(text: str) -> dict[str, str]:
    commands: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        code_match = re.search(r"`([^`]+)`", stripped)
        if not code_match:
            continue
        command = code_match.group(1).strip()
        prefix = stripped[: code_match.start()]
        key_match = re.search(r"([A-Za-z][A-Za-z0-9_-]*)\s*:?\s*$", prefix)
        key = key_match.group(1).lower().replace("-", "_") if key_match else ""
        if key not in COMMAND_HINTS:
            for hint in COMMAND_HINTS:
                if re.search(rf"\b{re.escape(hint)}\b", stripped, re.IGNORECASE):
                    key = hint
                    break
        if key in COMMAND_HINTS and key not in commands:
            commands[key] = command
    return commands


def discover_instruction_sources(root: Path) -> list[Path]:
    sources = [root / rel for rel in INSTRUCTION_SOURCES if (root / rel).is_file()]
    cursor_sources = sorted((root / ".cursor/rules").glob("*.mdc"))
    for source in cursor_sources:
        if source not in sources and source.is_file():
            sources.append(source)
    return sources


def infer_project_name(root: Path) -> str:
    name = root.resolve().name
    return name or "example-service"


def infer_language(root: Path) -> str:
    checks = [
        ("pyproject.toml", "Python"),
        ("package.json", "JavaScript/TypeScript"),
        ("Cargo.toml", "Rust"),
        ("go.mod", "Go"),
        ("pom.xml", "Java"),
        ("Gemfile", "Ruby"),
    ]
    for filename, language in checks:
        if (root / filename).exists():
            return language
    return "Not specified"


def build_migrated_playbook(root: Path, sources: list[Path]) -> str:
    project_chunks: list[str] = []
    principles: list[str] = []
    forbidden: list[str] = []
    commands: dict[str, str] = {}

    for source in sources:
        text = source.read_text(encoding="utf-8")
        for heading, body in split_markdown_sections(text):
            kind = classify_section(heading)
            if kind == "commands":
                commands.update({k: v for k, v in extract_commands(body).items() if k not in commands})
            elif kind == "principles":
                principles.extend(extract_list_items(body))
            elif kind == "constraints":
                forbidden.extend(extract_list_items(body))
            elif body:
                project_chunks.append(plain_text(body))

    summary = next((chunk for chunk in project_chunks if chunk), "Migrated from existing repository agent instruction files.")
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "..."
    source_paths = [str(path.relative_to(root)) for path in sources]
    principles = principles[:12] or [
        "Prefer small, reviewable changes.",
        "Run tests or explain why they could not run.",
    ]
    forbidden = forbidden[:12] or [
        "Do not commit secrets, caches, build output, or generated credentials.",
    ]

    lines = [
        "# agent-playbook.toml: migrated from existing repository instruction files",
        "[project]",
        f"name = {toml_string(infer_project_name(root))}",
        f"summary = {toml_string(summary)}",
        f"language = {toml_string(infer_language(root))}",
        "",
        "[commands]",
    ]
    if commands:
        for key in sorted(commands):
            lines.append(f"{key} = {toml_string(commands[key])}")
    else:
        lines.extend(
            [
                '# setup = "python -m pip install -e ."',
                '# test = "python -m unittest discover -s tests -v"',
            ]
        )
    lines.extend(
        [
            "",
            "[principles]",
            f"items = {toml_array(principles)}",
            "",
            "[boundaries]",
            'allowed = ["Edit source, tests, docs, examples, and packaging metadata."]',
            f"forbidden = {toml_array(forbidden)}",
            "",
            "[context]",
            f"architecture = {toml_string('Review migrated source instruction files for additional architecture notes.')}",
            f"important_paths = {toml_array(source_paths)}",
            "",
            "[handoff]",
            'summary_template = "Summarize changed files, validation commands, and remaining risks."',
            "",
        ]
    )
    return "\n".join(lines)


def init_playbook_content(root: Path) -> tuple[str, list[Path]]:
    sources = discover_instruction_sources(root)
    if not sources:
        return DEFAULT_PLAYBOOK, []
    return build_migrated_playbook(root, sources), sources


def preview_init(content: str, sources: list[Path], root: Path, path: Path) -> None:
    print(f"Would create {path}")
    if sources:
        print("Detected source files:")
        for source in sources:
            print(f"- {source.relative_to(root)}")
    else:
        print("Detected source files: none; would use starter playbook")

    data = tomllib.loads(content)
    print("Generated sections:")
    for section in ("project", "commands", "principles", "boundaries", "context", "handoff"):
        value = data.get(section)
        if not value:
            continue
        if isinstance(value, dict):
            keys = ", ".join(sorted(value))
            print(f"- [{section}] {keys}")
        else:
            print(f"- [{section}]")


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
    boundaries = data.get("boundaries", data.get("constraints", {}))
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
    if args.path != "agent-playbook.toml" and args.output != "agent-playbook.toml":
        print("Use either positional path or --output, not both", file=sys.stderr)
        return 2
    path = Path(args.output if args.output != "agent-playbook.toml" else args.path)
    if path.exists() and not args.force and not args.dry_run:
        print(f"Refusing to overwrite {path}; pass --force", file=sys.stderr)
        return 2
    root = Path(".")
    content, sources = init_playbook_content(root)
    if args.dry_run:
        preview_init(content, sources, root, path)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if sources:
        source_list = ", ".join(str(source.relative_to(root)) for source in sources)
        print(f"Created {path} from {source_list}")
    else:
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
        return 2 if args.exit_code or args.quiet else 1
    targets = args.target or ["agents"]
    diff_lines = diff_outputs(data, Path(args.out), targets)
    if not diff_lines:
        if not args.quiet:
            print("No changes.")
        return 0
    if args.quiet:
        return 1
    sys.stdout.writelines(diff_lines)
    return 1 if args.exit_code else 0


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
    p_init = sub.add_parser("init", help="create or migrate an agent-playbook.toml")
    p_init.add_argument("path", nargs="?", default="agent-playbook.toml")
    p_init.add_argument("--output", default="agent-playbook.toml", help="playbook path to create")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing output file")
    p_init.add_argument("--dry-run", "--preview", action="store_true", help="preview migrated playbook content without writing files")
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
    p_diff.add_argument("--exit-code", action="store_true", help="return 1 when generated output differs, 0 when unchanged, and 2 for validation errors")
    p_diff.add_argument("--quiet", action="store_true", help="return 1 when generated output differs without printing diffs")
    p_diff.set_defaults(func=cmd_diff)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
