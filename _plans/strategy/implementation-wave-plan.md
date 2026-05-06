# Implementation Wave Plan (Post-Strategy Approval)

This plan is for execution **after** the strategy package is approved.

## Scope label

- `[flagged runtime later]` for Waves E1-E4

## Execution policy

- Each wave is PR-sized.
- One primary risk surface per wave.
- No default flips without acceptance and rollback gates passing.

## Wave E1: Memory exposure controls (`[flagged runtime later]`)

### Goal

Add opt-in context bridges (peer/forum/retrieval prompt sections) with strict caps and provenance labels.

### Candidate files

- `agent/state_builder.py`
- `agent/executor.py`
- `schemas/events.py` (if new metadata payloads are needed)
- run-config documentation surfaces

### Tests/gates

- New unit tests for:
  - cap enforcement,
  - provenance tag presence,
  - graceful fallback when sources absent.
- `uv run pytest -q`
- `python -m tools.verify_chains --ecosystem alpha`
- `python -m tools.verify_chains --ecosystem beta`
- `python -m tools.check_run_config_hashes --base-dir .`

### Rollback triggers

- token/latency overrun,
- novelty regressions,
- unverifiable context injections.

## Wave E2: Offline multi-run map-reduce protocol surfaces (`[flagged runtime later]`)

### Goal

Add explicit handoff schema and supporting event conventions for lead/tasker/checker across separate runs.

### Candidate files

- `agent/executor.py`
- `forums/*`
- `schemas/events.py`
- docs + prompt pack (`prompts/sage_team_prompts.json`)

### Tests/gates

- schema validation tests for handoff payloads,
- forum/public dual-write consistency checks,
- checker-verdict required-path tests.

### Rollback triggers

- unresolved conflict growth,
- invalid handoff payloads,
- safety fail-budget increase.

## Wave E3: Ecosystem ID generalization (`[flagged runtime later]`)

### Goal

Move from `Literal["alpha", "beta"]` to validated ID grammar with alias compatibility.

### Candidate files

- `infra/storage.py`
- `tools/verify_chains.py`
- `infra/s3_sync.py`
- `tools/export_to_sqlite.py`
- `tools/batch_etl.py`

### Tests/gates

- storage traversal/firewall tests for new ID grammar,
- alias resolution tests,
- run-lock isolation tests,
- S3 prefix/sync-state compatibility tests,
- ETL/export ecosystem attribution checks.

### Rollback triggers

- path-resolution ambiguity,
- chain verification mismatch on legacy IDs,
- S3/ETL naming collisions.

## Wave E4: Promotion defaults and deprecation (`[flagged runtime later]`)

### Goal

Promote approved conventions to defaults, then deprecate legacy assumptions in stages.

### Candidate actions

- update default run configs,
- update README/AGENTS operational commands and examples,
- mark deprecations with transition windows.

### Tests/gates

- full regression suite + chain checks + hash checks,
- migration rehearsal checklist pass,
- rollback rehearsal dry-run pass.

### Rollback triggers

- operator confusion from ambiguous defaults,
- dashboard/export breakage,
- missed deprecation compatibility windows.

## Global acceptance checklist per wave

- Functional tests pass.
- Chain integrity remains valid.
- Hash integrity checks pass.
- Safety outcomes remain within budget.
- Token/latency remains within wave scorecard.
- Rollback procedure tested, not just written.

## Global non-goals during these waves

- No in-place rewrite of historical ledger lines.
- No undocumented defaults.
- No irreversible migration without rehearsal evidence.

## Acceptance and rollback summary

- **Acceptance gate:** each wave clears functional, integrity, safety, and budget checks.
- **Rollback gate:** any integrity/safety breach or migration ambiguity triggers wave-level revert.
