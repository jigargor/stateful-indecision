# Wave 4: Observability and Evolution

## Escalation Justification
- This wave defines production-grade visibility and trajectory export quality.
- It depends on stabilized contracts and safety behavior from earlier waves.

## Expanded Worker Topology
- Worker count: 3
- Workers:
  - `metrics-worker`: extend SQLite and Grafana metrics for p50 or p95 latency, tokens per decision, stop reasons, and action mix
  - `trajectory-worker`: add `tools/export_trajectories.py` for offline RL or preference training JSONL
  - `adaptation-worker`: document Level 1 checkpoint tuning (metric, rule, mutation, rollback)

## Dependencies
- Requires Wave 1, Wave 2, and Wave 3 go decisions.

## Inter-Wave Role Intake and Handoff (3 -> 4 -> 5)
- Intake:
  - Consume Wave 3 random handoff role.
  - If no role is recorded, default to `determinism-keeper`.
- Outgoing handoff:
  - Assign a new random role at Wave 4 closeout for Wave 5.
  - Candidate roles:
    - `systems-integrator` (cross-layer consistency first)
    - `formalism-curator` (theory-to-runtime mapping first)
    - `compatibility-steward` (flag safety and default behavior first)
- Record both intake role and outgoing role in scorecard.

## Artiforge Integration
- Optional planning assist:
  - `codebase-scanner` focused on observability and performance bottlenecks.

## Acceptance Criteria
- SQL queries support required latency, token, stop-reason, and action-mix metrics.
- Dashboard template and README are aligned with SQL.
- Trajectory export tool exists with documented schema.
- Level 1 adaptation workflow documentation is complete.
- Grafana SQL validates against `dashboard.db`.
- Chain verification for alpha and beta passes.

## File Manifest
- `tools/grafana_starter_queries.sql`
- `tools/grafana_dashboard_template.json`
- `tools/README-Grafana.md`
- `tools/export_trajectories.py`
- Supporting tests or validation scripts

## Wave-by-Wave Findings
- Metrics extension complete: [ ] yes [ ] no
- Trajectory export complete: [ ] yes [ ] no
- Adaptation docs complete: [ ] yes [ ] no
- `dashboard.db` validation complete: [ ] yes [ ] no

## Scorecard
- Observability quality: [ ] green [ ] yellow [ ] red
- Offline-training readiness: [ ] green [ ] yellow [ ] red
- Residual risk level: [ ] low [ ] medium [ ] high
- Go or no-go recommendation: [ ] go [ ] no-go

## Synthesis and Decision
- Decision:
- Rationale:
- Follow-up actions:

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Keep old Grafana query pack versioned for quick revert.
  - Make trajectory export non-invasive to runtime paths.
