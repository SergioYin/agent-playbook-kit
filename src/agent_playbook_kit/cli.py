from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import textwrap
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_playbook_kit import __version__

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

SAMPLE_PLAYBOOKS: dict[str, dict[str, str]] = {
    "python-service": {
        "description": "Python service with CLI, tests, and review boundaries.",
        "content": """# agent-playbook.toml: sample gallery / python-service
[project]
name = "billing-service"
summary = "Python billing service with a small CLI, deterministic unit tests, and package metadata."
language = "Python"

[commands]
setup = "python -m pip install -e ."
test = "python -m unittest discover -s tests -v"
lint = "python -m compileall src tests"
run = "python -m billing_service --help"

[principles]
items = [
  "Keep CLI parsing thin and put business behavior in importable modules.",
  "Prefer focused tests around billing calculations, parsing, and command exit codes.",
  "Document skipped validation with the exact blocker and risk."
]

[boundaries]
allowed = ["Edit source, tests, docs, examples, and packaging metadata."]
forbidden = [
  "Do not edit production credentials, customer data exports, or deployment settings.",
  "Do not add network calls to unit tests.",
  "Do not add GitHub Actions unless workflow-scope auth is confirmed."
]

[context]
architecture = "The CLI delegates to service modules; IO adapters sit at the edges."
important_paths = ["src/billing_service/", "tests/", "README.md", "pyproject.toml"]

[handoff]
summary_template = "Summarize changed files, test commands, CLI behavior impact, and remaining billing risks."
""",
    },
    "node-package": {
        "description": "Node or TypeScript package with package-script validation.",
        "content": """# agent-playbook.toml: sample gallery / node-package
[project]
name = "token-format"
summary = "Node package that exposes a small formatting API and command-line helper."
language = "JavaScript/TypeScript"

[commands]
setup = "npm install"
test = "npm test"
lint = "npm run lint"
build = "npm run build"

[principles]
items = [
  "Treat exported functions as public API and avoid breaking changes without docs.",
  "Keep tests focused on package entry points, edge cases, and CLI behavior.",
  "Avoid generated dependency churn unless dependency changes are required."
]

[boundaries]
allowed = ["Edit source, tests, examples, README, and package metadata."]
forbidden = [
  "Do not commit node_modules, build output, .env files, or registry tokens.",
  "Do not change package publishing credentials or release automation.",
  "Do not add GitHub Actions unless workflow-scope auth is confirmed."
]

[context]
architecture = "Source modules expose the public API; tests verify both imports and CLI entry points."
important_paths = ["src/", "test/", "tests/", "package.json", "README.md"]

[handoff]
summary_template = "Summarize API impact, commands run, changed files, and release risks."
""",
    },
    "docs-project": {
        "description": "Documentation repository with copy-paste command checks.",
        "content": """# agent-playbook.toml: sample gallery / docs-project
[project]
name = "platform-docs"
summary = "Documentation repository where Markdown accuracy and runnable examples matter most."
language = "Markdown"

[commands]
setup = "python -m pip install -e ."
test = "python -m unittest discover -s tests -v"
lint = "python -m compileall scripts tests"

[principles]
items = [
  "Preserve user-facing meaning and verify command examples after editing.",
  "Prefer concise task-focused docs over broad rewrites.",
  "Call out assumptions when examples depend on account, region, or runtime setup."
]

[boundaries]
allowed = ["Edit Markdown, examples, docs assets, and documentation helper scripts."]
forbidden = [
  "Do not edit deployment credentials, generated site output, or production settings.",
  "Do not introduce external dependencies for simple documentation checks.",
  "Do not add GitHub Actions unless workflow-scope auth is confirmed."
]

[context]
architecture = "README and docs pages are source content; generated artifacts must be reproducible."
important_paths = ["README.md", "docs/", "examples/", "scripts/"]

[handoff]
summary_template = "List docs changed, examples checked, commands run, and content needing review."
""",
    },
}

