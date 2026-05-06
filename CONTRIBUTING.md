# Contributing

## Development setup

```bash
uv sync --extra dev
```

For ETL-related changes, also install:

```bash
uv sync --extra etl
```

## Required validation before opening a PR

Run all release gates locally:

```bash
uv run pytest -q
uv run python -m tools.verify_chains --ecosystem alpha
uv run python -m tools.verify_chains --ecosystem beta
uv run python -m tools.check_run_config_hashes --base-dir .
```

If payload models changed, regenerate schemas:

```bash
uv run python -m tools.export_event_schemas
```

## PR expectations

- Keep changes focused and test-backed.
- Preserve append-only ledger and hash-chain invariants.
- Avoid silent fallback behavior on contract-critical paths.
- Update `CHANGELOG.md` in `Unreleased` for user-visible changes.
