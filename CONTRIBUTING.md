# Contributing

Small, practical improvements are welcome.

Before opening a PR, run:

```bash
python -m compileall src tests
python -m unittest discover -s tests
python -m agent_playbook_kit.cli check examples/agent-playbook.toml
```

Please do not include secrets, generated caches, or large binary files.
