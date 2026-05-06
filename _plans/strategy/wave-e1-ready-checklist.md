# Wave E1 Ready-to-Execute Checklist

Scope label: `[flagged runtime later]`  
Wave: `E1 — Memory exposure controls`  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/strategy/implementation-wave-plan.md`](/home/ubuntu/stateful-indecision/_plans/strategy/implementation-wave-plan.md)

## A) Scope lock and success criteria

- [ ] Confirm E1 is opt-in only and does not change defaults.
- [ ] Confirm E1 non-goals:
  - [ ] no ecosystem ID generalization
  - [ ] no scheduler-level multi-agent runtime
  - [ ] no Level-2/3 training automation
- [ ] Record baseline thresholds for this wave:
  - [ ] safety fail budget
  - [ ] novelty proxy threshold
  - [ ] token/latency budget ceiling
  - [ ] expected action-distribution drift bounds

## B) Config contract definition

- [ ] Define new/updated run-config keys for memory exposure toggles and caps.
- [ ] Set deterministic defaults (`off` or `0`) for all E1 keys.
- [ ] Define invalid-value handling policy (explicit fail or explicit fallback).
- [ ] Document key semantics and constraints in strategy docs and/or operator docs.

## C) Provenance and cap spec

- [ ] Define required provenance fields per injected context segment:
  - [ ] source ledger/path
  - [ ] source event IDs
  - [ ] source agent IDs (where applicable)
- [ ] Define per-segment and total prompt budget caps.
- [ ] Define deterministic truncation rules and markers.

## D) State snapshot implementation

- [ ] Add optional peer context extraction (capped, provenance-tagged).
- [ ] Add optional forum preview/digest extraction (capped, provenance-tagged).
- [ ] Wire retrieval context inclusion path for prompt use when enabled.
- [ ] Ensure empty/missing sources degrade gracefully without exceptions.

## E) Executor prompt assembly implementation

- [ ] Inject optional context blocks only when enabled and non-empty.
- [ ] Keep prompt block ordering deterministic.
- [ ] Add explicit block headers for each memory source.
- [ ] Preserve existing default prompt behavior when all E1 toggles are off.

## F) Safety and firewall invariants

- [ ] Verify all new reads remain under storage firewall constraints.
- [ ] Verify no new write paths are introduced by E1 memory features.
- [ ] Verify evaluation-ledger write protections remain unchanged.

## G) Test implementation

- [ ] Add unit tests for cap enforcement (including boundary values).
- [ ] Add tests for provenance field presence and structure.
- [ ] Add tests for graceful fallback with empty/missing data.
- [ ] Add tests for prompt block inclusion/exclusion logic.
- [ ] Add regression tests proving default behavior remains unchanged.

## H) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] review schema diff for intended-only changes

## I) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] safety outcomes (`pass`/`warn`/`fail`)
  - [ ] novelty proxy
  - [ ] token/latency
  - [ ] action distribution
- [ ] Compare observed deltas against expected deltas.
- [ ] Mark decision outcome: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback steps before merge.
- [ ] Define trigger thresholds (safety, novelty, latency, attribution failures).
- [ ] Validate rollback can disable E1 entirely via config.
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory gates pass.
- [ ] No default behavior changes when E1 flags are off.
- [ ] E1 fully controllable via explicit config toggles.
- [ ] Wave scorecard complete with acceptance/rollback evidence.

