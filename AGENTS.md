# AGENTS.md

## Project Purpose
- `stateful-indecision` is a ledger-first agent research runtime.
- The core guarantee is append-only, hash-chained event logs with deterministic verification.
- All implementation waves (0–5, E1–E4) are complete. The project is in post-pipeline steady-state operation with a 417+ test regression floor.

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
- Ecosystem IDs must pass the validated grammar (lowercase alphanumeric + hyphens, no reserved words).

## Operational Commands
- Run tests: `uv run pytest -q`
- Verify chains (supports any validated ecosystem ID):
  - `uv run python -m tools.verify_chains --ecosystem alpha`
  - `uv run python -m tools.verify_chains --ecosystem beta`
- Export sqlite for dashboards:
  - `uv run python -m tools.export_to_sqlite --db dashboard.db --base-dir .`
- Export event schemas (regenerate after payload model changes):
  - `uv run python -m tools.export_event_schemas`
- Periodic batch ETL (Parquet tabular + separate research JSONL; requires `uv sync --extra etl`):
  - `uv run python -m tools.batch_etl --base-dir . --out-dir ./etl_warehouse`
- Verify run-config hashes against tracked files:
  - `uv run python -m tools.check_run_config_hashes --base-dir .`
  - `uv run python -m tools.sync_run_config_hashes --base-dir .`  (update hashes after modifying tracked files)
- Notebook sharing + overlap proxy for "net new phrasing" vs corpus (and optional `action.executed` raw text): `uv run python -m tools.notebook_novelty --ecosystem beta --base-dir . --export-dir ./share_exports` (add `--include-executed-raw` to widen the source pool).

## Coding Standards
- Prefer explicit typed payloads over freeform dictionaries where practical.
- Keep backward-compatible defaults when introducing new runtime flags.
- Add focused tests for each new control path (validation, masks, verifier events).
- Avoid silent fallback behavior for safety-critical or contract-critical features.
- Use fixed-shape Pydantic models; no `extra="allow"` for stable payloads.
- Boolean config fields must be strictly validated — no truthy/falsy shortcuts (`isinstance(x, bool)` only).
- Cross-validate related config fields to prevent inconsistent state (e.g. cap > 0 requires enable flag).
- Docstrings must match actual code flow — audit after refactors.
- Documentation must not overstate what the code actually does.
- No default flips without acceptance AND rollback gates passing.

## Current Wave Priorities
All implementation waves (0–5, E1–E4) are complete. Post-pipeline priorities:
1. Monitor promoted defaults across live runs for unexpected drift.
2. Enforce deprecation transition windows per the E4 schedule.
3. Collect scorecard evidence for potential v2 scope decisions.
4. Maintain the 417+ test baseline as a regression floor.

## Out of Scope (until v2)
- Unbounded runtime complexity growth.
- Breaking changes to ledger schema without migration strategy.
- Default flips for experimental features (`enable_pi_reason_then_action`, `emit_latent_reasoning_events`) without dedicated scorecard evidence.
- Promoting `verifier_mode` from `"warn"` to `"enforce"` without operator acceptance testing.
