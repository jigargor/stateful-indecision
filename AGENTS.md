# AGENTS.md

## Project Purpose
- `stateful-indecision` is a ledger-first agent research runtime.
- The core guarantee is append-only, hash-chained event logs with deterministic verification.
- The current objective is stable v1 behavior with strong contracts, safety gates, and observability.

## Core Architecture
- **Blueprint inputs:** `run_config*.json`, `seeds/*`, `schemas/*`
- **Runtime engine:** `agent/*`, `adapters/*`, `workload/*`, `forums/*`
- **Persistence and integrity:** `core/writer.py`, `core/verifier.py`, `infra/storage.py`
- **Safety controls:** `safety/*` + evaluation ledger hooks
- **Observability:** JSONL ledgers + `tools/*` export, analysis, and Grafana starter assets

## Key Data Surfaces
- `ecosystems/<id>/public.jsonl` - primary event stream
- `ecosystems/<id>/evaluation.jsonl` - safety and verifier outcomes
- `ecosystems/<id>/commons.jsonl` - commons interactions
- `ecosystems/<id>/roundtable.jsonl` / `townhall.jsonl` - structured forum streams
- **External townhall visitor:** set `townhall_visitor` on `run_config` to append a closed `session_kind: "external_visitor"` townhall (topic, optional `tangential_bridge` / `relation_to_team_work`, optional `brief`) before the decision loop. `StateBuilder` surfaces the latest visitor briefing on every snapshot so agents can connect tangentially without flattening domains. Re-injection is skipped when the ledger already contains the same visitor `topic` (multi-agent waves share one briefing).
- **Prompt progression:** `prompt_progression` on `run_config` — `off` (default), `standard`, or `aggressive` — adds per-step escalation hints tied to `decision_number` / `max_decisions` (stronger depth, steel-manning, and synthesis pressure in aggressive mode).
- `ecosystems/<id>/agents/<agent-id>/notebook.jsonl` - durable notebook entries
- `ecosystems/<id>/agents/<agent-id>/constitution.md` - mutable constitution with frontmatter

## Runtime Invariants
- Events are append-only and hash linked (`prev_hash`, `record_hash`).
- Canonical JSON serialization is required for integrity.
- Paths must remain under ecosystem storage firewall boundaries.
- Evaluation ledger is not writable by standard agent action paths.

## Operational Commands
- Run tests: `uv run pytest -q`
- Verify chains:
  - `python -m tools.verify_chains --ecosystem alpha`
  - `python -m tools.verify_chains --ecosystem beta`
- Export sqlite for dashboards:
  - `python -m tools.export_to_sqlite --db dashboard.db --base-dir .`
- Periodic batch ETL (Parquet tabular + separate research JSONL; requires `uv sync --extra etl`):
  - `uv run python -m tools.batch_etl --base-dir . --out-dir ./etl_warehouse`
- Notebook sharing + overlap proxy for “net new phrasing” vs corpus (and optional `action.executed` raw text): `python -m tools.notebook_novelty --ecosystem beta --base-dir . --export-dir ./share_exports` (add `--include-executed-raw` to widen the source pool).

## Coding Standards
- Prefer explicit typed payloads over freeform dictionaries where practical.
- Keep backward-compatible defaults when introducing new runtime flags.
- Add focused tests for each new control path (validation, masks, verifier events).
- Avoid silent fallback behavior for safety-critical or contract-critical features.

## Current Wave Priorities
1. Wave 0 stabilization and baseline pass gates.
2. Contract hardening (write-path validation and schema exports).
3. Memory, safety, observability, then optional formalism features behind flags.

## Out of Scope (until stabilized)
- Unbounded runtime complexity growth.
- Experimental formalism changes without contract and safety gates first.
- Breaking changes to ledger schema without migration strategy.
