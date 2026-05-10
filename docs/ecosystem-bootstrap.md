# New ecosystems: templates, reset tiers, and plugins

This guide explains how to spin up a **new ecosystem** (new `ecosystem_id` under `ecosystems/`), reset state at three levels, wire **optional integrations**, and run against **OpenAI-compatible** endpoints (including local open-weight models).

## Ecosystem identity and layout

### ID rules

Ecosystem IDs are validated at runtime (`infra.storage.validate_ecosystem_id`):

- Lowercase, start with a letter, match `^[a-z][a-z0-9_-]{0,62}$` (max 63 characters).
- Reserved words are rejected (including `public`, `commons`, `evaluation`, `agents`, `corpora`, `tmp`, `test`, `none`, `null`, `default`).

### On-disk surfaces

| Surface | Path |
|--------|------|
| Public ledger | `ecosystems/<id>/public.jsonl` |
| Evaluation ledger | `ecosystems/<id>/evaluation.jsonl` |
| Commons | `ecosystems/<id>/commons.jsonl` |
| Roundtable / townhall | `ecosystems/<id>/roundtable.jsonl`, `townhall.jsonl` |
| Per agent | `ecosystems/<id>/agents/<agent_id>/constitution.md`, `notebook.jsonl`, `research/*.json` |
| Corpus | `corpora/<id>/` |
| Run lock (while an agent runs) | `ecosystems/<id>/.run.lock.<agent_id>` |

`EcosystemStorage` creates `ecosystems/<id>/` and `agents/` on first use; JSONL ledgers are created when events are written.

### RAG / vector index note

`StateBuilder` defaults to a repo-relative vector store under **`<base_dir>/.vectordb`**. That path is **not** namespaced per ecosystem in the default layout. If you use `enable_rag_retrieval: true`, a “full wipe” of `.vectordb` can affect **all** ecosystems sharing that base directory. Prefer **disabling RAG** for clean experiments, or plan a dedicated clone of the repo / base_dir per ecosystem when using RAG.

---

## Workflow: template before every new episode

1. **Choose `ecosystem_id` and `agent_id`** (valid grammar; unique agent namespace under that ecosystem).
2. **Pick a reset tier** (below) and apply the matching steps.
3. **Run config**
   - Copy an existing `run_config*.json` (for example `run_config.json` or `run_config_oss_local.example.json`).
   - Set `ecosystem_id`, `agent_id`, `max_decisions`, `seed`, memory/safety/E1 flags as needed.
   - After changing any **tracked blueprint files** referenced by hashes (`constitution_seed_path`, `field_list_path`, `action_vocabulary_path`, `executor_templates_path`, `prompt_pack_path`), run:
     - `uv run python -m tools.sync_run_config_hashes --base-dir .`
     - `uv run python -m tools.check_run_config_hashes --base-dir .`
4. **Environment**
   - Copy `.env.example` to `.env.local` (or export vars on the host). Load path is handled by `infra.env.load_env` from the repo root.
5. **Preflight**
   - Ensure no **live** process holds a run lock. Stale locks can be removed only when no agent is running (see `EcosystemStorage.acquire_run_lock` in `infra/storage.py`).
6. **Run**
   - `uv run python -m agent --base-dir . --config <your-config.json>`
7. **Post-run**
   - `uv run python -m tools.verify_chains --ecosystem <id>`
   - Optional: `uv run python -m tools.export_to_sqlite --db dashboard.db --base-dir .`

Optional human log: copy `_plans/run_log_template.md` to `_plans/runs/run_<N>_<agent_id>.md`.

---

## Reset tier A — Complete (“empty locations”)

**Goal:** No prior ledger, notebook, constitution, or research artifacts for this ecosystem; optional clean corpus and sync state.

**Steps**

1. Stop any process using this ecosystem.
2. Remove `ecosystems/<ecosystem_id>/` entirely.
3. Remove `corpora/<ecosystem_id>/` if you want a clean corpus directory for that ID.
4. Optional: remove `.sync_state/<ecosystem_id>.json` if you use S3 offload and want a fresh sync cursor (see `_plans/s3_data_offload_design.md`).
5. Optional / careful: if you used RAG and need a global vector reset, address `<base_dir>/.vectordb` knowing it may be **shared** across ecosystems (see above).
6. Use a fresh `config_version` (for example `0.0.1`), new `seed`, sync hashes after seed/template edits.
7. First run recreates directories and appends new hash-chained events.

Do **not** hand-edit or truncate JSONL to “empty” while preserving a chain — use verification-oriented tooling (`tools.merge_chains`, archives, or a new ecosystem ID).

---

## Reset tier B — Partial (“reseed”, new iteration)

**Goal:** New trajectory with new seeds / knobs without destroying unrelated ecosystems.

