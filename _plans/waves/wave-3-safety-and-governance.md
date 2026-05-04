# Wave 3: Safety and Governance

## Escalation Justification
- This wave changes decision admissibility and enforcement behavior.
- Errors here can silently alter agent policy semantics and safety posture.

## Expanded Worker Topology
- Worker count: 4
- Workers:
  - `mask-worker`: implement hard action masks pre-sampling from config or constitution rules
  - `allowlist-worker`: add adapter or tool allowlist configuration and enforcement
  - `verifier-hook-worker`: write deterministic verifier events at step and terminal boundaries
  - `killswitch-worker`: update `KillSwitchMonitor.evaluate` to emit pass or warn or fail behavior

## Dependencies
- Requires Wave 0 go decision.
- Can run in parallel with Wave 1 and Wave 2.

## Inter-Wave Role Handoff (3 -> 4)
- Assign a random handoff role seed at Wave 3 closeout.
- Candidate roles:
  - `safety-warden` (risk-first)
  - `determinism-keeper` (event consistency first)
  - `policy-guardian` (mask and allowlist strictness first)
- Record selected role in scorecard and pass it to Wave 4 kickoff.

## Artiforge Integration
- Optional planning assist:
  - `artiforge-make-development-task-plan` for enforcement edge cases.

## Acceptance Criteria
- Masking occurs before sampling and rejects illegal leaves deterministically.
- Adapter or tool allowlist is configurable and enforced.
- Verifier events are emitted deterministically with tests.
- Kill-switch outcomes are explicit and test-covered.
- Focused tests pass.
- Chain verification for alpha and beta passes.

## File Manifest
- `agent/policy.py`
- `agent/decision.py`
- `agent/runner.py`
- `core/verifier.py`
- `safety/kill_switch.py`
- `schemas/events.py`
- `run_config.json`
- Tests under `tests/`

## Wave-by-Wave Findings
- Hard masks complete: [ ] yes [ ] no
- Allowlists complete: [ ] yes [ ] no
- Verifier hooks complete: [ ] yes [ ] no
- Kill-switch outcomes complete: [ ] yes [ ] no

## Scorecard
- Safety control coverage: [ ] green [ ] yellow [ ] red
- Determinism level: [ ] green [ ] yellow [ ] red
- Residual risk level: [ ] low [ ] medium [ ] high
- Go or no-go recommendation: [ ] go [ ] no-go

## Synthesis and Decision
- Decision:
- Rationale:
- Remaining hazards:

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Keep mask logic behind clear feature switch if rollout issues appear.
  - Maintain event schema compatibility during kill-switch transition.
