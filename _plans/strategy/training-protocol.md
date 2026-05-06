# Training Protocol (Three Gated Levels)

This protocol defines promotion gates for adaptation/training changes using internal ledgers plus external evidence.

## Scope label

- Level 1: `[docs-only now]`
- Level 2: `[flagged runtime later]`
- Level 3: `[v2+]`

## Source pools

### Internal evidence

- `ecosystems/<id>/public.jsonl`
- `ecosystems/<id>/evaluation.jsonl`
- `ecosystems/<id>/agents/<agent-id>/notebook.jsonl`
- `agents/<id>/research/*.json`
- SQLite/ETL exports (`tools/export_to_sqlite.py`, `tools/batch_etl.py`)

### External evidence

- Axis/Auton paper (`2602.23720v1`)
- Multi-agent orchestration references:
  - AutoGen team patterns (round-robin, selector)
  - Hugging Face smolagents memory + orchestrator examples
  - LangGraph supervisor hierarchy/memory controls
  - CAMEL role specialization findings

## Level 1: In-context adaptation (`[docs-only now]`)

Primary mechanism: small manual mutation + strict validation.

### Allowed changes

- Prompt pack edits
- Action vocabulary weight/mask adjustments
- Conservative run-config convention changes

### Required loop

1. checkpoint config/hash state
2. collect metrics (action mix, novelty proxy, safety outcomes, token/latency)
3. apply one mutation family
4. run acceptance gates
5. accept/revert and log rationale

### Acceptance gates

- `uv run pytest -q`
- `python -m tools.verify_chains --ecosystem alpha`
- `python -m tools.verify_chains --ecosystem beta`
- `python -m tools.check_run_config_hashes --base-dir .`

## Level 2: STaR-style candidate generation (`[flagged runtime later]`)

Primary mechanism: generate candidate reasoning/program artifacts offline, then review.

### Candidate classes

- prompt-pack alternatives
- vocabulary proposals
- retrieval-policy suggestions
- checker rubric refinements

### Promotion policy

Never auto-promote. Require:

- checker-approved evidence package,
- contradiction review completed,
- at least one replay/ablation versus baseline,
- no safety or integrity regression.

### Rejection criteria

- low novelty gain,
- safety fail-budget increase,
- unverifiable claims,
- schema/hash contract break risk.

## Level 3: Offline RL / trajectory optimization (`[v2+]`)

Primary mechanism: offline trajectory studies, not runtime behavior changes.

### Inputs

- trajectory exports
- evaluation ledger reward signals
- task-level outcomes and costs

### Constraints

- no direct online policy updates in v1 runtime,
- all outputs treated as research artifacts until separately approved.

## Cadence

- Level 1: weekly or per controlled wave.
- Level 2: monthly candidate batch.
- Level 3: quarterly research cycle.

## Artifact requirements for every promotion attempt

- before/after config hash set,
- scorecard with acceptance and rollback gates,
- citation list (internal events + external references),
- explicit keep/revert decision.

## Human governance rule

Any change touching safety, memory exposure, or orchestration defaults requires explicit human approval before becoming default behavior.

## Acceptance and rollback summary

- **Acceptance gate:** level-specific criteria satisfied and evidence artifact complete.
- **Rollback gate:** any safety/integrity regression, unverifiable claim set, or contract break risk forces revert.
