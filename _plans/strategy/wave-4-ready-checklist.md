# Wave 4 Ready-to-Execute Checklist

Scope label: `[tools-only, non-invasive]`  
Wave: `4 — Observability and Evolution`  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec:
  - [`_plans/waves/wave-4-observability-and-evolution.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-4-observability-and-evolution.md)
- Training protocol reference:
  - [`_plans/strategy/training-protocol.md`](/home/ubuntu/stateful-indecision/_plans/strategy/training-protocol.md)

## A) Scope lock and success criteria

- [ ] Confirm Wave 4 is tools-only and does not modify runtime, safety, or ledger write paths.
- [ ] Confirm Wave 4 non-goals:
  - [ ] no runtime behavior changes
  - [ ] no new ledger event types
  - [ ] no safety gate modifications
  - [ ] no Level 2/3 training automation (Level 1 docs only)
- [ ] Record baseline thresholds for this wave:
  - [ ] existing query count in `grafana_starter_queries.sql` (currently 9)
  - [ ] existing panel count in `grafana_dashboard_template.json` (currently 5)
  - [ ] existing trajectory export field set (currently 13 fields)
  - [ ] test count baseline (currently 245 passing)

## B) Metrics extension spec (metrics-worker)

- [ ] Audit existing SQL queries 8 and 9 in `grafana_starter_queries.sql`:
  - [ ] Query 8 already provides `latency_ms`, `tokens_in`, `tokens_out`, `tokens_total` from `action.executed` events.
  - [ ] Query 9 already provides `stop_reason` distribution by ecosystem and agent.
- [ ] Add or extend SQL queries for the following required metrics:
  - [ ] p50/p95 decision latency (per ecosystem, per agent, overall). SQLite lacks native percentile functions; use `ORDER BY + LIMIT + OFFSET` approximation or document Grafana transformation.
  - [ ] Tokens per decision (total, in, out) with aggregation by ecosystem and agent.
  - [ ] Stop reason distribution over time (time-bucketed, not just aggregate).
  - [ ] Action mix over time (top_action distribution per time bucket).
- [ ] Verify all new queries validate against a freshly exported `dashboard.db`:
  - [ ] `python -m tools.export_to_sqlite --db dashboard.db --base-dir .`
  - [ ] Run each new query against the DB to confirm no schema mismatches.
- [ ] Confirm new queries use only columns already present in the `events` table schema (no new columns required in `export_to_sqlite.py`).
- [ ] If `export_to_sqlite.py` schema changes are needed, add backward-compatible `ALTER TABLE` or `CREATE TABLE IF NOT EXISTS` patterns only.

## C) Dashboard and Grafana implementation (metrics-worker)

- [ ] Add new dashboard panels to `grafana_dashboard_template.json`:
  - [ ] Latency distribution panel (p50/p95 from query 8, with Grafana transformations).
  - [ ] Tokens per decision panel (timeseries or stat panel).
  - [ ] Stop reason mix panel (pie chart or grouped bar from query 9).
  - [ ] Action mix over time panel (stacked bar or timeseries).
- [ ] Assign non-conflicting panel IDs (existing panels use IDs 1–5).
- [ ] Place new panels with non-overlapping `gridPos` (existing panels occupy y=0 through y=32).
- [ ] Update `tools/README-Grafana.md`:
  - [ ] Document each new panel and its source query.
  - [ ] Include Grafana transformation steps for percentile panels.
  - [ ] Keep existing setup instructions intact.
- [ ] Validate dashboard JSON is syntactically valid (`python -c "import json; json.load(open('tools/grafana_dashboard_template.json'))"`)

## D) Trajectory export spec (trajectory-worker)

- [ ] Audit existing `tools/export_trajectories.py`:
  - [ ] Currently exports 13 fields per trajectory row: `ecosystem_id`, `agent_id`, `decision_event_id`, `snapshot_id`, `top_action`, `sub_action`, `sample_seed`, `raw_output`, `structured_output`, `side_effects`, `tokens_in`, `tokens_out`, `stop_reason`, `wall_time`.
  - [ ] Links decisions to executions via `decision_event_id`.
- [ ] Define and document the trajectory JSONL schema:
  - [ ] Field names, types, and semantics.
  - [ ] Nullable fields and when they may be null.
  - [ ] Relationship between trajectory rows and ledger events.
- [ ] Extend export if needed for offline RL / preference training:
  - [ ] Add `evaluation_outcome` field from evaluation ledger (if available per decision).
  - [ ] Add `decision_number` / `decision_index` for trajectory ordering.
  - [ ] Add `latency_ms` computed from execution metrics.
  - [ ] Add `run_config_version` for provenance.
- [ ] Ensure backward compatibility: new fields are optional or have safe defaults.
- [ ] Add `--format` flag documentation (JSONL is default; note that HuggingFace datasets can load JSONL directly).
- [ ] Verify export runs cleanly on both alpha and beta ecosystems:
  - [ ] `python -m tools.export_trajectories --ecosystem alpha --base-dir . --output /tmp/test_alpha.jsonl`
  - [ ] `python -m tools.export_trajectories --ecosystem beta --base-dir . --output /tmp/test_beta.jsonl`

## E) Adaptation documentation (adaptation-worker)

- [ ] Write or extend Level 1 checkpoint tuning documentation covering:
  - [ ] **Metric collection**: which metrics to gather before/after a mutation (action mix, novelty proxy, safety outcomes, token/latency).
  - [ ] **Rule definition**: how to define a mutation rule (prompt edit, action mask adjustment, config convention change).
  - [ ] **Mutation application**: step-by-step procedure (checkpoint → collect → apply → gate → accept/revert).
  - [ ] **Rollback procedure**: how to revert a failed mutation using config hash restoration.
- [ ] Reference concrete tools for each step:
  - [ ] `python -m tools.check_run_config_hashes --base-dir .` (checkpoint)
  - [ ] `python -m tools.export_to_sqlite --db dashboard.db --base-dir .` (metrics)
  - [ ] `python -m tools.sync_run_config_hashes --base-dir .` (post-mutation hash sync)
  - [ ] `uv run pytest -q` and chain verification (gates)
- [ ] Include a worked example of one Level 1 mutation cycle.
- [ ] Cross-reference `_plans/strategy/training-protocol.md` for acceptance gates and artifact requirements.
- [ ] Confirm documentation does not prescribe Level 2/3 automation (out of scope for Wave 4).

## F) Safety and non-invasiveness invariants

- [ ] Verify no new runtime code paths are introduced (all changes are in `tools/` or `_plans/`).
- [ ] Verify no modifications to:
  - [ ] `core/writer.py`
  - [ ] `core/verifier.py`
  - [ ] `safety/*`
  - [ ] `agent/*`
  - [ ] `infra/storage.py`
- [ ] Verify trajectory export reads ledgers read-only (no writes to ecosystem directories).
- [ ] Verify Grafana queries are read-only SQL (`SELECT` only, no `INSERT`/`UPDATE`/`DELETE`).
- [ ] Verify evaluation ledger write protections remain unchanged.
- [ ] Confirm all new tools are non-invasive to runtime paths (per wave spec).

## G) Test implementation

- [ ] Add tests for trajectory export:
  - [ ] Round-trip: synthetic events → export → verify field presence and structure.
  - [ ] Empty ecosystem: export produces empty output without error.
  - [ ] Missing execution events: decisions without matching `action.executed` degrade gracefully.
  - [ ] Ecosystem filtering: only events for the requested ecosystem appear in output.
- [ ] Add tests for new/extended SQL queries:
  - [ ] Latency query returns expected columns against a test `dashboard.db`.
  - [ ] Token aggregation query produces correct sums on synthetic data.
  - [ ] Stop reason query groups correctly.
  - [ ] Action mix time-bucket query produces expected bucketing.
- [ ] Add validation for dashboard template JSON:
  - [ ] Valid JSON with expected top-level keys.
  - [ ] No duplicate panel IDs.
  - [ ] All panel SQL references resolve against `events`/`runs`/`artifacts` schema.
- [ ] Ensure no existing tests are broken (regression baseline: 245 tests).

## H) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Grafana SQL validation against `dashboard.db`:
  - [ ] Export fresh DB: `python -m tools.export_to_sqlite --db dashboard.db --base-dir .`
  - [ ] Run each query in `grafana_starter_queries.sql` against DB without errors.
- [ ] Trajectory export validation:
  - [ ] `python -m tools.export_trajectories --ecosystem alpha --base-dir . --output /tmp/validate_alpha.jsonl`
  - [ ] `python -m tools.export_trajectories --ecosystem beta --base-dir . --output /tmp/validate_beta.jsonl`
  - [ ] Verify output is valid JSONL (each line parses as JSON).
- [ ] If any tracked files were modified, sync hashes:
  - [ ] `python -m tools.sync_run_config_hashes --base-dir .`
  - [ ] Re-run `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] Review schema diff for intended-only changes.

## I) Wave scorecard evidence capture

- [ ] Record delivery status for each worker:
  - [ ] metrics-worker: SQL queries extended [ ] yes [ ] no
  - [ ] metrics-worker: dashboard panels added [ ] yes [ ] no
  - [ ] trajectory-worker: export tool validated [ ] yes [ ] no
  - [ ] trajectory-worker: schema documented [ ] yes [ ] no
  - [ ] adaptation-worker: Level 1 docs complete [ ] yes [ ] no
- [ ] Record acceptance criteria from wave spec:
  - [ ] SQL queries support latency, token, stop-reason, and action-mix metrics: [ ] pass [ ] fail
  - [ ] Dashboard template and README aligned with SQL: [ ] pass [ ] fail
  - [ ] Trajectory export tool exists with documented schema: [ ] pass [ ] fail
  - [ ] Level 1 adaptation workflow docs complete: [ ] pass [ ] fail
  - [ ] Grafana SQL validates against `dashboard.db`: [ ] pass [ ] fail
  - [ ] Chain verification for alpha and beta passes: [ ] pass [ ] fail
- [ ] Record inter-wave role handoff:
  - [ ] Intake role (from Wave 3): ___
  - [ ] Outgoing role (to Wave 5): ___ (candidate: `systems-integrator`, `formalism-curator`, or `compatibility-steward`)
- [ ] Compare observed test count against baseline (245).
- [ ] Mark decision outcome: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback steps before merge:
  - [ ] Keep old `grafana_starter_queries.sql` versioned for quick revert.
  - [ ] Keep old `grafana_dashboard_template.json` versioned for quick revert.
  - [ ] Trajectory export is additive; rollback = remove new file or revert to prior version.
  - [ ] Adaptation docs are additive; rollback = remove documentation files.
- [ ] Define trigger thresholds:
  - [ ] Dashboard JSON fails to import in Grafana.
  - [ ] New SQL queries fail against exported `dashboard.db`.
  - [ ] Trajectory export produces invalid JSONL or crashes on real data.
  - [ ] Any existing test regression.
- [ ] Validate rollback does not require runtime changes (tools-only wave).
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory validation gates pass (section H).
- [ ] No runtime code modified (tools and docs only).
- [ ] All acceptance criteria from wave spec met (section I).
- [ ] Wave scorecard complete with acceptance/rollback evidence.
- [ ] Inter-wave role handoff recorded for Wave 5.
- [ ] Test count >= baseline (245).
