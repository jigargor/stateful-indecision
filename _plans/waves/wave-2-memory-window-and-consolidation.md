# Wave 2: Memory Window and Consolidation

## Escalation Justification
- Memory behavior directly affects model quality and repeatability.
- This wave defines stable memory boundaries and controllable context growth.

## Expanded Worker Topology
- Worker count: 3
- Workers:
  - `memory-cap-worker`: make `recent_events` and `recent_notebook` configurable via run config
  - `memory-docs-worker`: document STM/LTM boundaries across ledger, notebook, constitution, artifacts, and prompt window
  - `consolidation-worker`: add reflector-style notebook consolidation and rolling-summary hook

## Dependencies
- Requires Wave 0 go decision.
- Can run in parallel with Wave 1 and Wave 3.

## Artiforge Integration
- Optional planning assist:
  - `codebase-scanner` with additional context focused on memory pathways.

## Acceptance Criteria
- Run-config supports memory caps with backward-compatible defaults.
- STM/LTM boundary document is explicit and discoverable.
- Consolidation flow exists and is test-covered.
- Rolling summary hook exists (RAG remains a stub unless needed).
- Focused tests pass.
- Chain verification for alpha and beta passes.

## File Manifest
- `agent/state_builder.py`
- `agent/notebook.py`
- `agent/executor.py`
- `run_config.json`
- `run_config_beta_a2.json`
- `run_config_beta_a3.json`
- `tools/consolidate_notebook.py`
- `_plans/auton_and_agent_layers.md`

## Wave-by-Wave Findings
- Memory caps integrated: [ ] yes [ ] no
- STM/LTM docs completed: [ ] yes [ ] no
- Consolidation + summary hook completed: [ ] yes [ ] no

## Scorecard
- Memory stability: [ ] green [ ] yellow [ ] red
- Context-pressure resilience: [ ] green [ ] yellow [ ] red
- Residual risk level: [ ] low [ ] medium [ ] high
- Go or no-go recommendation: [ ] go [ ] no-go

## Synthesis and Decision
- Decision:
- Rationale:
- Follow-up tasks:

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Revert cap fields while retaining docs if rollout causes regressions.
  - Disable consolidation hook behind feature flag if quality drops.
