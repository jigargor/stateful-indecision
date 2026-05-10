# stateful-indecision

A ledger-first, single-agent research runtime with a v1.0.0 package baseline.

Blueprint-vs-runtime alignment follows the Auton framing in [The Auton Agentic AI Framework (arXiv:2602.23720v1)](https://arxiv.org/abs/2602.23720).

## Status

**v1.0.0 pipeline complete.** All implementation waves (0–5, E1–E4) are delivered. 417+ tests pass across contracts, safety, memory, observability, and formalism layers.

The substrate is built and verified. Three agents (`biochem-lead`, `psych-lead`, `sweng-lead`) have completed alpha runs with a combined 1,632 public ledger events and 118 notebook entries across 5 agent namespaces. Beta ecosystem has 3,160 public events across 3 agents.

What is implemented:
- Hash-chained ledgers (`public`, `commons`, `evaluation`, per-agent `notebook`) with full verification
- 30+ Pydantic payload models with strict validation and schema export (`tools/export_event_schemas`)
- Vocabulary-weighted policy sampling with action masks (`blocked_leaf_actions`) and tool allowlist enforcement
- Constitution manager with atomic append and frontmatter tracking
- Executor with prompt templates, decision phases (`state_snapshot` → `ledger_commit`), and latent reasoning events
- Memory exposure controls: peer context, forum digest, RAG retrieval — all with configurable caps and provenance
- Multi-agent surfaces: commons, roundtable, townhall forums; map-reduce handoff protocol with checker verdicts
- Generalized ecosystem IDs with validated grammar, reserved-word checks, and firewall hardening
- Notebook consolidation with rolling summaries and novelty proxy analysis
- Observability: JSONL ledgers, SQLite export, Grafana dashboards, Parquet ETL, trajectory export
- Prompt progression (`off`, `standard`, `aggressive`) with per-step escalation hints
- Safety: hard action masks, tool allowlist, kill-switch monitoring, evaluation ledger isolation
- S3 data offload with periodic sync and spot-instance termination handling
- CLI tools: `verify_chains`, `inspect_ledger`, `diff_constitution`, `export_event_schemas`, `notebook_novelty`, `batch_etl`

What is not in v1 scope (deferred to v2+):
- Promoting `verifier_mode` to `"enforce"` by default (remains `"warn"` pending operator acceptance)
- Promoting experimental features (`enable_pi_reason_then_action`, `emit_latent_reasoning_events`) to on-by-default
- State-conditioned policy (currently frozen-uniform with masks)
- User-facing UI (everything is CLI + ledger files)

## New ecosystems and resets

See **[docs/ecosystem-bootstrap.md](docs/ecosystem-bootstrap.md)** for ecosystem IDs, full vs partial vs model-only resets, integrations, and **local OpenAI-compatible** (`openai:` + `OPENAI_BASE_URL` / `openai_base_url`) setups. Example configs: `run_config_oss_local.example.json`, `run_config_oss_llamacpp.json` (with `uv sync --extra local-llm` + GGUF under `.models/`).

## Quickstart

```bash
uv sync --extra dev
uv run pytest -q
```

Run an agent:

```bash
uv run python -m agent --ecosystem alpha --agent-id agent-001 --model claude-sonnet-4-6-20250514 --max-decisions 100
```

Verify and inspect after a run:

```bash
uv run python -m tools.verify_chains --ecosystem alpha
uv run python tools/inspect_ledger.py --ecosystem alpha --agent agent-001 --tail 50
uv run python tools/diff_constitution.py --agent agent-001 --revisions all
uv run python -m tools.check_run_config_hashes --base-dir .
uv run python -m tools.export_event_schemas
```

## Docker

A multi-stage Dockerfile is provided for reproducible, production-oriented runs (including AWS spot instances). Secrets are passed via environment variables at runtime and are never baked into the image.

### Build

```bash
# Production image (runtime deps only)
docker build -t stateful-indecision:latest .

# Dev image (includes pytest)
docker build --target dev -t stateful-indecision:dev .
```

### Run

```bash
# Run the agent with an env file and persistent ecosystem volume
docker run --rm --env-file .env.local \
  -v stateful_data:/app/ecosystems \
  stateful-indecision:latest \
  python -m agent --config run_config.json

# Show agent CLI help (default when no command is given)
docker run --rm stateful-indecision:latest
```

### Test

```bash
# Run the test suite inside the dev image
docker run --rm stateful-indecision:dev uv run pytest -q
```

### Verify and Export

```bash
# Verify ledger chains against a mounted volume
docker run --rm -v stateful_data:/app/ecosystems \
  stateful-indecision:latest \
  python -m tools.verify_chains --ecosystem alpha

# Export ledgers to SQLite for Grafana dashboards
docker run --rm \
  -v stateful_data:/app/ecosystems \
  -v "$(pwd)/exports:/app/exports" \
  stateful-indecision:latest \
  python -m tools.export_to_sqlite --db exports/dashboard.db
```

### Mutable State and Volumes

The container writes runtime state to these paths:

| Path | Contents |
|---|---|
| `ecosystems/<id>/` | Ledgers, notebooks, constitutions, research artifacts, run locks |
| `run_config*.json` | Config version bump at end of run (ephemeral inside container) |
| `seeds/action_vocabulary.json` | Vocabulary mutations (ephemeral inside container) |
| `corpora/<ecosystem>/` | Fetched corpus data (ephemeral inside container) |

Mount `/app/ecosystems` as a Docker volume or cloud block storage to persist ledger data across runs. Config and seed files are baked into the image; if cross-run persistence of config bumps is needed, bind-mount those files individually.

### S3 Data Offload

For long-running or multi-run deployments where EBS will fill, ecosystem data can be archived to S3. Install the S3 extra and enable via environment variables:

```bash
# Build S3-enabled image
docker build --target s3 -t stateful-indecision:s3 .

# Run with S3 offload enabled
docker run --rm --env-file .env.local \
  -e S3_OFFLOAD_ENABLED=1 \
  -e S3_OFFLOAD_BUCKET=my-bucket \
  -e S3_OFFLOAD_PREFIX=prod \
  -e AWS_REGION=us-east-1 \
  -v stateful_data:/app/ecosystems \
  stateful-indecision:s3 \
  python -m agent --config run_config.json

# Manual sync (without running agent)
docker run --rm --env-file .env.local \
  -e S3_OFFLOAD_ENABLED=1 \
  -e S3_OFFLOAD_BUCKET=my-bucket \
  -v stateful_data:/app/ecosystems \
  stateful-indecision:s3 \
  python -m infra.s3_sync --ecosystem alpha --mode once
```

When `S3_OFFLOAD_ENABLED=1`, the entrypoint uses a Python supervisor that handles SIGTERM by running a shutdown sync before forwarding the signal. The agent runner also starts a background periodic sync thread.

S3 bucket layout mirrors the local filesystem: `s3://<bucket>/<prefix>/ecosystems/<id>/...`. Sync state is tracked in `.sync_state/<ecosystem>.json` (excluded from the image via `.dockerignore`). Research artifacts are bundled as tarballs by default (`S3_RESEARCH_MODE=bundle`).

After restoring or syncing data locally, periodic batch analytics can merge ledgers into Parquet and extract research bodies separately: `uv sync --extra etl` then `uv run python -m tools.batch_etl --base-dir . --out-dir ./etl_warehouse` (see `AGENTS.md`).

See `.env.example` for the full list of S3 env vars, and `_plans/s3_data_offload_design.md` for the complete design document.

### Spot-Instance Termination

AWS spot sends SIGTERM with a ~2-minute grace window. The entrypoint uses `exec` so the Python process is PID 1 and receives the signal directly. Each decision's JSONL append is atomic (file-locked + fsynced), so a SIGTERM between decisions loses no data. A SIGTERM mid-decision may leave one partial event line, which the chain verifier will flag and the next run can tolerate.

If the container is killed (SIGKILL after the grace window), a stale `.run.lock` may remain:

```bash
# Clear a stale run lock after spot termination
docker run --rm -v stateful_data:/app/ecosystems \
  stateful-indecision:latest \
  rm -f /app/ecosystems/alpha/.run.lock
```

### Environment Variables

Copy `.env.example` to `.env.local` and fill in your keys. Supported variables:

- `ANTHROPIC_API_KEY` (required)
- `OPENAI_API_KEY` (optional, not currently in deps)
- `SCITE_API_KEY`, `SCITE_PARTNER_KEY` (optional)
- `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_ID` (optional)
- `S3_OFFLOAD_ENABLED`, `S3_OFFLOAD_BUCKET`, `S3_OFFLOAD_PREFIX`, `AWS_REGION` (optional, for S3 offload)

## Repository Layout

```
stateful-indecision/
├── seeds/                  # Locked inputs: action vocabulary, field list, constitution seeds
├── schemas/                # Pydantic models for events, constitution, state, action vocabulary
│   └── generated/          # Auto-generated JSON Schema exports (tools/export_event_schemas)
├── core/                   # Canonical JSON, hash-chain writer, verifier, timestamps
├── infra/                  # Ecosystem storage + path firewall, LLM client
├── agent/                  # Policy, state builder, decision loop, executor, runner, managers
├── adapters/               # LLM adapter boundary and provider implementations
├── forums/                 # Commons + structured forum ledgers (roundtable, townhall, t1_pulse)
├── workload/               # Alpha corpus adapter, field list loader, beta stub
├── safety/                 # Firewall validator, kill-switch monitor, kill-switch rubric
├── tools/                  # verify_chains, inspect_ledger, diff_constitution, export_event_schemas, notebook_novelty, batch_etl
├── prompts/                # Prompt packs for team roles
├── tests/                  # 417+ tests across contracts, safety, memory, observability, formalism
├── corpora/alpha/          # Curated paper corpus for alpha ecosystem
└── ecosystems/<id>/        # Live ledger files and agent state (gitignored at runtime)
```

## Auton Concept Mapping

| Auton concept | Where it maps here |
|---|---|
| Cognitive Blueprint | `run_config*.json`, `seeds/*`, `schemas/` |
| Runtime Engine | `agent/runner.py`, `agent/decision.py`, `agent/executor.py`, `agent/policy.py`, `adapters/` |
| Constraint manifold | Action vocabulary + event schemas + verifier |
| Cognitive persistence | `notebook.jsonl`, constitution files, `research/` artifacts |
| Observability | JSONL ledgers + `tools/*` analysis/export + Grafana starter assets |

## Memory Boundaries (STM vs LTM)

- **Short-term memory (STM):**
  - Active prompt window slices from recent public events and recent notebook entries.
  - Configurable caps via `memory_recent_events_cap` and `memory_recent_notebook_cap` in `run_config*.json`.
- **Long-term memory (LTM):**
  - Durable notebook ledger (`notebook.jsonl`)
  - Constitution state (`constitution.md`)
  - Stored artifacts (`agents/<id>/research/*.json`)
  - Shared ecosystem ledgers (`public.jsonl`, `commons.jsonl`, forum ledgers)
- **Consolidation path:**
  - `tools/consolidate_notebook.py` summarizes notebook repetition patterns.
  - Rolling summary from older notebook entries is included in the runtime prompt context.

## Runtime Decision Phases

Decision execution is tracked as ordered phases:
- `state_snapshot`
- `policy_proposal`
- `policy_sample`
- `executor_run`
- `ledger_commit`

These phases are emitted on `action.executed` payloads for observability and formalism alignment.

## MCP and Adapter Boundary

- `adapters/` defines the model execution boundary (`LLMAdapter`) and provider-specific implementations.
- `agent/executor.py` is the side-effect router and enforces tool allowlist policy from run config.
- MCP-style integration should stay behind adapter registration points rather than direct runtime writes.
- Model-output failures are handled explicitly for structured actions (`ANALYZE`, `ANNOTATE`) using retry + validation-failure markers.

## Privilege and Tool Controls

- Tool access is centrally constrained through run-config `tool_allowlist`.
- Policy-level action admissibility is constrained through `blocked_leaf_actions` masks before sampling.
- Executor-side checks enforce allowlist decisions and emit explicit blocked side-effect markers when denied.
- This keeps adapter and side-effect privilege decisions auditable in event logs.

## Reward and Evaluation Signals

- `evaluation.jsonl` includes `safety.trigger.evaluated` entries.
- Each evaluation entry carries:
  - `outcome` (`pass`, `warn`, `fail`)
  - `reward_mode` (`sparse` or `dense`)
  - `reward_signal` numeric value
- Run-config fields `reward_mode`, `discount_gamma`, and `horizon_T` provide reward metadata for downstream analysis.

## Multi-Agent and Ecosystem Note

- Each `ecosystems/<id>/` directory is an isolated shared world surface.
- Within one ecosystem, `public.jsonl` acts as shared observable state `S/Ω` for all participating agents.
- Forum ledgers (`commons`, `roundtable`, `townhall`) provide structured interaction channels over that shared state.

## Versioning

| Branch | Purpose |
|---|---|
| `main` | v1.0.x — all implementation waves complete; steady-state operation |
| `v0.x.x` | Legacy pre-release snapshots and historical experiment states |

v1.0.0 is defined as: all verification commands pass, the agent runs 100 decisions cleanly, and the constitution shows at least one revision from a `SELF_REFLECT` cycle. All implementation waves (0–5, E1–E4) are delivered on this baseline.

## Operational Playbooks

- Grafana and sqlite dashboard setup: `tools/README-Grafana.md`
- Level 1 adaptation loop (checkpoint -> metrics -> weight tweak): `tools/README-Level1-Adaptation.md`
- Quarterly alignment review checklist: `_plans/quarterly_review_checklist.md`
