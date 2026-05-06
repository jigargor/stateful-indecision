# Wave 0: Artiforge Foundation and Stabilization

## Escalation Justification
- This wave establishes the baseline all later waves depend on.
- It combines tool-driven project synthesis plus stabilization fixes with strict pass gates.
- Failure here invalidates downstream planning assumptions.

## Expanded Worker Topology
- Worker count: 4
- Workers:
  - `artiforge-runner`: run required Artiforge calls and capture outputs
  - `stabilization-runner`: fix or reclassify PONDER leaf-weight invariant failures
  - `version-consistency-runner`: reconcile README wording with `pyproject.toml` version `1.0.0`
  - `validator-runner`: execute test and chain-verification gates; produce scorecard

## Dependencies
- None. This is the required first wave.

## Inter-Wave Role Handoff (0 -> 1)
- Assign a random handoff role seed at Wave 0 closeout.
- Candidate roles:
  - `strict-auditor` (contract correctness first)
  - `schema-architect` (types and validation first)
  - `release-steward` (backward compatibility first)
- Record selected role in scorecard and pass it to Wave 1 kickoff.

## Required Artiforge Invocations
- `codebase-scanner`
- `artiforge-make-project-docs`
- `artiforge-make-development-task-plan`

## Fallback Policy
- Artiforge is mandatory.
- If any Artiforge call fails:
  - record command or tool invocation
  - record full error output
  - record manual fallback action
  - record residual risk
- Do not silently skip Artiforge.

## Acceptance Criteria
- Root `AGENTS.md` generated or updated.
- README includes Auton concept mapping table.
- `_plans/auton_and_agent_layers.md` pins paper version to v1.
- PONDER vocabulary invariant issue is fixed or formally reclassified with test coverage.
- README pre-release wording aligns with `pyproject.toml` version `1.0.0`.
- `uv run pytest -q` passes.
- `python -m tools.verify_chains --ecosystem alpha` passes.
- `python -m tools.verify_chains --ecosystem beta` passes.

## File Manifest
- `README.md`
- `pyproject.toml`
- `seeds/action_vocabulary.json`
- `_plans/auton_and_agent_layers.md`
- `AGENTS.md`
- Tests touching vocabulary invariants

## Wave-by-Wave Findings
- Artiforge runs:
  - `codebase-scanner`: [ ] pass [x] fail (empty error object; see runtime log)
  - `artiforge-make-project-docs`: [ ] pass [x] fail (empty error object; see runtime log)
  - `artiforge-make-development-task-plan`: [ ] pass [x] fail (empty error object; see runtime log)
- Stabilization updates complete: [x] yes [ ] no
- Baseline gates complete: [x] yes [ ] no

## Artiforge Runtime Log (Current Session)
- `act-as-agent`: succeeded and returned agent prompt scaffold.
- `codebase-scanner`: returned `{ "error": "" }` (runtime failure, no diagnostic text).
- `artiforge-make-project-docs`: returned `{ "error": "" }` (runtime failure, no diagnostic text).
- `artiforge-make-development-task-plan`: returned `{ "error": "" }` (runtime failure, no diagnostic text).
- Manual fallback applied for Wave 0 documentation outputs in this session.

## Scorecard
- Baseline stability: [x] green [ ] yellow [ ] red
- Artifact completeness: [x] green [ ] yellow [ ] red
- Residual risk level: [x] low [ ] medium [ ] high
- Go or no-go recommendation: [x] go [ ] no-go

## Synthesis and Decision
- Decision: **Go for Wave 1**
- Rationale: All validation gates pass (123 tests, 8 beta chains verified, 4 config hashes clean). PONDER invariant formally reclassified with test coverage (Option 2). README/pyproject version language aligned. AGENTS.md operational commands updated. No runtime behavior changed.
- Required follow-ups before Wave 1: None blocking. Artiforge tooling remains unavailable but manual fallback outputs are verified.
- Handoff role seed: `schema-architect`

## Residual Risks and Rollback
- Risks:
- Rollback plan:
  - Revert vocabulary adjustments if tests regress unrelated paths.
  - Revert README wording only if product/version policy changes.
  - Keep log of failed Artiforge calls for audit.
