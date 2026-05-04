# Auton paper ↔ this codebase

**Reference:** [The Auton Agentic AI Framework](https://arxiv.org/abs/2602.23720) (arXiv:2602.23720v1). Below, headings mirror the whitepaper’s major sections. Each block has a **short summary**, **where this repo stands**, and **action items** (implementation / documentation).

---

## 1 Introduction

**Summary:** Shift from opaque, imperative agents to **declarative, auditable** specifications; LLMs as stochastic engines controlling deterministic backends.

**Here:** We treat `run_config` + `seeds/` + `schemas/` as a lightweight **blueprint** and `agent/*` + `adapters/` as **runtime**, with event logs for auditability.

### Action items

- [ ] One cross-link in the root **README** (or `AGENTS.md` if present): blueprint vs runtime + arXiv pointer.  
- [ ] Pin **paper version** (v1) in this doc when the PDF/HTML changes.

---

## 2 The Integration Paradox and Ecosystem Fragmentation

**Summary:** Mismatch between **probabilistic** model outputs and **schema-bound** systems; fragmentation across frameworks.

**Here:** **ChainWriter** + `schemas/events.py` push toward typed events; the **adapter** still bridges stochastic generation and structured append paths.

### Action items

- [ ] Tighten **output validation** on executor structured payloads (retry or reject before ledger write).  
- [ ] Document **failure modes** when the model violates schema (today’s glue path).

---

## 3 The AgenticFormat Standard

**Summary:** **Configuration over code**: language-agnostic declarative spec (YAML/JSON) for interface, tools, memory, constraints — the **Cognitive Blueprint** vs **Runtime Engine**.

**Here:** Not AgenticFormat verbatim; closest artifacts: `run_config*.json` (version, hashes, paths), `seeds/*`, `schemas/`, vocabulary JSON. **Contract-driven** behavior via event types and vocabulary.

### Action items

- [ ] Add a **one-line mapping table** in README: AgenticFormat concept → our file(s).  
- [ ] Keep **hash fields** in run configs in sync with seeds (`action_vocabulary_hash`, etc.); optional CI check.  
- [ ] Optional: **JSON Schema** (or Pydantic) export for one representative agent output type as a template for stricter contracts.

### Quick lookup: Auton concept → repo

| Auton idea | Where it lives here |
|------------|---------------------|
| Cognitive Blueprint | `run_config*.json`, `seeds/*`, `schemas/` |
| Runtime Engine | `agent/runner.py`, `agent/decision.py`, `agent/executor.py`, `agent/policy.py`, `adapters/` |
| Constraint manifold (preview) | Finite vocabulary + event schemas + verifier |
| Cognitive persistence | `notebook.jsonl`, constitution, research dirs |
| Observability | JSONL events, `tools/analyze_run.py`, export/Grafana starters |

---

## 4 Formal Agent Execution Model

**Summary:** Agent as a decision system in an **augmented POMDP**: tuple **T = ⟨S, Ω, A, Z, M, P, R⟩**, **latent reasoning space Z**, **factorized** π_reason then π_action, discounted objective **J**.

**Here:**

- **S:** Full ecosystem state (ledgers, files, other agents); never passed wholesale to the policy.  
- **Ω / M:** `StateBuilder` → `StateSnapshot` = hand-built summary **f(H)** (last N/K events, constitution, `in_commons`).  
- **A:** Hierarchical `(top_action, sub_action)` from `ActionVocabulary`.  
- **Z:** Folded into `Executor.execute` (LLM internals); **not** a separate no-side-effect ledger step yet.  
- **P:** Appends via **ChainWriter** + stochastic generation; **Markov** only approximate due to **windowing**.  
- **R / γ:** Horizon ≈ `max_decisions`; no on-step reward in `decision.step` yet; offline eval / `evaluation.jsonl` as verifier-style signal.

**End-to-end step:** **m**_t_ ← `build()` → π(**a** | **m**_t_) → execute (internal **z**) → environment → **m**_t+1_.

### Action items

- [ ] **Sequence diagram** (mermaid): snapshot → policy → writes → next snapshot (here or `agent/decision.py` docstring).  
- [ ] **Window sizes** configurable or documented (tie to approximate-Markov gap).  
- [ ] Optional **`agent.latent.reasoned`** events (no side effects) to separate **Z** from **A** in logs.  
- [ ] Optional **named phases** in `decision.step` for π_reason → π_action experiments.  
- [ ] **π_reason then π_action** behind a runtime flag (scratch **z**, then sample **a**).  
- [ ] **Belief spike:** explicit **b(s)** or particles vs deterministic **f(H)**.  
- [ ] Plumb **γ**, **T**, and sparse/dense **R** from config + verifiers when ready.

---

## 5 Cognitive Memory Architecture

**Summary:** **Hierarchical memory**: short-term event stream + long-term consolidated knowledge; **reflector-driven consolidation** to avoid unbounded context.

**Here:** **Short-term:** recent public + notebook slices in `StateSnapshot`; **long-term:** `notebook.jsonl`, `constitution.md`, research files — partially loaded per step.

### Action items

- [ ] Document **STM vs LTM** boundaries explicitly (which paths are “ephemeral window” vs “durable”).  
- [ ] Optional **consolidation** job: compress notebook/event bursts into summary lines (reflector-style).  
- [ ] **Retrieval:** if context grows, add cheap **RAG** or rolling summary before executor prompt.  
- [ ] Add table row for **Belief / snapshot** (`StateBuilder`, future `belief_state`) in §3 table when implemented.

---

## 6 Safety and Governance

**Summary:** **Constraint manifold**: project policy onto safe **A** by construction; not only post-hoc filtering.

**Here:** Finite vocabulary, event schemas, `core/verifier` patterns; **soft** biasing in `Policy.propose` — not full hard masks yet.

### Action items

- [ ] **Hard action masks** (illegal leaves removed before `sample()`), driven by constitution or policy rules.  
- [ ] **Verifier hooks** at terminal or per-step boundaries (sparse **R**).  
- [ ] Audit **privilege** story for adapters (tool allowlists à la AgenticFormat snippet).

---

## 7 Self-Evolving Agents and End-to-End Optimization

**Summary:** Multi-level improvement: in-context adaptation, distilled self-teaching, **RL** (e.g. GRPO/PPO) on multi-turn POMDPs.

**Here:** Manual / script-driven **tuning** (`seeds/action_vocabulary.json`, `run_beta_loop.py`, `analyze_run.py`); no RL loop in-process.

### Action items

- [ ] Formalize **checkpoint → metrics → weight tweak** as a documented “Level 1” adaptation path.  
- [ ] Optional: export trajectories (JSONL) in a format suitable for **offline RL** or preference training later.  
- [ ] Link **evaluation.jsonl** to explicit **R** definitions when added.

---

## 8 Inference Efficiency

**Summary:** **Cognitive Map-Reduce**, speculative inference, **dynamic context pruning** to bound latency.

**Here:** Single-threaded step loop; token metrics logged on `action.executed`; no parallel tool graph or speculative paths.

### Action items

- [ ] **Context pruning** policy for prompts (drop oldest notebook lines with a cap).  
- [ ] If multiple tools exist: **dependency-aware batching** sketch in executor.  
- [ ] Grafana panels for **p50/p95 latency** and tokens per decision (extend starter SQL).

---

## 9 Strategic Impact and Open-Source Roadmap

**Summary:** Declarative agents, standards (MCP), open ecosystem.

**Here:** Repo is a **research / simulation** substrate; MCP mentioned as future adapter boundary.

### Action items

- [ ] **MCP boundary doc:** env, server list, how `adapters/` would register tools.  
- [ ] **Multi-agent / ecosystem** note: `ecosystems/<id>/` + public ledger as shared **S** / **Ω** for peers.  
- [ ] **Layering diagram** (experience → … → model) with file pointers (fulfills cross-stack clarity).  
- [ ] PR template checkbox: update **§3 lookup table** when paths change.

---

## 10 Conclusion

**Summary:** Auton unifies blueprint vs runtime, POMDP formalism, memory, constraints, evolution, and efficiency.

**Here:** This document is the **living alignment** between that narrative and `stateful-indecision`; extend it as the runtime gains explicit **Z**, **R**, and stronger contracts.

### Action items

- [ ] Periodic **review** (e.g. quarterly): check off completed items, archive done work, add new Auton sections if the paper updates.

---

*Design bridge only — not a machine-checked specification.*
