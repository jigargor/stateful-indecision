# Baseline Gap Map

This document records the current shipped baseline before any new orchestration or memory expansion work.

## Scope

- Status date: 2026-05-06
- Runtime family: v1.0.x stabilization
- Intended use: planning and promotion gating only (`[docs-only now]`)

## Current baseline snapshot

### Shipped now

- Serial single-process decision loop in `agent/runner.py` and `agent/decision.py`.
- Prompt-role team behavior through `team_role` + prompt pack in `agent/executor.py`.
- Append-only hash-linked ledgers with verification via `core/writer.py` and `core/verifier.py`.
- Hard action masks and tool allowlists:
  - `blocked_leaf_actions` enforced in `agent/policy.py`
  - `tool_allowlist` enforced in `agent/executor.py`
- Safety/evaluation events (`safety.trigger.*`) and reward metadata surfaces in `evaluation.jsonl`.
- Prompt progression controls (`off`, `standard`, `aggressive`) in runtime config.
- Optional `pi_reason` path and latent reasoning event path (flag-gated).
- S3 offload + ETL export toolchain (`infra/s3_sync.py`, `tools/batch_etl.py`, `tools/export_to_sqlite.py`).

### Available behind flags or optional deps

- RAG retrieval path in `agent/state_builder.py` (`enable_rag_retrieval`) with optional vector/embedding dependencies.
- Prompt-pack role overlays (`prompt_pack_path`) and team role routing (`team_role`).
- Emitted latent reasoning events (`emit_latent_reasoning_events`).

### Documentation gaps

- Existing Auton mapping doc still contains stale text in places (`_plans/auton_and_agent_layers.md`) around:
  - mask behavior wording
  - old wave completion assumptions not aligned to current code paths
- README memory wording suggests prompt exposure of recent public events, but current prompt content is narrower than full ledger surface.

### Requires runtime changes (not in this pass)

- True scheduler-level multi-agent federation.
- Default prompt inclusion of cross-agent forum context.
- Generalized ecosystem IDs beyond hard-coded `alpha`/`beta`.

## Owner surface map

| Surface | Primary files | Responsibility |
|---|---|---|
| Runner/config | `agent/runner.py`, `run_config*.json` | Decision-loop setup, runtime knobs, lifecycle gates |
| Policy/control | `agent/policy.py` | Action admissibility and sampling |
| State/memory | `agent/state_builder.py`, `agent/notebook.py`, `agent/constitution_manager.py` | Snapshot composition, STM/LTM stitching |
| Side effects/tools | `agent/executor.py`, `workload/*`, `forums/*` | Tool usage, forum writes, artifact writes |
| Storage/firewall | `infra/storage.py`, `safety/firewalls.py` | Path safety, ledger boundaries, run locks |
| Safety/eval | `safety/kill_switch.py` | Pass/warn/fail governance signals |
| Observability/export | `tools/export_to_sqlite.py`, `tools/batch_etl.py`, `tools/notebook_novelty.py` | Analytics and adaptation evidence |

## Auton concept mapping matrix

| Auton concept | Current repo primitive | Gap | Risk if ignored | Next action | Out-of-scope boundary |
|---|---|---|---|---|---|
| AgenticFormat (blueprint/runtime split) | `run_config*.json`, `seeds/*`, `schemas/*` vs `agent/*` runtime | No single canonical schema artifact for all blueprint fields | Drift between declared config and runtime behavior | Keep hash sync + schema export + doc index of control fields | Full formal AgenticFormat transpiler |
| Constraint manifold | Hard masks (`agent/policy.py`), tool allowlist (`agent/executor.py`), storage firewall (`infra/storage.py`), verifier/safety events | Constraint spec is spread across files | Safety regressions from inconsistent enforcement semantics | Publish one strategy constraint map and acceptance gates | Symbolic optimization/KKT implementation |
| STM/LTM/consolidation | Snapshot + notebook + constitution + ledgers + consolidation tools | Prompt context narrower than full durable memory | Agents appear to “forget” shared context despite durable logs | Define memory mode contract + enablement conditions | Fully automatic LLM memory rewrite |
| Level 1/2/3 evolution | Level-1 adaptation doc exists; Level-2/3 mostly conceptual | Promotion criteria and rollback gates not unified | Unsafe/low-quality training changes promoted ad hoc | Training protocol with level-specific gates | Online RL in v1 runtime |
| Cognitive map-reduce | Current v1 is serial + role prompts, no scheduler | No orchestrator for parallel team execution | Premature complexity or under-scaling with wrong topology | Stage A/B/C roadmap with explicit decision rules | Live scheduler implementation in this pass |
| Augmented POMDP | `StateSnapshot` (`Omega/M`), action vocabulary (`A`), ledger transitions (`P`), eval rewards (`R`) | Formalism not consistently tied to operational gates | Confusion between theoretical framing and deployable controls | Baseline matrix + wave scorecard fields mapped to tuple components | Formal proof-oriented runtime |

## External evidence anchors for protocol design

- Auton paper sections 4/5/6/7/8 for execution model, memory hierarchy, constraint manifold, evolution levels, and efficiency (`uploads/2602.23720v1-0.md`).
- AutoGen team guidance:
  - “start with a single agent for simpler tasks” and escalate only when needed
  - round-robin and selector-group patterns for team control
  - source: `microsoft.github.io/autogen` docs.
- Hugging Face smolagents:
  - explicit agent memory surfaces (`agent.memory`, replay, step callbacks)
  - orchestrator-with-specialists pattern
  - source: `huggingface.co/docs/smolagents`.
- LangGraph supervisor:
  - hierarchical supervisor pattern, message-history modes, compile-time memory/checkpointer wiring
  - source: `langchain-ai.github.io/langgraphjs/reference/modules/langgraph-supervisor.html`.
- CAMEL (NeurIPS 2023):
  - role-playing multi-agent cooperation and known failure patterns (role drift/loops), useful for guardrails.

## Promotion-gate implications

- Any horizontal-growth proposal must first prove:
  - chain integrity unchanged,
  - safety fail budget unchanged or improved,
  - novelty and artifact yield not regressing,
  - tool-risk not increased without explicit approval.

## Acceptance and rollback summary

- **Acceptance gate:** baseline and Auton matrix remain code-consistent and source-cited.
- **Rollback gate:** if any baseline assertion is disproven by runtime behavior, dependent strategy docs must be revised before promotion.