STARTER_TEMPLATES: dict[str, dict[str, Any]] = {
    "generic": {
        "description": "General-purpose starter matching the original init behavior.",
        "language": "Python",
        "summary": "Small service used to demonstrate agent instructions.",
        "commands": {
            "setup": "python -m pip install -e .",
            "test": "python -m pytest",
            "lint": "python -m compileall src tests",
            "run": "python -m example_service",
        },
        "principles": [
            "Prefer small, reviewable changes.",
            "Run tests or explain why they could not run.",
            "Never commit secrets, .env files, build caches, or generated credentials.",
        ],
        "allowed": ["Edit source, tests, docs, examples, and packaging metadata."],
        "forbidden": [
            "Do not alter production credentials or deploy infrastructure.",
            "Do not add GitHub Actions unless workflow-scope auth is confirmed.",
        ],
        "architecture": "Keep business logic isolated from CLI glue.",
        "paths": ["src/", "tests/", "examples/"],
        "handoff": "Summarize changed files, validation commands, and remaining risks.",
    },
    "python-cli": {
        "description": "Python command-line tool with unittest/compileall checks.",
        "language": "Python",
        "summary": "Python CLI package with standard-library friendly tests and packaging metadata.",
        "commands": {
            "setup": "python -m pip install -e .",
            "test": "python -m unittest discover -s tests -v",
            "lint": "python -m compileall src tests",
            "run": "python -m your_package --help",
        },
        "principles": [
            "Keep CLI parsing thin and move behavior into testable functions.",
            "Prefer deterministic unit tests around command behavior and exit codes.",
            "Preserve standard-library compatibility unless project metadata says otherwise.",
        ],
        "allowed": ["Edit Python source, tests, examples, README, and packaging metadata."],
        "forbidden": [
            "Do not commit virtual environments, build artifacts, caches, or credentials.",
            "Do not introduce network calls into unit tests.",
            "Do not add GitHub Actions unless workflow-scope auth is confirmed.",
        ],
        "architecture": "The CLI should parse arguments and delegate behavior to importable modules under src/.",
        "paths": ["src/", "tests/", "README.md", "pyproject.toml"],
        "handoff": "List changed files, validation commands, user-visible CLI impact, and remaining risks.",
    },
    "node-library": {
        "description": "Node.js or TypeScript library with npm scripts.",
        "language": "JavaScript/TypeScript",
        "summary": "Node library intended for package consumers and automated tests.",
        "commands": {
            "setup": "npm install",
            "test": "npm test",
            "lint": "npm run lint",
            "build": "npm run build",
        },
        "principles": [
            "Keep public APIs stable and document behavior changes.",
            "Prefer focused tests around exported functions and package entry points.",
            "Avoid generated dependency churn unless dependency changes are required.",
        ],
        "allowed": ["Edit library source, tests, examples, README, and package metadata."],
        "forbidden": [
            "Do not commit node_modules, build output, .env files, or registry tokens.",
            "Do not change package publishing credentials or release automation.",
            "Do not add GitHub Actions unless workflow-scope auth is confirmed.",
        ],
        "architecture": "Source modules expose the public API; tests should cover package entry points and edge cases.",
        "paths": ["src/", "test/", "tests/", "package.json", "README.md"],
        "handoff": "Summarize API impact, validation commands, changed files, and any release risks.",
    },
    "docs-only": {
        "description": "Documentation repository or docs-focused project.",
        "language": "Markdown",
        "summary": "Documentation project focused on accurate, readable Markdown content.",
        "commands": {
            "setup": "python -m pip install -e .",
            "test": "python -m unittest discover -s tests -v",
            "lint": "python -m compileall scripts tests",
        },
        "principles": [
            "Preserve user-facing meaning and examples when reorganizing text.",
            "Keep instructions copy-paste runnable and note environment assumptions.",
            "Prefer concise docs with clear command examples over broad rewrites.",
        ],
        "allowed": ["Edit Markdown, examples, docs assets, and documentation helper scripts."],
        "forbidden": [
            "Do not edit production credentials, deployment settings, or generated site output.",
            "Do not add external dependencies for simple documentation checks.",
            "Do not add GitHub Actions unless workflow-scope auth is confirmed.",
        ],
        "architecture": "README and docs pages are the source of truth; generated artifacts should be reproducible.",
        "paths": ["README.md", "docs/", "examples/", "scripts/"],
        "handoff": "List docs changed, commands run, examples checked, and any content that still needs review.",
    },
}

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


