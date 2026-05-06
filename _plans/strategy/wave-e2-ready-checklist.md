# Wave E2 Ready-to-Execute Checklist

Scope label: `[flagged runtime later]`  
Wave: `E2 — Offline multi-run map-reduce protocol surfaces`  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/strategy/implementation-wave-plan.md`](/home/ubuntu/stateful-indecision/_plans/strategy/implementation-wave-plan.md) (lines 45-68)
- Map-reduce roadmap:
  - [`_plans/strategy/cognitive-map-reduce-roadmap.md`](/home/ubuntu/stateful-indecision/_plans/strategy/cognitive-map-reduce-roadmap.md)
- Autogen iteration protocol (handoff schema definition):
  - [`_plans/strategy/autogen-iteration-protocol.md`](/home/ubuntu/stateful-indecision/_plans/strategy/autogen-iteration-protocol.md)

## A) Scope lock and success criteria

- [ ] Confirm E2 is opt-in only and does not change existing single-run defaults.
- [ ] Confirm E2 non-goals:
  - [ ] no in-process multi-agent scheduler (Stage C / v2+)
  - [ ] no concurrency semantics or fault-tolerant distributed orchestration
  - [ ] no ledger schema migrations (append new event types only)
  - [ ] no automatic self-modification promotion
- [ ] Record baseline thresholds for this wave:
  - [ ] safety fail budget
  - [ ] novelty proxy threshold
  - [ ] token/latency budget ceiling
  - [ ] unresolved conflict count baseline

## B) Handoff schema definition

- [ ] Define `HandoffPayload` Pydantic model in `schemas/events.py` with strict fields:
  - [ ] `handoff_id: str` (UUID, unique per handoff)
  - [ ] `from_role: str` (must be one of `research_lead`, `assistant_researcher`, `checker`)
  - [ ] `to_role: str` (must be one of `research_lead`, `assistant_researcher`, `checker`)
  - [ ] `task_objective: str` (non-empty description of delegated work)
  - [ ] `inputs_refs: list[str]` (event IDs, artifact IDs, or doc IDs)
  - [ ] `expected_output_shape: str` (description of what the recipient should produce)
  - [ ] `deadline_step: int | None` (optional step budget for completion)
  - [ ] `completion_status: str | None` (one of `pending`, `completed`, `failed`, `superseded`, or `None`)
  - [ ] `checker_verdict: str | None` (one of `PASS`, `REVISE`, `BLOCK`, or `None`)
- [ ] Do NOT use `extra="allow"` on the handoff model.
- [ ] Add `field_validator` for `from_role` and `to_role` against known role set.
- [ ] Add `field_validator` for `completion_status` and `checker_verdict` against allowed enum values.
- [ ] Define `CheckerVerdictPayload` Pydantic model in `schemas/events.py`:
  - [ ] `handoff_id: str` (references the handoff being reviewed)
  - [ ] `batch_id: str | None` (optional batch identifier)
  - [ ] `verdict: str` (must be one of `PASS`, `REVISE`, `BLOCK`)
  - [ ] `checker_confidence: float` (0.0–1.0)
  - [ ] `scores: dict[str, float]` (evidence_grounding, consistency, completeness, calibration, learning_utility)
  - [ ] `accepted_claim_ids: list[str]`
  - [ ] `rejected_claim_ids: list[str]`
  - [ ] `issues: list[dict[str, str]]` (severity, claim_id, problem, required_fix)
  - [ ] `notes: str | None`
- [ ] Do NOT use `extra="allow"` on the verdict model.
- [ ] Register both new models in `KNOWN_EVENT_PAYLOAD_MODELS`:
  - [ ] `"handoff.issued"` → `HandoffPayload`
  - [ ] `"checker.verdict"` → `CheckerVerdictPayload`

## C) Cross-team communication contract fields

- [ ] Verify handoff schema covers cognitive-map-reduce roadmap required fields:
  - [ ] `team_id` → derivable from `from_role` / ecosystem context (document mapping)
  - [ ] `role` → covered by `from_role` / `to_role`
  - [ ] `task_id` → covered by `handoff_id`
  - [ ] `input_refs` → covered by `inputs_refs`
  - [ ] `claim_set` → covered by `expected_output_shape` + checker verdict `accepted_claim_ids`
  - [ ] `checker_verdict` → covered directly
  - [ ] `confidence` → covered by `CheckerVerdictPayload.checker_confidence`
  - [ ] `next_action` → derivable from `completion_status` (document convention)
- [ ] Document any field gaps and explicit mapping conventions in strategy docs.

## D) Forum/public dual-write consistency

- [ ] Read and verify `ForumBase._dual_write` in `forums/base.py` writes identical payloads to both forum and public writers.
- [ ] Verify `event_id_override` ensures same event ID appears in both ledgers.
- [ ] Add handoff events to dual-write path:
  - [ ] Decide forum surface for handoff events (roundtable or new `handoff` forum ledger).
  - [ ] If new ledger: add `handoff_ledger()` to `EcosystemStorage` following existing `roundtable_ledger()` / `townhall_ledger()` pattern.
  - [ ] If existing forum: extend roundtable or public-only path with handoff event types.
- [ ] Verify no dual-write event ID collision across forum and public writers.
- [ ] Add explicit test that forum ledger and public ledger contain matching event IDs and payloads for handoff events.

## E) Checker-verdict required path

- [ ] Add `checker.verdict` as a required event type before handoff completion status can transition to `completed`.
  - [ ] Define the enforcement point (validation at write time or verification post-hoc).
  - [ ] If write-time: add validation in `validate_known_event_payload` or a dedicated handoff validator.
  - [ ] If post-hoc: add verifier check similar to `VerifierBoundaryCheckedPayload`.
- [ ] Checker verdict with `verdict: "BLOCK"` must prevent downstream acceptance of associated claims.
- [ ] Checker verdict with `verdict: "REVISE"` must leave `completion_status` as `pending` (no silent promotion).
- [ ] Verify checker verdict references a valid `handoff_id` (cross-reference validation).
- [ ] Non-negotiable: every claim promoted to synthesis requires a checker `PASS` verdict (no silent merge).

## F) Executor and role resolution updates

- [ ] Verify `SUB_ACTION_ROLE_MAP` in `agent/executor.py` covers all sub-actions relevant to handoff:
  - [ ] `ORCHESTRATE` → `research_lead` (already mapped)
  - [ ] `CHALLENGE` / `CRITIQUE_IDEA` → `checker` (already mapped)
  - [ ] Research sub-actions → `assistant_researcher` (already mapped)
- [ ] Add handoff-aware prompt assembly path in executor:
  - [ ] When `team_role` is set and handoff context is available, inject handoff objective into prompt.
  - [ ] Keep injection conditional and deterministic (no injection when handoff is absent).
- [ ] Ensure `_resolve_team_prompt` continues to work correctly with existing prompt pack structure.
- [ ] Prompt pack (`prompts/sage_team_prompts.json`) updates:
  - [ ] Add handoff protocol instructions to `research_lead` system prompt (task decomposition, handoff issuance).
  - [ ] Add handoff acceptance instructions to `assistant_researcher` system prompt (receive handoff, produce expected output).
  - [ ] Add verdict issuance instructions to `checker` system prompt (review handoff output, emit verdict).
  - [ ] Keep prompt pack version bump (update `"version"` field).

## G) Safety and firewall invariants

- [ ] Verify all new reads remain under storage firewall constraints (`validate_agent_access`).
- [ ] Verify no new write paths bypass existing dual-write or public-writer guards.
- [ ] Verify evaluation-ledger write protections remain unchanged.
- [ ] Verify handoff payloads cannot reference paths outside ecosystem storage boundaries.
- [ ] Verify `inputs_refs` field values are validated as known event IDs or artifact IDs (no arbitrary path injection).
- [ ] Verify existing safety controls (masks, allowlists, kill-switch, boundary verification) are unaffected.
- [ ] No silent fallback: invalid `checker_verdict` or `completion_status` values must raise `ValidationError`, not degrade silently.

## H) Test implementation

- [ ] Schema validation tests for handoff payloads:
  - [ ] Valid `HandoffPayload` round-trips through `model_validate` / `model_dump`.
  - [ ] Invalid `from_role` / `to_role` raises `ValidationError`.
  - [ ] Invalid `completion_status` raises `ValidationError`.
  - [ ] Invalid `checker_verdict` raises `ValidationError`.
  - [ ] Missing required fields raise `ValidationError`.
  - [ ] `extra="forbid"` behavior: unexpected fields are rejected.
- [ ] Schema validation tests for checker verdict:
  - [ ] Valid `CheckerVerdictPayload` round-trips correctly.
  - [ ] Invalid `verdict` value raises `ValidationError`.
  - [ ] `checker_confidence` out of range handled correctly.
- [ ] Forum/public dual-write consistency tests:
  - [ ] Handoff event appears in both forum and public ledgers with matching `event_id`.
  - [ ] Payload content is identical across both ledgers.
- [ ] Checker-verdict required-path tests:
  - [ ] Handoff without checker verdict cannot reach `completed` status.
  - [ ] `BLOCK` verdict prevents claim acceptance.
  - [ ] `REVISE` verdict keeps status as `pending`.
  - [ ] `PASS` verdict allows status transition to `completed`.
- [ ] `KNOWN_EVENT_PAYLOAD_MODELS` registration tests:
  - [ ] `"handoff.issued"` resolves to `HandoffPayload`.
  - [ ] `"checker.verdict"` resolves to `CheckerVerdictPayload`.
  - [ ] `validate_known_event_payload` correctly validates handoff and verdict events.
- [ ] Regression tests:
  - [ ] All existing payload models continue to validate unchanged.
  - [ ] Default behavior (no handoff events) remains identical.
  - [ ] Existing forum dual-write behavior for roundtable/townhall/commons is unaffected.

## I) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] Review schema diff for intended-only changes.

## J) Rollback readiness

- [ ] Pre-write rollback steps before merge.
- [ ] Define trigger thresholds:
  - [ ] unresolved conflict growth above baseline
  - [ ] invalid handoff payloads appearing in ledgers
  - [ ] safety fail-budget increase
  - [ ] dual-write consistency failures
- [ ] Validate rollback can remove E2 event types without breaking existing chains.
- [ ] Verify existing runs without handoff events continue to work identically.
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory gates pass.
- [ ] No default behavior changes when handoff features are unused.
- [ ] `HandoffPayload` and `CheckerVerdictPayload` models are strict (no `extra="allow"`).
- [ ] All handoff fields match autogen-iteration-protocol and cognitive-map-reduce-roadmap specs.
- [ ] Checker verdict required before handoff completion (no silent merge).
- [ ] Forum/public dual-write verified for new event types.
- [ ] Prompt pack updated with handoff protocol instructions and version bumped.
- [ ] Wave scorecard complete with acceptance/rollback evidence.
