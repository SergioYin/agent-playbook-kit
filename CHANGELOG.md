# Changelog

## v0.1.6

- Added `agent-playbook validate` to report playbook commands missing from `README.md`, `package.json` scripts, and `pyproject.toml` project scripts.
- Added stable JSON output and `--no-fail` support for command drift validation.

## v0.1.5

- Added built-in starter templates for `generic`, `python-cli`, `node-library`, and `docs-only` projects.
- Added `agent-playbook templates` and `agent-playbook init --list-templates` for template discovery.
- Added `scripts/selfcheck.py` for copy-paste local validation of unit tests plus render/diff/init smoke checks.
- Documented template initialization and selfcheck usage.