@dataclass
class CommandEvidence:
    source: str
    detail: str


@dataclass
class CommandDriftIssue:
    id: str
    command_key: str
    command: str
    evidence: list[str]


@dataclass
class ProvenanceIssue:
    target: str
    path: Path
    status: str
    message: str


@dataclass
class DiffResult:
    lines: list[str]
    provenance_issues: list[ProvenanceIssue]


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


def template_names() -> list[str]:
    return sorted(STARTER_TEMPLATES)


def render_template_playbook(template_name: str, root: Path) -> str:
    try:
        template = STARTER_TEMPLATES[template_name]
    except KeyError as exc:
        raise SystemExit(f"Unknown template: {template_name}") from exc
    if template_name == "generic":
        return DEFAULT_PLAYBOOK
    lines = [
        f"# agent-playbook.toml: {template_name} starter template",
        "[project]",
        f"name = {toml_string(infer_project_name(root))}",
        f"summary = {toml_string(template['summary'])}",
        f"language = {toml_string(template['language'])}",
        "",
        "[commands]",
    ]
    for key, value in template["commands"].items():
        lines.append(f"{key} = {toml_string(value)}")
    lines.extend(
        [
            "",
            "[principles]",
            f"items = {toml_array(template['principles'])}",
            "",
            "[boundaries]",
            f"allowed = {toml_array(template['allowed'])}",
            f"forbidden = {toml_array(template['forbidden'])}",
            "",
            "[context]",
            f"architecture = {toml_string(template['architecture'])}",
            f"important_paths = {toml_array(template['paths'])}",
            "",
            "[handoff]",
            f"summary_template = {toml_string(template['handoff'])}",
            "",
        ]
    )
    return "\n".join(lines)


def print_templates() -> None:
    for name in template_names():
        print(f"{name}\t{STARTER_TEMPLATES[name]['description']}")


def sample_names() -> list[str]:
    return sorted(SAMPLE_PLAYBOOKS)


def sample_content(name: str) -> str:
    try:
        content = SAMPLE_PLAYBOOKS[name]["content"]
    except KeyError as exc:
        raise SystemExit(f"Unknown sample: {name}") from exc
    return content.rstrip() + "\n"


def print_gallery() -> None:
    for name in sample_names():
        print(f"{name}\t{SAMPLE_PLAYBOOKS[name]['description']}")


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


def init_playbook_content(root: Path, template_name: str = "generic", force_template: bool = False) -> tuple[str, list[Path], str]:
    sources = discover_instruction_sources(root)
    if sources and not force_template:
        return build_migrated_playbook(root, sources), sources, "migration"
    return render_template_playbook(template_name, root), [], "template"


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


def command_entries(data: dict[str, Any]) -> dict[str, str]:
    commands = data.get("commands", {})
    if not isinstance(commands, dict):
        return {}
    return {str(key): str(value) for key, value in commands.items() if str(value).strip()}


def read_optional_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def command_supported_by_readme(command: str, root: Path) -> CommandEvidence | None:
    if command and command in read_optional_text(root / "README.md"):
        return CommandEvidence("README.md", "contains exact command")
    return None


def npm_script_command_names(name: str) -> set[str]:
    commands = {f"npm run {name}", f"npm run-script {name}"}
    if name in {"start", "stop", "test", "restart"}:
        commands.add(f"npm {name}")
    return commands


