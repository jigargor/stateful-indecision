# Level 1 Adaptation: Checkpoint -> Metrics -> Weight Tweak

This document defines the current manual adaptation loop used before in-process RL.

## Goal

Provide a reproducible, low-risk tuning path for action vocabulary and runtime knobs.

## Loop

1. **Checkpoint**
   - Freeze current run config (`run_config*.json`) and vocabulary (`seeds/action_vocabulary.json`).
   - Ensure hash fields are synced:
     - `python -m tools.sync_run_config_hashes --base-dir .`
     - `python -m tools.check_run_config_hashes --base-dir .`

2. **Collect metrics**
   - Export sqlite:
     - `python -m tools.export_to_sqlite --db dashboard.db --base-dir .`
   - Inspect key signals:
     - action mix
     - notebook duplicate ratio
     - latency and token usage
     - safety evaluation outcomes (`pass/warn/fail`, reward signal)

3. **Apply rule**
   - Select one explicit mutation rule, for example:
     - reduce duplicate pressure by increasing `RESEARCH` affinity
     - tighten unsafe or noisy leaves via `blocked_leaf_actions`
     - reduce tool-risk by shrinking `tool_allowlist`

4. **Mutate**
   - Apply small deltas only (single file or single knob family).
   - Keep defaults backward-compatible.

5. **Validate**
   - `uv run pytest -q`
   - `python -m tools.verify_chains --ecosystem alpha`
   - `python -m tools.verify_chains --ecosystem beta`
   - `python -m tools.check_run_config_hashes --base-dir .`

6. **Rollback rule**
   - If validation fails or metrics regress materially, revert the mutation and record:
     - attempted rule
     - observed failure/regression
     - follow-up hypothesis

## Output artifact

For each adaptation cycle, capture:
- starting hashes/config version
- mutation applied
- validation results
- metric delta summary
- keep/revert decision
