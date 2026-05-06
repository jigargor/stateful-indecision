# Wave 1 Ready-to-Execute Checklist

Scope label: `[contracts-and-blueprint]`  
Wave: `1 — Contracts and Blueprint`  
Handoff role: `schema-architect` (types and validation first)  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec:
  - [`_plans/waves/wave-1-contracts-and-blueprint.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-1-contracts-and-blueprint.md)

## A) Scope lock and success criteria

- [ ] Confirm Wave 1 is strictly about hardening write paths and output contracts.
- [ ] Confirm Wave 1 non-goals:
  - [ ] no new runtime features or toggles beyond validation
  - [ ] no memory exposure changes (Wave E1 scope)
  - [ ] no seed file modifications unless required by validation schema
  - [ ] no changes to prompt assembly or decision sampling logic
- [ ] Record baseline thresholds for this wave:
  - [ ] existing test count and pass rate
  - [ ] current `KNOWN_EVENT_PAYLOAD_MODELS` coverage (currently 12 event types)
  - [ ] schema export count (currently 9 files in `schemas/generated/`)
  - [ ] unvalidated event types passing through writer (forum events, `indulge.*`)

## B) Config contract definition

- [ ] Audit `run_config*.json` for all fields that influence write paths.
- [ ] Verify `load_run_config` in `agent/runner.py` rejects hash mismatches with explicit `ValueError`.
- [ ] Verify boolean config values are validated strictly (not truthy strings) per Wave 0 lesson.
- [ ] Confirm `tool_allowlist` defaults to empty list (not `None` ambiguity) — test exists in `test_wave1_contracts.py`.
- [ ] Document any new config semantics introduced by validation tightening (should be none — only enforcement changes).

## C) Payload validation coverage

- [ ] Confirm `validate_known_event_payload` is called in `core/writer.py:append()` (line 103) for ALL writes.
- [ ] Audit all `ChainWriter.append` call sites and verify payloads match `KNOWN_EVENT_PAYLOAD_MODELS`:
  - [ ] `agent/decision.py` — `agent.state.snapshotted`, `agent.decision.proposed`, `agent.decision.taken`, `agent.latent.reasoned`, `action.executed`
  - [ ] `agent/executor.py` — `agent.latent.reasoned`, `agent.constitution.revised`, `agent.artifact.stored`, `agent.skill.authored`, `indulge.requested`, `indulge.responded`
  - [ ] `agent/runner.py` — `run.completed`, plus initialization events
  - [ ] `agent/notebook.py` — `agent.notebook.appended`
  - [ ] `forums/base.py` via `_dual_write` — `townhall.*`, `roundtable.*`, `commons.*`
- [ ] Identify event types that bypass validation (unknown to `KNOWN_EVENT_PAYLOAD_MODELS`):
  - [ ] `indulge.requested` — add payload model or document as intentionally unvalidated
  - [ ] `indulge.responded` — add payload model or document as intentionally unvalidated
  - [ ] Forum events (`townhall.convened`, `townhall.broadcast`, `townhall.response`, `townhall.adjourned`, `roundtable.convened`, `roundtable.round_completed`, `roundtable.adjourned`, `commons.*`) — add payload models or document as intentionally unvalidated
- [ ] Decision: add models for currently-unvalidated event types OR explicitly document bypass rationale in `schemas/events.py`.

## D) Structured output handling (Executor)

- [ ] Verify `_parse_structured_with_retry` in `agent/executor.py` (line 503) produces exactly one of three deterministic outcomes:
  - [ ] Validated JSON dict (Pydantic-validated via `AnalyzeStructuredOutput` or `AnnotateStructuredOutput`)
  - [ ] Repaired JSON dict (retry succeeds: same Pydantic validation applied)
  - [ ] Explicit failure marker: `{"_validation_failure": {...}, "text": raw_output}`
- [ ] Verify `_parse_and_validate_structured` (line 546) returns `None` for both `JSONDecodeError` and `ValidationError`.
- [ ] Verify ANNOTATE executor path (line 351) short-circuits on `_validation_failure` without triggering catalog side effects.
- [ ] Verify ANALYZE executor path does not overwrite structured data from a failed parse with citation data silently — confirm line 345 (`if structured is None`) guards correctly.
- [ ] Add test: retry with invalid JSON produces `_validation_failure` marker (not silent `None`).
- [ ] Add test: repaired JSON that still fails Pydantic produces `_validation_failure` marker.
- [ ] Add test: valid JSON on first attempt skips retry entirely.

## E) JSON Schema export completeness

- [ ] Verify `tools/export_event_schemas.py` currently exports schemas for:
  - [ ] `AgentStateSnapshottedPayload`
  - [ ] `DecisionProposedPayload`
  - [ ] `DecisionTakenPayload`
  - [ ] `ActionExecutedPayload`
  - [ ] `NotebookPayload`
  - [ ] `ConstitutionRevisedPayload`
  - [ ] `ArtifactStoredPayload`
  - [ ] `AnalyzeStructuredOutput`
  - [ ] `AnnotateStructuredOutput`
- [ ] Identify missing schemas from `KNOWN_EVENT_PAYLOAD_MODELS` not yet exported:
  - [ ] `LatentReasonedPayload` — add to `SCHEMA_MODELS` dict in `tools/export_event_schemas.py`
  - [ ] `RunCompletedPayload` — add to `SCHEMA_MODELS` dict
  - [ ] `SafetyTriggerArmedPayload` — add to `SCHEMA_MODELS` dict
  - [ ] `SafetyTriggerEvaluatedPayload` — add to `SCHEMA_MODELS` dict
- [ ] Run `python -m tools.export_event_schemas` after adding missing models.
- [ ] Verify new `.schema.json` files appear in `schemas/generated/`.
- [ ] Add test: `SCHEMA_MODELS` keys in export tool match `KNOWN_EVENT_PAYLOAD_MODELS` keys (no drift).

## F) Hash check tooling

- [ ] Verify `tools/check_run_config_hashes.py` exists and runs standalone via `python -m tools.check_run_config_hashes --base-dir .`.
- [ ] Verify `tools/sync_run_config_hashes.py` exists and runs standalone via `python -m tools.sync_run_config_hashes --base-dir .`.
- [ ] Verify `test_wave1_contracts.py::test_run_config_hash_check_detects_mismatch` exercises the check tool.
- [ ] Verify `test_wave1_contracts.py::test_load_run_config_rejects_hash_mismatch` exercises runner-level enforcement.
- [ ] Verify hash check is invoked during `uv run pytest -q` (either as a test or via fixture).
- [ ] Confirm `HASH_FIELDS` dict in both tools covers: `constitution_seed_hash`, `field_list_hash`, `action_vocabulary_hash`, `executor_templates_hash`, `prompt_pack_hash`.

## G) Test implementation

- [ ] Existing tests to verify pass:
  - [ ] `tests/test_chain.py::test_known_payload_validation_rejects_invalid_shape` — validates writer rejects bad payloads
  - [ ] `tests/test_wave1_contracts.py::test_parse_and_validate_structured_accepts_valid_analyze_json`
  - [ ] `tests/test_wave1_contracts.py::test_parse_and_validate_structured_rejects_non_json`
  - [ ] `tests/test_wave1_contracts.py::test_run_config_hash_check_detects_mismatch`
  - [ ] `tests/test_wave1_contracts.py::test_load_run_config_rejects_hash_mismatch`
  - [ ] `tests/test_wave1_contracts.py::test_load_run_config_defaults_tool_allowlist_to_empty`
- [ ] New tests to add in `tests/test_wave1_contracts.py`:
  - [ ] `test_validate_known_event_payload_passes_unknown_types_through` — unknown event types return payload unchanged
  - [ ] `test_validate_known_event_payload_validates_all_known_types` — each key in `KNOWN_EVENT_PAYLOAD_MODELS` rejects a malformed payload
  - [ ] `test_structured_retry_produces_failure_marker` — full `_parse_structured_with_retry` path when both parse attempts fail
  - [ ] `test_structured_retry_succeeds_on_second_attempt` — mock LLM returns valid JSON on retry
  - [ ] `test_annotate_skips_side_effects_on_validation_failure` — executor returns early with `executor.structured.validation_failed`
  - [ ] `test_schema_export_covers_all_known_payload_models` — `SCHEMA_MODELS` in export tool >= `KNOWN_EVENT_PAYLOAD_MODELS`
  - [ ] `test_export_event_schemas_produces_valid_json_schema` — each generated file is valid JSON Schema
  - [ ] `test_hash_check_passes_when_synced` — verify no errors when hashes match
- [ ] Verify all tests exercise real code paths (not duplicating logic) per Wave 0 lesson.

## H) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas after adding new models:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] review schema diff — only new files for added models, no changes to existing schemas
- [ ] Sync hashes if any tracked files were modified:
  - [ ] `python -m tools.sync_run_config_hashes --base-dir .`

## I) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] payload validation coverage (event types validated / total event types written)
  - [ ] schema export coverage (exported models / known payload models)
  - [ ] structured output determinism (all three outcome paths tested)
  - [ ] hash check enforcement (runner rejects mismatches)
- [ ] Compare observed state against acceptance criteria in Wave 1 spec.
- [ ] Mark decision outcome: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback plan before merge:
  - [ ] New payload models in `schemas/events.py` can be removed without breaking existing data (models only validate on write, not read).
  - [ ] New entries in `SCHEMA_MODELS` export dict can be reverted independently.
  - [ ] Structured output changes are local to `_parse_structured_with_retry` — revert is single-method.
- [ ] Define trigger thresholds for rollback:
  - [ ] Any existing test failure introduced by new validation
  - [ ] Chain verification failure caused by stricter payload enforcement
  - [ ] False rejection of previously-valid payloads in production ledgers
- [ ] Validate rollback preserves all existing schema artifacts for audit.

## K) Exit criteria

- [ ] All mandatory gates pass (section H).
- [ ] Payload validation is enforced before known writes in critical paths (verified via audit in section C).
- [ ] Invalid structured output produces deterministic handling path (verified via tests in section D).
- [ ] JSON Schema artifacts are generated for all payload models in `KNOWN_EVENT_PAYLOAD_MODELS`.
- [ ] Hash check command exists and is wired into test flow.
- [ ] No changes outside declared scope (no prompt changes, no new runtime features, no seed modifications).
- [ ] Wave scorecard complete with acceptance evidence.
