# Wave E3 Ready-to-Execute Checklist

Scope label: `[flagged runtime later]`  
Wave: `E3 — Ecosystem ID generalization`  
Status: Execution checklist (implementation-facing)  
Risk level: **HIGH** — infrastructure-level changes to path resolution and data integrity boundaries

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/strategy/implementation-wave-plan.md`](/home/ubuntu/stateful-indecision/_plans/strategy/implementation-wave-plan.md) (lines 70-96)
- Soft-unification contract:
  - [`_plans/strategy/ecosystem-soft-unification.md`](/home/ubuntu/stateful-indecision/_plans/strategy/ecosystem-soft-unification.md)

## A) Scope lock and success criteria

- [ ] Confirm E3 scope is limited to ID grammar generalization and alias compatibility — no runtime behavior changes, no topology migration, no new data surfaces.
- [ ] Confirm E3 non-goals:
  - [ ] no directory renames of existing `alpha`/`beta` ecosystems
  - [ ] no promotion of `prod`/`sandbox-*` defaults (deferred to E4)
  - [ ] no changes to ledger event schemas or hash-chain logic
  - [ ] no deprecation of `alpha`/`beta` (deferred to E4)
- [ ] Record baseline thresholds for this wave:
  - [ ] all 273 existing tests pass before any changes
  - [ ] `verify_chains` passes for both `alpha` and `beta`
  - [ ] `check_run_config_hashes` passes
  - [ ] no firewall or path-resolution regressions

## B) ID grammar definition

- [ ] Define `EcosystemId` validated type with regex pattern `^[a-z][a-z0-9_-]{0,62}$`.
- [ ] Confirm grammar aligns with soft-unification contract: `[a-z0-9-]`, starts with letter, max length 63 (contract says 32 — reconcile and document chosen limit).
- [ ] Define reserved ID set and reject at validation time: `tmp`, `test`, `none`, `null`, `default`.
- [ ] Replace `Literal["alpha", "beta"]` type annotation in `EcosystemStorage.__init__` with validated grammar.
- [ ] Replace hardcoded `{"alpha", "beta"}` membership check with regex + reserved-word validation.
- [ ] Raise `ValueError` with descriptive message for IDs that fail validation (preserving current error contract).

## C) Alias compatibility layer

- [ ] Define alias mapping structure: `{"alpha": "alpha", "beta": "beta"}` as identity aliases initially (no repointing until E4).
- [ ] Decide alias resolution location: recommend resolving at `EcosystemStorage.__init__` entry point so all downstream paths use the resolved ID.
- [ ] Ensure alias resolution is explicit — never infer aliases from string heuristics (per soft-unification contract).
- [ ] Store both requested ID and resolved ID on the storage instance for audit logging.
- [ ] Ensure `alpha` and `beta` continue to pass validation and resolve to themselves.
- [ ] Document alias configuration surface (config file, environment variable, or code constant) — prefer a single source of truth.

## D) Storage and path resolution implementation

- [ ] Update `EcosystemStorage.__init__` to use validated ID grammar instead of `Literal`.
- [ ] Verify `self.ecosystem_dir` resolves correctly for new-grammar IDs (e.g., `my-project`, `sandbox-01`, `prod`).
- [ ] Verify `self.base_dir / "ecosystems" / ecosystem_id` produces valid, non-colliding paths for all grammar-legal IDs.
- [ ] Verify `resolve()` firewall check remains intact: `candidate.startswith(ecosystem_dir)` must hold for all new IDs.
- [ ] Verify `corpus_dir()` path (`corpora/<ecosystem_id>`) resolves correctly and stays within `base_dir`.
- [ ] Verify `acquire_run_lock()` lock file naming (`.run.lock.<agent_id>`) is unaffected by ID generalization.
- [ ] Confirm `agent_dir()`, `agent_constitution()`, `agent_notebook()`, `agent_research_dir()` all resolve correctly under new IDs.
- [ ] Confirm directory auto-creation (`mkdir(parents=True, exist_ok=True)`) works for new IDs without side effects.

## E) Tool CLI and pipeline updates

### `tools/verify_chains.py`
- [ ] Remove or relax any implicit `alpha`/`beta` assumption in `--ecosystem` argument (currently no `choices` constraint — verify it accepts arbitrary valid IDs).
- [ ] Verify path construction `base / "ecosystems" / args.ecosystem` is safe for grammar-legal IDs.
- [ ] Add input validation: reject IDs that fail the grammar check before constructing paths.

### `infra/s3_sync.py`
- [ ] Remove `choices=["alpha", "beta"]` from `--ecosystem` argparse argument.
- [ ] Add grammar validation for the `--ecosystem` CLI argument.
- [ ] Verify `_ecosystem_s3_prefix()` produces valid, collision-free S3 prefixes for new IDs.
- [ ] Verify `.sync_state/<ecosystem_id>.json` naming remains collision-safe across all grammar-legal IDs.
- [ ] Verify `SyncState.ecosystem_id` field works with arbitrary valid IDs.

### `tools/export_to_sqlite.py`
- [ ] Verify `ecosystems_dir.rglob("*.jsonl")` correctly discovers ledgers under new ecosystem directory names.
- [ ] Verify `ecosystem_id` field in SQLite tables correctly records the ID from event data (no hardcoded filtering).
- [ ] Confirm no hardcoded `alpha`/`beta` assumptions in export logic.

### `tools/batch_etl.py`
- [ ] Verify `_iter_ecosystem_jsonl()` and `_iter_research_json()` iterate all ecosystem directories without ID filtering.
- [ ] Verify hive-partitioned Parquet `partition_cols=["ecosystem_id"]` handles new IDs without filesystem-unsafe characters.
- [ ] Confirm `_event_row()`, `_run_row()`, `_artifact_meta_row()` propagate arbitrary ecosystem IDs correctly.

## F) Safety and firewall invariants

- [ ] **Path traversal**: IDs containing `..`, `/`, `\`, or null bytes must be rejected by the grammar — verify regex excludes these.
- [ ] **Firewall boundary**: `resolve()` must still block escapes from `ecosystem_dir` for all grammar-legal IDs.
- [ ] **Cross-ecosystem isolation**: an ID like `alpha-copy` must not resolve to paths overlapping `alpha`.
- [ ] **Corpus firewall**: `corpus_dir()` path must stay within `base_dir` for all valid IDs.
- [ ] **Run-lock isolation**: locks for ecosystem `foo` must not collide with locks for ecosystem `foo-bar`.
- [ ] **Evaluation ledger protection**: `blocked_for_agent()` behavior must remain unchanged regardless of ecosystem ID.
- [ ] **No new write paths**: E3 must not introduce any new file-write locations beyond what the grammar change requires.
- [ ] **Reserved ID rejection**: verify that `EcosystemStorage("tmp", base)` raises `ValueError`.

## G) Test implementation

### ID grammar validation tests
- [ ] Valid IDs accepted: `alpha`, `beta`, `prod`, `sandbox-01`, `my-project`, `a` (min length), 63-char ID (max length).
- [ ] Invalid IDs rejected: empty string, starts with digit (`0bad`), starts with hyphen (`-bad`), contains uppercase (`Alpha`), contains dots (`a.b`), contains slashes (`a/b`), 64-char ID (exceeds max), reserved IDs (`tmp`, `test`, `none`, `null`, `default`).
- [ ] Boundary: single-char ID `a` (valid), 63-char ID (valid), 64-char ID (invalid).

### Alias compatibility tests
- [ ] `alpha` resolves to `alpha` and works end-to-end.
- [ ] `beta` resolves to `beta` and works end-to-end.
- [ ] Storage created with alias produces identical directory structure to storage created with resolved ID.

### Path resolution and firewall tests (extend `test_firewall.py`)
- [ ] `EcosystemStorage("my-eco", tmp_path)` resolves all paths under `ecosystems/my-eco/`.
- [ ] Path traversal blocked for new-grammar IDs (same escapes as existing tests).
- [ ] Cross-ecosystem escape blocked: storage for `eco-a` cannot resolve paths in `eco-b`.
- [ ] `corpus_dir()` resolves correctly for new IDs.
- [ ] Run-lock isolation verified across new-grammar IDs.

### S3/sync compatibility tests (extend `test_s3_sync.py`)
- [ ] `SyncState` round-trips with new-grammar ecosystem IDs.
- [ ] `_ecosystem_s3_prefix()` produces correct prefixes for new IDs.
- [ ] `.sync_state` file naming works for new IDs.
- [ ] `syncable_ledger_paths()` stays within firewall for new IDs.

### Regression tests
- [ ] All existing `test_firewall.py` tests pass unchanged (backward compat).
- [ ] All existing `test_s3_sync.py` tests pass unchanged.
- [ ] `EcosystemStorage("alpha", base)` and `EcosystemStorage("beta", base)` behavior is identical to pre-E3.

## H) Validation gates (must pass)

- [ ] `uv run pytest -q` — all tests pass including new E3 tests.
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] review schema diff for intended-only changes
- [ ] Manual verification: create a temporary ecosystem with a new-grammar ID, write a test event, verify chain, delete.

## I) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] total test count and pass rate
  - [ ] `verify_chains` output for `alpha` and `beta`
  - [ ] path-resolution test coverage for new ID patterns
  - [ ] firewall test coverage for edge-case IDs
- [ ] Confirm zero behavioral delta for `alpha`/`beta` ecosystems.
- [ ] Confirm S3 prefix generation produces no collisions for sample ID set.
- [ ] Mark decision outcome: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback steps before merge:
  - [ ] revert `EcosystemStorage.__init__` to `Literal["alpha", "beta"]`.
  - [ ] restore `choices=["alpha", "beta"]` in `s3_sync.py` CLI.
  - [ ] remove new test files or test cases.
- [ ] Define trigger thresholds:
  - [ ] any path-resolution ambiguity or firewall bypass
  - [ ] chain verification mismatch on legacy `alpha`/`beta` IDs
  - [ ] S3 prefix or `.sync_state` naming collision
  - [ ] ETL/export ecosystem attribution ambiguity
  - [ ] any existing test failure introduced by E3 changes
- [ ] Validate rollback restores exact pre-E3 behavior — no residual grammar artifacts.
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory gates pass (section H).
- [ ] `alpha` and `beta` ecosystems behave identically to pre-E3.
- [ ] Arbitrary grammar-legal ecosystem IDs can be created, used, and verified.
- [ ] No path traversal, firewall bypass, or cross-ecosystem data leak for any grammar-legal ID.
- [ ] Reserved IDs are rejected at construction time.
- [ ] All tools (`verify_chains`, `export_to_sqlite`, `batch_etl`, `s3_sync`) handle arbitrary valid IDs.
- [ ] Wave scorecard complete with acceptance/rollback evidence.
- [ ] Soft-unification contract (sections 1-8) honored — no forbidden actions violated.