def command_supported_by_package_json(command: str, root: Path) -> CommandEvidence | None:
    path = root / "package.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return None
    for name in sorted(scripts):
        value = str(scripts[name])
        if command == value or command in npm_script_command_names(str(name)):
            return CommandEvidence("package.json", f"scripts.{name}")
    return None


def command_supported_by_pyproject(command: str, root: Path) -> CommandEvidence | None:
    path = root / "pyproject.toml"
    raw = read_optional_text(path)
    if command and command in raw:
        return CommandEvidence("pyproject.toml", "contains exact command")
    if not raw:
        return None
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError:
        return None
    scripts = data.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        return None
    executable = command.split(maxsplit=1)[0] if command else ""
    for name in sorted(scripts):
        if executable == str(name) or command == str(scripts[name]):
            return CommandEvidence("pyproject.toml", f"project.scripts.{name}")
    return None


def command_evidence(command: str, root: Path) -> list[CommandEvidence]:
    evidence: list[CommandEvidence] = []
    for checker in (
        command_supported_by_readme,
        command_supported_by_package_json,
        command_supported_by_pyproject,
    ):
        found = checker(command, root)
        if found is not None:
            evidence.append(found)
    return evidence


def validate_command_drift(data: dict[str, Any], root: Path) -> tuple[dict[str, list[CommandEvidence]], list[CommandDriftIssue]]:
    supported: dict[str, list[CommandEvidence]] = {}
    issues: list[CommandDriftIssue] = []
    for key, command in sorted(command_entries(data).items()):
        evidence = command_evidence(command, root)
        supported[key] = evidence
        if not evidence:
            issues.append(
                CommandDriftIssue(
                    "command-missing",
                    key,
                    command,
                    ["README.md", "package.json", "pyproject.toml"],
                )
            )
    return supported, issues


def command_drift_payload(data: dict[str, Any], root: Path) -> dict[str, Any]:
    commands = command_entries(data)
    supported, issues = validate_command_drift(data, root)
    issue_payload = [
        {
            "id": issue.id,
            "command_key": issue.command_key,
            "command": issue.command,
            "evidence": issue.evidence,
        }
        for issue in issues
    ]
    supported_payload = {
        key: [{"source": item.source, "detail": item.detail} for item in evidence]
        for key, evidence in sorted(supported.items())
        if evidence
    }
    return {
        "ok": not issues,
        "commands": {key: commands[key] for key in sorted(commands)},
        "counts": {
            "commands": len(commands),
            "supported": len(commands) - len(issues),
            "issues": len(issues),
        },
        "issues": issue_payload,
        "supported": supported_payload,
    }


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


def html_comment_value(value: str) -> str:
    return value.replace("--", "- -").replace(">", "&gt;")


def provenance_header(playbook_path: Path) -> str:
    source = html_comment_value(playbook_path.as_posix())
    name = html_comment_value(playbook_path.name or playbook_path.as_posix())
    return f"<!-- Generated from {source} (name: {name}) by agent-playbook-kit {__version__}. -->\n\n"


def add_provenance(content: str, target: str, playbook_path: Path) -> str:
    header = provenance_header(playbook_path)
    if target != "cursor":
        return header + content
    frontmatter_end = content.find("\n---\n\n")
    if content.startswith("---\n") and frontmatter_end != -1:
        split_at = frontmatter_end + len("\n---\n\n")
        return content[:split_at] + header + content[split_at:]
    return header + content