**Recommended:** Use a **new `ecosystem_id`** (for example `sandbox-oss-01`) or a **new `agent_id`** under the same ecosystem, plus a new `seed` and any constitution/vocabulary/prompt changes (with hash sync).

If you must reuse the same `ecosystem_id`, prefer **moving the old tree aside** (`mv ecosystems/old-id ecosystems/old-id.bak`) and then Tier A, rather than deleting individual ledger lines.

Typical edits: `constitution_seed_path`, `field_list_path`, `action_vocabulary_path`, `prompt_pack_path`, `max_decisions`, `seed`, `prompt_progression`, E1 memory keys, `blocked_leaf_actions`, `tool_allowlist`.

---

## Reset tier C — Minimal (“same memory, different model”)

**Goal:** Same ecosystem and agent; same ledgers; only change the LLM.

**Steps**

1. In run config, update **`model_spec`** (preferred form: `provider:model_id`, for example `anthropic:...` or `openai:...`) and align **`model_id`** for clarity.
2. For OpenAI-compatible servers, set **`openai_base_url`** in run config and/or **`OPENAI_BASE_URL`** in the environment (run_config wins when both are set for resolution order inside `create_adapter_auto`).
3. Do **not** bump blueprint hashes unless you changed those files.
4. Run and verify chains as usual.

The next `run.completed` event records the embedded `run_config` snapshot (including model fields).

---

## Plugins and integrations

| Capability | Configuration | Notes |
|------------|-----------------|--------|
| **Anthropic** | `model_spec`: `anthropic:<model_id>` | `ANTHROPIC_API_KEY` |
| **OpenAI / OpenAI-compatible** | `model_spec`: `openai:<model_id>` | `OPENAI_API_KEY`; optional **`openai_base_url`** in run config or **`OPENAI_BASE_URL`** for local/proxy servers (`adapters/openai_adapter.py`, `adapters.create_adapter_auto`). When `openai_base_url` / `OPENAI_BASE_URL` is set, **`OPENAI_API_KEY` may be omitted** (a placeholder key is used for the HTTP client). |
| **Mock / no API key** | Missing keys for cloud providers | `create_adapter_auto` falls back to `MockAdapter` unless OpenAI local base URL applies |
| **Web** | `tool_allowlist` includes `web.search`, `web.fetch` | Requires network egress |
| **Scite / Zotero** | Allowlist + env | See `.env.example` |
| **S3 offload** | Extra `[s3]` | See `.env.example` and `AGENTS.md` |
| **ETL** | Parquet pipeline | `uv sync --extra etl` per `AGENTS.md` |

---

## Open-source / local models (OpenAI-compatible)

There is no separate `ollama:` provider in `PROVIDER_MAP`. Use **`openai:`** with a **custom base URL**:

1. Run a local server with an OpenAI-compatible HTTP API (Ollama with OpenAI compat, LM Studio, vLLM, etc.).
2. Set in **run config** (example file `run_config_oss_local.example.json`):
   - `"model_spec": "openai:<your-local-model-name>"`
   - `"openai_base_url": "http://127.0.0.1:11434/v1"` (adjust port/path for your stack)
3. Or set **`OPENAI_BASE_URL`** in `.env.local` instead of `openai_base_url`.
4. The **`openai`** Python package is a **core** dependency of this repo (used by `OpenAIAdapter`).
5. Prefer **Tier A or B** with a dedicated **`ecosystem_id`** until you trust outputs.

Example config in repo root: **`run_config_oss_local.example.json`** (copy and adjust `model_spec`; hashes match the same seed files as `run_config.json`).

### llama.cpp Python server (disk-friendly OSS path)

When full **Ollama** installs are too large for the host, use **`llama-cpp-python`**’s built-in OpenAI-compatible server (CPU inference; a C/C++ toolchain may be required on first install):

1. `uv sync --extra local-llm` — pulls `llama-cpp-python`, `uvicorn`, `fastapi`, and server helpers.
2. Download a GGUF (not tracked; `.models/` is gitignored), e.g. [TheBloke TinyLlama Chat Q4](https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF) into `.models/tinyllama-q4.gguf`.
3. Start the server (separate terminal):

   ```bash
   uv run python -m llama_cpp.server \
     --model .models/tinyllama-q4.gguf \
     --host 127.0.0.1 --port 8088 \
     --chat_format chatml \
     --n_ctx 2048
   ```

4. Discover the model id the server exposes: `curl -s http://127.0.0.1:8088/v1/models` — use that string after `openai:` in `model_spec` (often the relative model path).
5. Run the agent with **`run_config_oss_llamacpp.json`** (or a copy), which points at `http://127.0.0.1:8088/v1` and uses `tool_allowlist: []` for a minimal local smoke run.

---

## Operational commands (reference)

See **`AGENTS.md`** for the canonical list: `pytest`, `verify_chains`, `check_run_config_hashes`, `export_to_sqlite`, `batch_etl`, etc.
