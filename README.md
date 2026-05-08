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
# 1) Create a starter playbook
agent-playbook init

# 2) Validate it
agent-playbook check agent-playbook.toml

# 3) Render files for common agents
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
agent-playbook init [path] [--force]
agent-playbook check [agent-playbook.toml]
agent-playbook render [agent-playbook.toml] --target agents --target claude --target cursor --out .
```

`check` reports:

- missing required project metadata;
- missing recommended setup/test commands;
- over-large playbooks;
- token/API-key/secret-looking strings.

## Example

See `examples/agent-playbook.toml` and run:

```bash
python -m agent_playbook_kit.cli check examples/agent-playbook.toml
python -m agent_playbook_kit.cli render examples/agent-playbook.toml --out /tmp/agent-playbook-demo --target agents --target claude --target cursor
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
```

## License

MIT
