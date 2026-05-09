# agent-playbook-kit

Compile one small TOML playbook into practical instruction files for AI coding agents.

`agent-playbook-kit` is for maintainers who use several coding agents (Codex, Claude Code, Cursor, Copilot Coding Agent) and do not want four drifting instruction files. Keep a single `agent-playbook.toml`, validate it for obvious quality/security issues, then render agent-specific files.

## Why this exists

AI coding assistants increasingly depend on repository-local context such as `AGENTS.md`, `CLAUDE.md`, Cursor rules, and Copilot instructions. Teams quickly run into three problems:

1. instructions drift between tools;
2. playbooks become too long or vague;
3. unsafe snippets or accidental secrets can be copied into instruction files.

This project provides a tiny, dependency-light workflow for a repeatable "agent instruction release".

## Install

From a checkout:

```bash
python -m pip install -e .
```

No runtime dependencies are required beyond Python 3.11+.

## Quick start

```bash
# 1) Create a starter playbook, or migrate existing instruction files
agent-playbook init

# Optional: choose a starter template when no instruction files exist
agent-playbook init --template python-cli

# Optional: discover starter templates without writing files
agent-playbook templates
agent-playbook init --list-templates

# Optional: preview migration before writing agent-playbook.toml
agent-playbook init --preview

# 2) Validate it
agent-playbook check agent-playbook.toml

# 3) Preview generated file changes
agent-playbook diff --target agents --target claude --target cursor

# 4) Use diff in scripts/local checks without writing files or printing clean output
agent-playbook diff --quiet --target agents --target claude --target cursor

# 5) Render files for common agents
agent-playbook render --target agents --target claude --target cursor
```

Outputs:

- `AGENTS.md` for Codex/OpenAI-style coding agents;
- `CLAUDE.md` for Claude Code;
- `.cursor/rules/agent-playbook.mdc` for Cursor;
- optionally `.github/copilot-instructions.md` for Copilot Coding Agent.

> Note: this repository intentionally does not include GitHub Actions because the current automation token may not have `workflow` scope.

## Playbook format

```toml
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
forbidden = ["Do not alter production credentials or deploy infrastructure."]

[context]
architecture = "Keep business logic isolated from CLI glue."
important_paths = ["src/", "tests/", "examples/"]

[handoff]
summary_template = "Summarize changed files, validation commands, and remaining risks."
```

## CLI reference

```bash
agent-playbook init [path] [--output agent-playbook.toml] [--template generic|python-cli|node-library|docs-only] [--force-template] [--list-templates] [--force] [--dry-run|--preview]
agent-playbook templates
agent-playbook check [agent-playbook.toml]
agent-playbook diff [agent-playbook.toml] --target agents --target claude --target cursor --out . [--exit-code] [--quiet]
agent-playbook render [agent-playbook.toml] --target agents --target claude --target cursor --out . [--dry-run]
```

`init` creates `agent-playbook.toml` by default. If the repository already has `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, or `.cursor/rules/*.mdc`, it bootstraps the playbook from those files instead of writing a starter template. It parses simple Markdown headings conservatively:

- project-like headings become `[project].summary`;
- principle/guideline/rule headings become `[principles].items`;
- command/setup/test/lint/run headings become `[commands]` entries when commands are written in backticks;
- constraint/boundary/security/forbidden headings become `[boundaries].forbidden`.

Use `--template` to choose a built-in starter when no existing instruction files are detected:

- `generic`: general-purpose starter matching the original init behavior;
- `python-cli`: Python command-line package with unittest and compileall checks;
- `node-library`: Node.js or TypeScript library with npm scripts;
- `docs-only`: documentation-focused repository.

Run `agent-playbook templates` or `agent-playbook init --list-templates` to list templates without writing files. Migration stays preferred when source instruction files exist; pass `--force-template` only when you intentionally want the selected template instead.

Use `--output path/to/agent-playbook.toml` to choose the destination. Existing output files are never overwritten unless `--force` is passed.

Use `--preview` or `--dry-run` before migration to inspect detected source files and the TOML sections that would be generated, without creating `agent-playbook.toml`:

```bash
agent-playbook init --preview
agent-playbook init --dry-run --output /tmp/agent-playbook.toml
```

`check` reports:

- missing required project metadata;
- missing recommended setup/test commands;
- over-large playbooks;
- token/API-key/secret-looking strings.

`diff` validates the playbook like `render`, then prints unified diffs between existing instruction files and the content that would be generated. Missing files are shown as diffs from `/dev/null`. Targets default to `agents`. Pass `--exit-code` to return `1` when generated output would differ from files on disk, `0` when there are no changes, and `2` for validation or usage errors.

Use `--quiet` for copy-paste local verification in scripts. It prints nothing when generated outputs match the files on disk, exits `0` when clean, and exits `1` when any target has drift:

```bash
agent-playbook diff --quiet --target agents --target claude --target cursor
```

## Example

See `examples/agent-playbook.toml` and run:

```bash
python -m agent_playbook_kit.cli check examples/agent-playbook.toml
python -m agent_playbook_kit.cli diff examples/agent-playbook.toml --out /tmp/agent-playbook-demo --target agents --target claude --target cursor
python -m agent_playbook_kit.cli render examples/agent-playbook.toml --out /tmp/agent-playbook-demo --target agents --target claude --target cursor
```

Self-contained migration example:

```bash
tmpdir="$(mktemp -d)"
cd "$tmpdir"

cat > AGENTS.md <<'EOF'
# Agent Instructions

## Project

Payment API for account billing.

## Principles

- Prefer focused patches.
- Explain validation gaps.

## Commands

- Setup: `python -m pip install -e .`
- Test: `python -m unittest discover -s tests -v`

## Constraints

- Do not commit secrets, caches, or build output.
EOF

agent-playbook init --output agent-playbook.toml
agent-playbook init --preview
agent-playbook check agent-playbook.toml
agent-playbook diff agent-playbook.toml --target agents --target claude --target cursor
agent-playbook diff --quiet agent-playbook.toml --target agents --target claude --target cursor
```

## Non-goals

- It is not a full policy engine.
- It does not call LLM APIs.
- It does not manage secrets or deploy infrastructure.
- It does not overwrite workflows or CI configuration.

## Development

```bash
python -m compileall src tests
python -m unittest discover -s tests
python -m agent_playbook_kit.cli check examples/agent-playbook.toml
python scripts/selfcheck.py
```

## License

MIT
