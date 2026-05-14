# Autonomous Team Sandbox (`mult_team_test_2`)

Single 3-agent team focused on:
**how multi-team autonomous research agents collaborate to discover novel patterns**.

## Team composition

| Config | Agent ID | Role | Model |
|---|---|---|---|
| `run_config_mt2_lead.json` | `mt2-lead` | `research_lead` | `anthropic:claude-opus-4-6` |
| `run_config_mt2_tasker.json` | `mt2-tasker` | `assistant_researcher` (tasker/orchestrator) | `anthropic:claude-3-5-haiku-latest` |
| `run_config_mt2_checker.json` | `mt2-checker` | `checker` | `anthropic:claude-sonnet-4-6` |

## Shared run profile

- Ecosystem: `comm-sandbox-mt2`
- `max_decisions`: `50`
- `horizon_T`: `50`
- Peer/forum context enabled for cross-agent signal flow.
- Role-specific constitutions and role prompt pack included.

## Artiforge note for tasker

Tasker config is pre-wired with an Artiforge-oriented tool allowlist:
- `artiforge.codebase-scanner`
- `artiforge.make-project-docs`
- `artiforge.make-development-task-plan`

The constitution and prompt pack instruct Artiforge-first orchestration with manual fallback logging when calls fail.

## Validate configs

```bash
uv run python -m tools.check_run_config_hashes --base-dir . \
  --config mult_team_test_2/run_config_mt2_lead.json \
  --config mult_team_test_2/run_config_mt2_tasker.json \
  --config mult_team_test_2/run_config_mt2_checker.json
```

## Run sequence (parallel)

```bash
uv run python -m agent --base-dir . --config mult_team_test_2/run_config_mt2_lead.json &
uv run python -m agent --base-dir . --config mult_team_test_2/run_config_mt2_tasker.json &
uv run python -m agent --base-dir . --config mult_team_test_2/run_config_mt2_checker.json &
wait
```

## Post-run checks

```bash
uv run python -m tools.verify_chains --ecosystem comm-sandbox-mt2
uv run python -m tools.export_to_sqlite --db exports/mt2_dashboard.db --base-dir .
uv run python -m tools.export_trajectories --ecosystem comm-sandbox-mt2 --base-dir . --output exports/mt2_trajectories.jsonl
```
