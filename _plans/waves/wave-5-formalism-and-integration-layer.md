# Wave 5: Formalism and Integration Layer

## Escalation Justification
- This wave introduces optional advanced reasoning structure and cross-layer docs.
- It must run only after behavior is stable under contracts, memory, and safety controls.

## Expanded Worker Topology
- Worker count: 4
- Workers:
  - `diagram-worker`: add Auton sequence and layering diagrams
  - `phase-worker`: add named decision phases in runtime flow
  - `latent-worker`: add optional latent reasoning events behind runtime flag
  - `integration-docs-worker`: document MCP boundary, adapter registration, and model-output failure modes

## Dependencies
- Requires Wave 4 go decision.
- Strongly gated on stable behavior from Waves 1 to 4.

## Inter-Wave Role Intake (4 -> 5)
- Consume Wave 4 random handoff role and keep it active for wave leadership.
- If no role is recorded, default to `compatibility-steward`.

## Artiforge Integration
- Optional planning assist:
  - `artiforge-make-development-task-plan` for phase and flag rollout design.

## Acceptance Criteria
- Sequence and layering diagrams are present and accurate.
- Named decision phases are implemented without changing default behavior.
- Latent reasoning events are optional and runtime-flag controlled.
- `pi_reason` then `pi_action` path remains experimental and disabled by default.
- MCP boundary and failure-mode docs are complete.
- Existing tests and new focused tests pass.
- Chain verification for alpha and beta passes.

## File Manifest
- `agent/decision.py`
- `agent/executor.py`
- `agent/runner.py`
- `schemas/events.py`
- `README.md`
- `_plans/auton_and_agent_layers.md`

## Wave-by-Wave Findings
- Diagrams complete: [ ] yes [ ] no
- Named phases complete: [ ] yes [ ] no
- Latent event flag path complete: [ ] yes [ ] no
- Integration docs complete: [ ] yes [ ] no

## Scorecard
- Formalism correctness: [ ] green [ ] yellow [ ] red
- Backward compatibility: [ ] green [ ] yellow [ ] red
- Residual risk level: [ ] low [ ] medium [ ] high
- Go or no-go recommendation: [ ] go [ ] no-go

## Synthesis and Decision
- Decision:
- Rationale:
- Deferred items:

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Disable latent and phase features by default flag.
  - Keep docs synchronized with actual feature-flag state.
