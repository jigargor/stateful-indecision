# Multi-team communication sandbox (`mult_team_test_1`)

Two teams × two agents share ecosystem **`comm-sandbox-mt1`**. Leads use **Claude Opus 4.6**; taskers use **Claude Sonnet 4.6**. Each agent runs **30** decisions with **`prompt_progression`: `standard`**.

## Layout

| Config | Agent ID | Role | Model |
|--------|----------|------|--------|
| `run_config_mt1_team_a_lead.json` | `mt1-a-lead` | `research_lead` | `anthropic:claude-opus-4-6` |
| `run_config_mt1_team_a_tasker.json` | `mt1-a-tasker` | `assistant_researcher` | `anthropic:claude-sonnet-4-6` |
| `run_config_mt1_team_b_lead.json` | `mt1-b-lead` | `research_lead` | `anthropic:claude-opus-4-6` |
| `run_config_mt1_team_b_tasker.json` | `mt1-b-tasker` | `assistant_researcher` | `anthropic:claude-sonnet-4-6` |

Blueprint files unique to this study:

- `constitution_comm_sandbox_seed.md` — scope and research focus (coordination, ledgers, peer/forum context).
- `fields_comm_coordination.json` — field tags for constitution / state.

## Closed-world / no live tools

- **`tool_allowlist`:** `[]` (no `web.search`, `web.fetch`, etc.).
- **`enable_rag_retrieval`:** `false`.
- **`research_seed_doc_ids`:** `[]`.

Agents still see the **sage** prompt pack text (including external URLs in the pack copy); the **constitution** above defines the operative sandbox scope. For stricter alignment, maintain a forked prompt pack and update hashes.

## Observability (cross-team + cross-role)

- **`enable_peer_context`:** `true` with **`peer_context_cap`:** `8000` (character budget per peer notebook segment).
- **`enable_forum_digest`:** `true` with **`forum_digest_cap`:** `8000` — injects recent **`roundtable.utterance`** and townhall speech into prompts so leads’ roundtable lines (when sampled) propagate to others.

**Runtime caveats (see repo behavior):**

- Each `VISIT_ROUNDTABLE` action uses a **single-agent participant list** in the executor; multiple agents still append to the **same** `roundtable.jsonl`, and the forum digest reads those utterances.
- Roundtable / commons / townhall **speech text is truncated** in the executor (short character limit per utterance). Long findings belong in **notebook** (visible via peer context).

## `config_version` note

Runner parsing requires **`MAJOR.MINOR.PATCH` with integer parts only** (no `-mt1` suffixes). Versions **`>= 1.0.0`** also hit a deliberate hard-stop in `agent/runner.py`; these sandbox configs use **`0.9.201`** so runs proceed. The `knob_changelog` field still labels the mult-team study.

## First-time setup

1. From repo root, install deps: `uv sync` (plus dev if you run tests).
2. Environment: `ANTHROPIC_API_KEY` (e.g. `.env.local` from `.env.example`).
3. **Reset (recommended):** remove `ecosystems/comm-sandbox-mt1/` if you need a clean chain (Tier A in `docs/ecosystem-bootstrap.md`).
4. Validate hashes:  
   `uv run python -m tools.check_run_config_hashes --base-dir . --config mult_team_test_1/run_config_mt1_team_a_lead.json --config mult_team_test_1/run_config_mt1_team_a_tasker.json --config mult_team_test_1/run_config_mt1_team_b_lead.json --config mult_team_test_1/run_config_mt1_team_b_tasker.json`

## Running four agents

Each process is independent; use separate terminals or a process pool. Example (stagger if you hit rate limits):

```bash
uv run python -m agent --base-dir . --config mult_team_test_1/run_config_mt1_team_a_lead.json &
uv run python -m agent --base-dir . --config mult_team_test_1/run_config_mt1_team_a_tasker.json &
uv run python -m agent --base-dir . --config mult_team_test_1/run_config_mt1_team_b_lead.json &
uv run python -m agent --base-dir . --config mult_team_test_1/run_config_mt1_team_b_tasker.json &
wait
```

Reference pattern: `tools/run_beta_loop.py` (parallel subprocesses, one config each).

## Post-run

```bash
uv run python -m tools.verify_chains --ecosystem comm-sandbox-mt1
uv run python -m tools.export_to_sqlite --db exports/mt1_dashboard.db --base-dir .
```

Inspect forums:

- `ecosystems/comm-sandbox-mt1/roundtable.jsonl`
- `ecosystems/comm-sandbox-mt1/commons.jsonl`
- Per agent: `ecosystems/comm-sandbox-mt1/agents/<agent-id>/notebook.jsonl`

Grafana starter SQL already counts roundtable utterances by ecosystem (`tools/grafana_starter_queries.sql` / `tools/README-Grafana.md`).

## Hash maintenance

If you edit `constitution_comm_sandbox_seed.md`, `fields_comm_coordination.json`, or any other hashed blueprint path in these configs:

```bash
uv run python -m tools.sync_run_config_hashes --base-dir . \
  --config mult_team_test_1/run_config_mt1_team_a_lead.json \
  --config mult_team_test_1/run_config_mt1_team_a_tasker.json \
  --config mult_team_test_1/run_config_mt1_team_b_lead.json \
  --config mult_team_test_1/run_config_mt1_team_b_tasker.json
```
