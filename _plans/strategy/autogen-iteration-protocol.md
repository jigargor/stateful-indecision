# Autogen Iteration Protocol

This protocol defines how to run many small, controlled horizontal-growth waves without changing runtime defaults prematurely.

## Scope label

- `[docs-only now]`

## Objectives

- Increase useful capability breadth across tasks/domains while preserving safety and ledger invariants.
- Keep each change bounded, reversible, and auditable.
- Prevent “silent drift” in prompts, vocabularies, and memory behavior.

## Operating principle

Start single-team and small. Expand only when evidence shows current topology is saturated.

External guidance alignment:
- AutoGen teams guidance: use teams for complex tasks and only after single-agent optimization.
- CAMEL role-playing evidence: role specialization helps, but requires guardrails against role drift and loop behavior.

## Micro-wave structure

Each wave modifies one knob family only:

- Prompt pack content, or
- Action vocabulary weights/masks, or
- Memory configuration convention, or
- Team communication convention.

No wave may combine more than one family unless explicitly marked as synthesis wave.

## Mandatory wave scorecard template

Copy this template for every wave:

```markdown
## Wave <id>

- Objective:
- Scope label: [docs-only now] | [config convention later] | [flagged runtime later] | [v2+]
- Change family: prompt | vocabulary | memory-convention | team-protocol
- Allowed ecosystems:
- Allowed flags:
- Max decisions per run:
- Seed policy:

### Baseline snapshot
- Baseline chain verification status:
- Baseline safety fail budget:
- Baseline novelty threshold:
- Baseline action distribution:
- Baseline token/latency budget:

### Expected deltas
- Expected action distribution delta:
- Expected novelty delta:
- Expected safety delta:

### Acceptance gate
- Tests: `uv run pytest -q`
- Chain checks: `python -m tools.verify_chains --ecosystem alpha|beta`
- Hash checks: `python -m tools.check_run_config_hashes --base-dir .`
- Safety threshold:
- Novelty threshold:
- Token/latency ceiling:

### Rollback gate
- Trigger conditions:
- Revert steps:
- Evidence to archive:

### Decision
- Result: accept | reject | extend
- Notes:
```

## Horizontal-growth lanes

- **Lane A: domain coverage**  
  Expand problem classes while preserving same safety envelope.
- **Lane B: process quality**  
  Improve checker quality, contradiction handling, and synthesis fidelity.
- **Lane C: memory utility**  
  Increase retained, reusable lessons without inflating prompt cost.
- **Lane D: orchestration quality**  
  Improve delegation/coordination protocol before adding runtime complexity.

Each wave must target exactly one primary lane.

## Lead/tasker/checker handoff schema (docs-level)

Use append-only communication records (forum/public logs) with strict fields:

- `handoff_id`
- `from_role`
- `to_role`
- `task_objective`
- `inputs_refs` (event IDs, artifact IDs, doc IDs)
- `expected_output_shape`
- `deadline_step`
- `completion_status`
- `checker_verdict`

## Saturation criteria for escalating topology

Escalate from single-team role switching to broader orchestration only if all are true for at least 2 waves:

- novelty plateau despite accepted waves,
- checker detects unresolved contradictions above target,
- lead backlog exceeds planned cycle budget,
- no safety regressions from prior wave.

## Non-goals for this protocol

- No in-process multi-agent scheduler design.
- No automatic self-modification promotion.
- No ledger schema migrations.

## Acceptance and rollback summary

- **Acceptance gate:** wave scorecard completed with tests, chain checks, hash checks, and threshold fields populated.
- **Rollback gate:** explicit trigger conditions and revert evidence captured for every rejected or extended wave.