def existing_provenance_line(content: str, target: str) -> str | None:
    lines = content.splitlines()
    if target == "cursor" and lines[:4] == ["---", "description: Project AI-agent playbook", "alwaysApply: true", "---"]:
        lines = lines[4:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    first = lines[0].strip() if lines else ""
    if first.startswith("<!-- Generated from ") and first.endswith("-->"):
        return first
    return None


def validate_existing_provenance(output: RenderedOutput, playbook_path: Path) -> ProvenanceIssue | None:
    if not output.path.exists():
        return None
    existing = output.path.read_text(encoding="utf-8")
    actual = existing_provenance_line(existing, output.target)
    expected = provenance_header(playbook_path).strip()
    if actual is None:
        return ProvenanceIssue(
            output.target,
            output.path,
            "missing",
            "missing generated-output provenance header",
        )
    if actual != expected:
        return ProvenanceIssue(
            output.target,
            output.path,
            "stale",
            f"expected `{expected}`, found `{actual}`",
        )
    return None


def render_outputs(
    data: dict[str, Any],
    out_dir: Path,
    targets: list[str],
    playbook_path: Path | None = None,
    include_provenance: bool = False,
) -> list[RenderedOutput]:
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
        if include_provenance:
            content = add_provenance(content, target, playbook_path or Path("agent-playbook.toml"))
        dest = out_dir / rel
        outputs.append(RenderedOutput(target, dest, content))
    return outputs


def render(
    data: dict[str, Any],
    out_dir: Path,
    targets: list[str],
    dry_run: bool = False,
    playbook_path: Path | None = None,
    include_provenance: bool = False,
) -> list[Path]:
    written: list[Path] = []
    for output in render_outputs(data, out_dir, targets, playbook_path, include_provenance):
        dest = output.path
        written.append(dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(output.content, encoding="utf-8")
    return written


def diff_outputs(
    data: dict[str, Any],
    out_dir: Path,
    targets: list[str],
    playbook_path: Path | None = None,
    include_provenance: bool = False,
) -> DiffResult:
    diff_lines: list[str] = []
    provenance_issues: list[ProvenanceIssue] = []
    source_path = playbook_path or Path("agent-playbook.toml")
    for output in render_outputs(data, out_dir, targets, playbook_path, include_provenance):
        if include_provenance:
            issue = validate_existing_provenance(output, source_path)
            if issue is not None:
                provenance_issues.append(issue)
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
    return DiffResult(diff_lines, provenance_issues)


def provenance_report_lines(issues: list[ProvenanceIssue]) -> list[str]:
    if not issues:
        return []
    lines = ["Provenance report:\n"]
    for issue in issues:
        lines.append(f"- {issue.target} {issue.path}: {issue.status}; {issue.message}\n")
    lines.append("\n")
    return lines


def cmd_init(args: argparse.Namespace) -> int:
    if args.list_templates:
        print_templates()
        return 0
    if args.path != "agent-playbook.toml" and args.output != "agent-playbook.toml":
        print("Use either positional path or --output, not both", file=sys.stderr)
        return 2
    path = Path(args.output if args.output != "agent-playbook.toml" else args.path)
    if path.exists() and not args.force and not args.dry_run:
        print(f"Refusing to overwrite {path}; pass --force", file=sys.stderr)
        return 2
    root = Path(".")
    content, sources, init_kind = init_playbook_content(root, args.template, args.force_template)
    if args.dry_run:
        preview_init(content, sources, root, path)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if sources:
        source_list = ", ".join(str(source.relative_to(root)) for source in sources)
        print(f"Created {path} from {source_list}")
    elif init_kind == "template" and args.template != "generic":
        print(f"Created {path} from {args.template} template")
    else:
        print(f"Created {path}")
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    print_templates()
    return 0


def cmd_gallery(args: argparse.Namespace) -> int:
    if args.sample is None:
        if args.output:
            print("Choose a gallery sample when using --output", file=sys.stderr)
            return 2
        print_gallery()
        return 0
    content = sample_content(args.sample)
    if args.output:
        path = Path(args.output)
        if path.exists() and not args.force:
            print(f"Refusing to overwrite {path}; pass --force", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path} from gallery sample {args.sample}")
        return 0
    print(content, end="")
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


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.playbook)
    data = load_playbook(path)
    payload = command_drift_payload(data, path.parent)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload["ok"]:
        count = payload["counts"]["commands"]
        print(f"OK: {count} command{'s' if count != 1 else ''} documented in README or package metadata")
    else:
        counts = payload["counts"]
        print(f"Command drift found: {counts['issues']} of {counts['commands']} command(s) missing")
        for issue in payload["issues"]:
            print(f"- {issue['id']} [{issue['command_key']}]: `{issue['command']}`")
            print(f"  Checked: {', '.join(issue['evidence'])}")
    return 0 if payload["ok"] or args.no_fail else 1


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
    written = render(data, Path(args.out), targets, args.dry_run, path, not args.no_provenance)
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
    result = diff_outputs(data, Path(args.out), targets, path, not args.no_provenance)
    if not result.lines:
        if not args.quiet:
            print("No changes.")
        return 0
    if args.quiet:
        return 1
    sys.stdout.writelines(provenance_report_lines(result.provenance_issues))
    sys.stdout.writelines(result.lines)
    return 1 if args.exit_code else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-playbook",
        description="Compile one TOML playbook into AI coding-agent instruction files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Typical flow:
          agent-playbook init
          agent-playbook gallery
          agent-playbook check agent-playbook.toml
          agent-playbook diff --target agents --target claude --target cursor
          agent-playbook render --target agents --target claude --target cursor
        """),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="create or migrate an agent-playbook.toml")
    p_init.add_argument("path", nargs="?", default="agent-playbook.toml")
    p_init.add_argument("--output", default="agent-playbook.toml", help="playbook path to create")
    p_init.add_argument("--template", choices=template_names(), default="generic", help="starter template to use when not migrating existing instruction files")
    p_init.add_argument("--force-template", action="store_true", help="use --template even when existing instruction files are detected")
    p_init.add_argument("--list-templates", action="store_true", help="list starter templates without writing files")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing output file")
    p_init.add_argument("--dry-run", "--preview", action="store_true", help="preview migrated playbook content without writing files")
    p_init.set_defaults(func=cmd_init)

    p_templates = sub.add_parser("templates", help="list starter templates")
    p_templates.set_defaults(func=cmd_templates)

    p_gallery = sub.add_parser("gallery", help="list or emit curated sample playbooks")
    p_gallery.add_argument("sample", nargs="?", choices=sample_names(), help="sample to print or write; omitted lists the gallery")
    p_gallery.add_argument("--output", help="write the selected sample to a file instead of stdout")
    p_gallery.add_argument("--force", action="store_true", help="overwrite an existing --output file")
    p_gallery.set_defaults(func=cmd_gallery)

    p_check = sub.add_parser("check", help="validate a playbook")
    p_check.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_check.set_defaults(func=cmd_check)

    p_validate = sub.add_parser("validate", help="validate playbook commands against README and package metadata")
    p_validate.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_validate.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    p_validate.add_argument("--no-fail", action="store_true", help="return 0 even when command drift issues are found")
    p_validate.set_defaults(func=cmd_validate)

    p_render = sub.add_parser("render", help="render instruction files")
    p_render.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_render.add_argument("--out", default=".", help="output directory")
    p_render.add_argument("--target", action="append", choices=["agents", "claude", "cursor", "copilot"], help="render target; may be repeated; defaults to agents")
    p_render.add_argument("--no-provenance", action="store_true", help="omit generated-output provenance headers")
    p_render.add_argument("--dry-run", action="store_true")
    p_render.set_defaults(func=cmd_render)

    p_diff = sub.add_parser("diff", help="preview instruction file changes")
    p_diff.add_argument("playbook", nargs="?", default="agent-playbook.toml")
    p_diff.add_argument("--out", default=".", help="output directory")
    p_diff.add_argument("--target", action="append", choices=["agents", "claude", "cursor", "copilot"], help="diff target; may be repeated; defaults to agents")
    p_diff.add_argument("--no-provenance", action="store_true", help="omit generated-output provenance headers")
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
