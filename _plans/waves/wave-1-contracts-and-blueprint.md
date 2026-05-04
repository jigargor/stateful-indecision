# Wave 1: Contracts and Blueprint

## Escalation Justification
- This wave hardens write paths and output contracts.
- It reduces schema drift and invalid payload risk before deeper runtime experiments.

## Expanded Worker Topology
- Worker count: 4
- Workers:
  - `payload-validation-worker`: add validation before known ledger writes
  - `schema-export-worker`: export JSON Schemas for selected payloads and structured executor outputs
  - `structured-output-worker`: tighten `ANALYZE` or `ANNOTATE` handling for invalid JSON (retry, reject, or explicit failure mark)
  - `hash-check-worker`: add seed and run-config hash check command or test

## Dependencies
- Requires Wave 0 go decision.

## Inter-Wave Role Intake (0 -> 1)
- Consume Wave 0 random handoff role and keep it active for wave leadership.
- If no role is recorded, default to `strict-auditor`.

## Artiforge Integration
- Optional planning assist:
  - `artiforge-make-development-task-plan` for worker-level breakdown.

## Acceptance Criteria
- Payload validation is enforced before known writes in critical paths.
- Invalid structured output produces deterministic handling path.
- JSON Schema artifacts are generated for agreed representative payloads.
- Hash check command or test exists and is wired into test flow.
- New focused tests pass.
- Chain verification for alpha and beta passes.

## File Manifest
- `agent/executor.py`
- `agent/decision.py`
- `core/writer.py`
- `schemas/events.py`
- `agent/runner.py`
- `run_config.json`
- Test files under `tests/`

## Wave-by-Wave Findings
- Validation implementation complete: [ ] yes [ ] no
- Structured output path complete: [ ] yes [ ] no
- Schema exports complete: [ ] yes [ ] no
- Hash checks complete: [ ] yes [ ] no

## Scorecard
- Contract robustness: [ ] green [ ] yellow [ ] red
- Test confidence: [ ] green [ ] yellow [ ] red
- Residual risk level: [ ] low [ ] medium [ ] high
- Go or no-go recommendation: [ ] go [ ] no-go

## Synthesis and Decision
- Decision:
- Rationale:
- Blockers:

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Isolate contract changes behind minimal surface area if regressions occur.
  - Preserve schema artifacts for audit even if implementation is rolled back.
