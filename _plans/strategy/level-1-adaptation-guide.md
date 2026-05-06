# Level 1 Adaptation Guide: Checkpoint-Tune Cycle

Scope: `[docs-only]` — no runtime changes.
Reference: [`training-protocol.md`](training-protocol.md) § Level 1.

## Overview

Level 1 adaptation is a **manual, single-mutation** workflow for tuning agent
behavior within the existing runtime. Each cycle follows a strict
checkpoint → collect → mutate → gate → accept/revert sequence. The mutation
is always exactly one change at a time, and rollback is always available.

This guide does **not** cover Level 2 (STaR-style candidate generation) or
Level 3 (offline RL / trajectory optimization). Those are out of scope until
the respective waves are approved.

## Prerequisites

- All validation gates pass on the current codebase.
- You have access to the tools described below.
- The ecosystems you plan to measure have recent ledger data.

## Step 1: Checkpoint config/hash state

Record the current configuration fingerprint so you can revert cleanly.

```bash
uv run python -m tools.check_run_config_hashes --base-dir .
```

Save or note the output hash set. This is your **rollback anchor**. If the
mutation fails gates, you restore these hashes to revert.

What to record:
- Run config hashes (printed by the command above).
- Git HEAD commit or working-tree state (for non-config files).
- Any prompt pack or seed file content hashes if the mutation targets those.

## Step 2: Collect baseline metrics

Export current data and gather the metrics you will compare against after
mutation.

### Export SQLite dashboard

```bash
uv run python -m tools.export_to_sqlite --db /tmp/baseline_dashboard.db --base-dir .
```

### Metrics to collect

| Metric | Source query | Where |
|--------|------------|-------|
| Action mix | Query 2/3 in `grafana_starter_queries.sql` | `dashboard.db` |
| Novelty proxy | `python -m tools.notebook_novelty --ecosystem <id> ...` | CLI output |
| Safety outcomes | Evaluation ledger events | `ecosystems/<id>/evaluation.jsonl` |
| Token usage (avg, total) | Query 11 in `grafana_starter_queries.sql` | `dashboard.db` |
| Latency (p50, p95) | Query 10 in `grafana_starter_queries.sql` | `dashboard.db` |
| Stop reason distribution | Query 9 in `grafana_starter_queries.sql` | `dashboard.db` |

Record these values in a scorecard document or table for comparison.

## Step 3: Define and apply one mutation

### Allowed mutation families

1. **Prompt pack edit** — modify `seeds/*.md`, prompt templates, or system
   instructions that shape agent behavior.
2. **Action mask adjustment** — change action vocabulary weights, enable/disable
   specific actions, or adjust sampling parameters in the run config.
3. **Run-config convention change** — conservative adjustments to
   `run_config*.json` fields (e.g., `max_decisions`, `prompt_progression`).

### Rules

- Apply **exactly one** mutation family per cycle.
- Keep the change small and reversible.
- Document what you changed and why before applying.

### After applying

If you modified any tracked files (run configs, seeds, schemas), sync hashes:

```bash
uv run python -m tools.sync_run_config_hashes --base-dir .
```

## Step 4: Run acceptance gates

All four gates must pass. Any failure means the mutation is rejected.

```bash
# Gate 1: Full test suite
uv run pytest -q

# Gate 2: Chain integrity (alpha)
uv run python -m tools.verify_chains --ecosystem alpha

# Gate 3: Chain integrity (beta)
uv run python -m tools.verify_chains --ecosystem beta

# Gate 4: Config hash consistency
uv run python -m tools.check_run_config_hashes --base-dir .
```

## Step 5: Collect post-mutation metrics

Repeat the metric collection from Step 2, using a separate database:

```bash
uv run python -m tools.export_to_sqlite --db /tmp/post_mutation_dashboard.db --base-dir .
```

Compare against baseline. Look for:
- **Action mix shift**: did the distribution change in the intended direction?
- **Novelty gain**: did notebook novelty proxy improve?
- **Safety regression**: any new safety failures in the evaluation ledger?
- **Token/latency regression**: significant cost or speed changes?
- **Stop reason shift**: unexpected increase in `max_tokens` stops?

## Step 6: Accept or revert

### Accept

If all gates pass and metrics show intended improvement without regression:

1. Record the mutation, before/after metrics, and rationale in a scorecard.
2. Keep the changes in the working tree (or commit if appropriate).
3. The new hash state becomes the next cycle's rollback anchor.

### Revert

If any gate fails or metrics show unacceptable regression:

1. Restore the files to their pre-mutation state (git checkout or manual revert).
2. Re-sync hashes to the original state:

```bash
uv run python -m tools.sync_run_config_hashes --base-dir .
```

3. Verify gates pass again:

```bash
uv run pytest -q
uv run python -m tools.check_run_config_hashes --base-dir .
```

4. Record the revert reason in the scorecard.

## Worked Example: Adjusting prompt progression

### Scenario

The beta ecosystem shows low action diversity (90%+ `research` actions). We
hypothesize that switching `prompt_progression` from `"off"` to `"standard"`
will encourage agents to explore broader action vocabulary in later decisions.

### Cycle

1. **Checkpoint**: run `check_run_config_hashes` — record hash set `{abc123...}`.
2. **Baseline**: export dashboard, note beta action mix is 91% research / 5%
   commons / 4% other.
3. **Mutate**: edit `run_config_beta.json`, set `"prompt_progression": "standard"`.
   Run `sync_run_config_hashes`.
4. **Gate**: run all four acceptance gates — all pass.
5. **Post-metrics**: after a new run, export dashboard. Beta action mix is now
   78% research / 12% commons / 10% other. Novelty proxy improved 8%.
   No safety regressions.
6. **Decision**: **accept**. Record before/after in scorecard. New hash set
   `{def456...}` is the next rollback anchor.

## Scorecard template

```
Mutation ID:        L1-YYYY-MM-DD-NNN
Mutation family:    [prompt-pack | action-mask | run-config]
Description:        <what was changed and why>
Baseline hashes:    <check_run_config_hashes output>
Post-mutation hashes: <check_run_config_hashes output>

Metrics:
  Action mix (before):  <values>
  Action mix (after):   <values>
  Novelty proxy (before): <value>
  Novelty proxy (after):  <value>
  Safety outcomes:      <pass/fail count>
  Token avg (before):   <value>
  Token avg (after):    <value>
  Latency p50/p95 (before): <values>
  Latency p50/p95 (after):  <values>

Gates:
  pytest:               [pass/fail]
  verify_chains alpha:  [pass/fail]
  verify_chains beta:   [pass/fail]
  check_run_config:     [pass/fail]

Decision:             [accept / revert]
Rationale:            <explanation>
```

## References

- [Training Protocol](training-protocol.md) — full three-level specification.
- [Wave 4 Spec](../_plans/waves/wave-4-observability-and-evolution.md) — wave context.
- [AGENTS.md](../../AGENTS.md) — project standards and operational commands.
