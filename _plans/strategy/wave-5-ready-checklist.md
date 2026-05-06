# Wave 5 Ready-to-Execute Checklist

Scope label: `[optional formalism]`  
Wave: `5 — Formalism and Integration Layer`  
Status: Execution checklist (verification- and documentation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec:
  - [`_plans/waves/wave-5-formalism-and-integration-layer.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-5-formalism-and-integration-layer.md)
- Auton alignment doc:
  - [`_plans/auton_and_agent_layers.md`](/home/ubuntu/stateful-indecision/_plans/auton_and_agent_layers.md)

## A) Scope lock and success criteria

- [ ] Confirm Wave 5 is entirely opt-in: no defaults change, no new mandatory behavior.
- [ ] Confirm Wave 5 non-goals:
  - [ ] no new write paths or side-effect changes
  - [ ] no modification to policy sampling logic (beyond already-flagged `enable_pi_reason_then_action`)
  - [ ] no breaking changes to ledger schema (additive only)
  - [ ] no RL or training-loop changes
- [ ] Confirm all prior waves pass (0–4, E1–E3): 350+ tests green.
- [ ] Record baseline thresholds carried forward:
  - [ ] safety outcomes unchanged (pass/warn/fail distribution)
  - [ ] chain verification passes for alpha and beta
  - [ ] no action-distribution drift when Wave 5 flags are off

## B) Config contract verification

Existing flags to verify (not create):

- [ ] `emit_latent_reasoning_events` (bool, default `False`):
  - [ ] Declared in `Executor.__init__` with default `False`.
  - [ ] Wired from `run_config` in `runner.py` with `bool(run_config.get("emit_latent_reasoning_events", False))`.
  - [ ] When `False`, no `agent.latent.reasoned` events are emitted from executor post-generation path.
- [ ] `enable_pi_reason_then_action` (bool, default `False`):
  - [ ] Consumed in `decision.step()` to gate `_reason_phase` + biased sampling.
  - [ ] Wired from `run_config` in `runner.py` decision loop.
  - [ ] When `False`, standard `sample(dist, rng)` path is used with no latent events from decision layer.
- [ ] `decision_phases` list in `action.executed` payload:
  - [ ] Hardcoded as `["state_snapshot", "policy_proposal", "policy_sample", "executor_run", "ledger_commit"]` in `decision.py`.
  - [ ] Present in `ActionExecutedPayload` model as `decision_phases: list[str]`.
  - [ ] Verify the five phase names match the actual code flow in `decision.step()`.
- [ ] Verify no invalid-value paths silently succeed — flags that are not bool should raise.

## C) Diagram worker — verify and complete

Target: Auton sequence and layering diagrams in `_plans/auton_and_agent_layers.md`.

- [ ] **Sequence diagram** (§4, mermaid):
  - [ ] Exists: `stateBuilder → policyPropose → policySample → executorRun → ledgerCommit → nextSnapshot`.
  - [ ] Verify it matches the five named `decision_phases` in `decision.py`.
  - [ ] Verify the diagram reflects the optional `_reason_phase` branch when `enable_pi_reason_then_action` is `True` (note or conditional path).
  - [ ] Verify the diagram reflects the optional post-generation latent event when `emit_latent_reasoning_events` is `True`.
- [ ] **Layering diagram** (§9, mermaid):
  - [ ] Exists: `Blueprint Inputs → Decision Layer → Execution Layer → Storage and Verification → Observability and Evaluation`.
  - [ ] Verify file pointers in the Auton concept → repo lookup table (§3) are accurate for current paths.
  - [ ] Verify the five layers map to concrete directories/files accurately.
- [ ] **Cross-reference**: diagrams are consistent with each other and with the strategy-index.

## D) Phase worker — verify named decision phases

Target: `agent/decision.py`, `schemas/events.py`.

- [ ] **Phase list correctness**: verify the five phases match the actual `step()` code flow:
  - [ ] `state_snapshot` — corresponds to `state_builder.build()` + snapshot event append.
  - [ ] `policy_proposal` — corresponds to `policy.propose(snapshot)` + proposed event append.
  - [ ] `policy_sample` — corresponds to `sample(dist, rng)` (or biased variant) + taken event append.
  - [ ] `executor_run` — corresponds to `executor.execute(...)`.
  - [ ] `ledger_commit` — corresponds to `action.executed` event append (the commit of the step result).
- [ ] **Payload model**: `ActionExecutedPayload.decision_phases` is `list[str]` with `default_factory=list`.
  - [ ] Verify the default (empty list) is safe for events written before phases were added.
  - [ ] Verify the generated schema (`schemas/generated/action-executed-payload.schema.json`) includes `decision_phases`.
- [ ] **No behavioral change**: the phase list is informational metadata — verify it does not gate any logic.
- [ ] **Documentation**: add a brief inline comment or docstring in `decision.py:step()` naming the phases, so future readers can trace the mapping.

## E) Latent worker — verify latent reasoning events and flag enforcement

Target: `agent/executor.py`, `agent/decision.py`, `schemas/events.py`.

### E.1) `emit_latent_reasoning_events` flag (executor post-generation)

- [ ] Verify emission site: `executor.py` around line 281 — `if self.emit_latent_reasoning_events:` block.
- [ ] Verify emitted event type is `agent.latent.reasoned`.
- [ ] Verify emitted payload matches `LatentReasonedPayload` schema:
  - [ ] `phase: "post_generation"`
  - [ ] `top_action`, `sub_action`, `structured_candidate`, `raw_output_preview` fields present.
- [ ] Verify when flag is `False`, no `agent.latent.reasoned` events appear on the executor path.
- [ ] Verify the event is append-only and has no side effects (no branching logic depends on it).

### E.2) `enable_pi_reason_then_action` flag (decision layer)

- [ ] Verify emission site: `decision.py` around line 96 — `if enable_pi_reason_then_action:` block.
- [ ] Verify emitted event type is `agent.latent.reasoned`.
- [ ] Verify emitted payload includes `phase: "pi_reason"`, `snapshot_id`, `suggested_top_action`, `rationale`, `belief_state`.
- [ ] Verify when flag is `False`, no latent event is emitted and standard `sample(dist, rng)` is used.
- [ ] Verify `_reason_phase` does not mutate snapshot or policy state.
- [ ] Verify `_sample_with_reason_bias` only adjusts top-level weights (1.5× boost), does not add/remove actions.

### E.3) `LatentReasonedPayload` model

- [ ] Verify model fields cover both emission sites (post-generation and pi_reason).
- [ ] Verify `phase` is required, all other fields are optional (nullable).
- [ ] Verify generated schema (`schemas/generated/latent-reasoned-payload.schema.json`) matches the model.
- [ ] Verify `KNOWN_EVENT_PAYLOAD_MODELS` maps `"agent.latent.reasoned"` → `LatentReasonedPayload`.

## F) Integration docs worker — MCP boundary, adapter registration, failure modes

### F.1) LLMAdapter protocol documentation

- [ ] Document `adapters/base.py` `LLMAdapter` Protocol:
  - [ ] Required attributes: `provider: str`, `model_id: str`.
  - [ ] Required method: `complete(system, messages, *, max_tokens, temperature) → LLMResponse`.
- [ ] Document adapter registration path: `adapters/__init__.py` `create_adapter_auto` factory.
- [ ] Document existing adapters (Anthropic, Mock) and how to add new ones.

### F.2) Model-output failure modes

- [ ] Document structured output retry flow (`Executor._parse_structured_with_retry`):
  - [ ] First parse attempt → validation against `AnalyzeStructuredOutput` / `AnnotateStructuredOutput`.
  - [ ] Repair LLM call on failure (temperature 0.0, max_tokens 2048).
  - [ ] `_validation_failure` sentinel on double failure — blocks catalog side effects for ANNOTATE.
- [ ] Document `LLMError` propagation: executor → runner → `agent.error` event → `SystemExit(1)`.
- [ ] Document adapter-level retry (Anthropic: 3 attempts with `[0, 1, 4]` second delays).

### F.3) MCP boundary documentation

- [ ] Document where MCP integration would attach: `adapters/` as tool-provider boundary.
- [ ] Document current tool dispatch: `Executor._tool_allowed` + `tool_allowlist` config.
- [ ] Document the tool governance model: `None` = allow-all (no run_config), `set()` = block-all (run_config present, no list), explicit list = named tools only.
- [ ] Note: MCP is a future adapter boundary — document the seam, not a full implementation.

### F.4) Documentation location

- [ ] Decide location: extend `_plans/auton_and_agent_layers.md` §9 (Strategic Impact) or create a focused doc.
- [ ] Cross-reference from `AGENTS.md` Core Architecture section if new doc is created.
- [ ] Keep doc statements verifiable against actual code (Wave 4 lesson: no overstatements).

## G) Safety and backward-compatibility invariants

- [ ] Verify no new write paths introduced by Wave 5 features.
- [ ] Verify `emit_latent_reasoning_events=False` produces identical event streams to pre-Wave-5.
- [ ] Verify `enable_pi_reason_then_action=False` produces identical event streams to pre-Wave-5.
- [ ] Verify `decision_phases` addition to `action.executed` is purely additive (does not break consumers of old events without the field).
- [ ] Verify evaluation-ledger write protections remain unchanged.
- [ ] Verify storage firewall constraints are not affected.
- [ ] Verify `pi_reason` then `pi_action` path remains experimental and disabled by default.

## H) Test implementation

### H.1) Existing tests to verify

- [ ] `tests/test_wave5_formalism.py`:
  - [ ] `test_reason_phase_prefers_research_on_high_duplication` — verify it exercises `_reason_phase` correctly.
  - [ ] `test_sample_with_reason_bias_returns_valid_actions` — verify it exercises `_sample_with_reason_bias` correctly.

### H.2) Tests to add

- [ ] **Decision phases presence**: test that `action.executed` events written by `step()` include `decision_phases` with the expected five-element list.
- [ ] **Decision phases default**: test that `ActionExecutedPayload()` without `decision_phases` defaults to `[]`.
- [ ] **Latent event flag enforcement (executor)**: test that `emit_latent_reasoning_events=True` emits `agent.latent.reasoned` with `phase="post_generation"`, and `=False` does not.
- [ ] **Latent event flag enforcement (decision)**: test that `enable_pi_reason_then_action=True` emits `agent.latent.reasoned` with `phase="pi_reason"`, and `=False` does not.
- [ ] **LatentReasonedPayload validation**: test that both emission-site payloads validate against the Pydantic model.
- [ ] **Reason phase purity**: test that `_reason_phase` does not mutate its input snapshot.
- [ ] **Bias sampling bounds**: test that `_sample_with_reason_bias` only returns actions present in the input distributions.
- [ ] **Default behavior unchanged**: integration test that a standard `step()` call with both flags off produces no latent events and includes `decision_phases` in the executed event.
- [ ] **Backward compat**: test that `ActionExecutedPayload` can be constructed without `decision_phases` or `decision_event_id` (old-format events).

## I) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Verify generated schemas are up to date:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] Review schema diff — confirm `LatentReasonedPayload` and `ActionExecutedPayload` schemas match models.
  - [ ] No unintended schema changes.

## J) Wave scorecard evidence capture

- [ ] Record per-worker outcomes:
  - [ ] diagram-worker: diagrams present and accurate (`yes` / `no`)
  - [ ] phase-worker: named phases correct and complete (`yes` / `no`)
  - [ ] latent-worker: flag path verified and enforced (`yes` / `no`)
  - [ ] integration-docs-worker: MCP boundary and failure-mode docs complete (`yes` / `no`)
- [ ] Record formalism correctness: `green` / `yellow` / `red`
- [ ] Record backward compatibility: `green` / `yellow` / `red`
- [ ] Record residual risk level: `low` / `medium` / `high`
- [ ] Compare observed test count and safety outcomes against baseline (350+ tests, no regressions).
- [ ] Mark decision outcome: `go` / `no-go`

## K) Rollback readiness

- [ ] Rollback path defined: disable `emit_latent_reasoning_events` and `enable_pi_reason_then_action` via config.
- [ ] `decision_phases` field is inert metadata — can be removed from `step()` without breaking consumers (field defaults to `[]`).
- [ ] Documentation changes are purely additive — rollback = note features as disabled/experimental.
- [ ] Validate rollback can disable all Wave 5 features entirely via existing config flags.
- [ ] Archive rollback evidence and rationale in wave scorecard.

## L) Exit criteria

- [ ] All mandatory gates (section I) pass.
- [ ] No default behavior changes when Wave 5 flags are off.
- [ ] All four worker deliverables verified (diagrams, phases, latent path, integration docs).
- [ ] Wave scorecard complete with go/no-go decision.
- [ ] This is the final runtime wave — confirm no deferred items require further runtime changes.
