# Ecosystem Soft Unification Roadmap

This roadmap replaces hard alpha/beta operational dependence with a logical primary ecosystem plus optional sandboxes, without breaking historical ledgers.

## Scope label

- Stage 1: `[docs-only now]`
- Stages 2-4: `[flagged runtime later]`

## Objectives

- Preserve verifiability of existing `alpha` and `beta` data.
- Reduce operational overhead from fixed dual-environment assumptions.
- Introduce a flexible ecosystem ID model with strict safety contracts.

## Target topology

- Primary: `ecosystems/prod`
- Optional sandboxes: `ecosystems/sandbox-*`
- Legacy aliases retained temporarily:
  - `alpha -> prod` (or designated sandbox during migration rehearsal)
  - `beta -> prod` or staged parallel sandbox, based on rehearsal outcome

## Compatibility contract (must be approved before code changes)

### 1) Ecosystem ID grammar

- allowed chars: `[a-z0-9-]`
- must start with letter
- max length: 32
- reserved IDs: `tmp`, `test`, `none`, `null`, `default`

### 2) Alias resolution

- aliases must be explicit in config, never implicit from string heuristics.
- alias table must be versioned and audited.
- tool outputs must include both requested ID and resolved ID.

### 3) Chain verification behavior

- `tools.verify_chains` must operate on resolved physical path.
- legacy `alpha`/`beta` verification must continue to work throughout transition.
- no in-place rename of historical directories.

### 4) S3/offload naming

- S3 prefixes must include resolved ecosystem ID.
- `.sync_state` naming must remain collision-safe across aliases.
- migration requires dry-run sync verification before cutover.

### 5) ETL/export naming

- SQLite/Parquet exports must record resolved ecosystem ID and optional logical alias.
- no schema regressions for existing dashboards.

### 6) Corpus scoping

- corpus path remains `corpora/<ecosystem_id>` with explicit mapping for aliases.
- fallback behavior must be explicit and logged.

### 7) Run-lock isolation

- lock files remain per-agent and per-resolved ecosystem path.
- migration rehearsal must test stale-lock recovery across alias resolution paths.

### 8) Forbidden actions

- never rewrite or reorder existing ledger lines.
- never silently repoint verification to a different physical directory.
- never drop alias provenance in audit outputs.

## Staged path

### Stage 1 (`[docs-only now]`)

- publish this contract and migration checklists.
- define canonical target IDs and alias table format.

### Stage 2 (`[flagged runtime later]`)

- expand storage validation to accept grammar-based IDs.
- preserve firewall and run-lock invariants.
- keep `alpha`/`beta` support as aliases.

### Stage 3 (`[flagged runtime later]`)

- migrate run-config defaults toward `prod` + optional `sandbox-*`.
- update tool docs/examples.

### Stage 4 (`[flagged runtime later]`)

- deprecate hard-coded alpha/beta assumptions only after rehearsal and sign-off.

## Rollback rehearsal criteria

A rehearsal is pass only if all checks succeed:

- `pytest` full suite passes.
- chain verification passes for legacy and target IDs.
- hash checks pass for all run configs.
- S3 dry-run + restore consistency check passes.
- ETL/export outputs preserve expected ecosystem attribution.
- stale-run-lock recovery behaves correctly under alias resolution.

## Rollback triggers

- chain mismatch or unexpected resolved path,
- S3 prefix/sync-state collision,
- dashboard/export attribution ambiguity,
- safety/control behavior divergence caused by ID resolution.

## Revert protocol

1. freeze writes to target ecosystem IDs.
2. restore prior alias mapping.
3. rerun chain verification on legacy paths.
4. archive migration logs and incident notes.
5. reopen only after corrective checklist sign-off.

## Acceptance and rollback summary

- **Acceptance gate:** compatibility contract approved and rehearsal checks pass before any runtime migration.
- **Rollback gate:** any path-resolution ambiguity, ledger mismatch, or attribution collision triggers immediate revert.
