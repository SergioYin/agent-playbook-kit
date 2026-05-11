# Changelog

## v0.1.8

- Added `agent-playbook gallery` with curated sample playbooks for Python services, Node packages, and docs projects.
- Added `agent-playbook gallery <sample> --output <path>` for writing a selected sample without adding runtime dependencies.
- Added provenance validation/reporting to `agent-playbook diff` so existing outputs with missing or stale generated-output headers are called out before the unified diff.

## v0.1.7

- Added default generated-output provenance headers for rendered and diffed `AGENTS.md`, `CLAUDE.md`, Cursor, and Copilot instruction outputs.
- Added `--no-provenance` for `agent-playbook render` and `agent-playbook diff` to omit provenance headers when needed.

## v0.1.6

- Added `agent-playbook validate` to report playbook commands missing from `README.md`, `package.json` scripts, and `pyproject.toml` project scripts.
- Added stable JSON output and `--no-fail` support for command drift validation.

## v0.1.5

- Added built-in starter templates for `generic`, `python-cli`, `node-library`, and `docs-only` projects.
- Added `agent-playbook templates` and `agent-playbook init --list-templates` for template discovery.
- Added `scripts/selfcheck.py` for copy-paste local validation of unit tests plus render/diff/init smoke checks.
- Documented template initialization and selfcheck usage.
