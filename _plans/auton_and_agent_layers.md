# Auton, POMDPs, and this codebase

**Reference:** [The Auton Agentic AI Framework](https://arxiv.org/abs/2602.23720) (arXiv:2602.23720v1), §4 *Formal Agent Execution Model* — in particular Definition 4.1 (augmented tuple) and the factorized policy (§4.3–4.4).

This document models the agent here as a **decision system in a (partially observed) Markovian setting**, aligned with Auton’s **augmented POMDP** (latent world state, observations, external actions, latent reasoning, memory context, transitions, rewards). It is a design bridge, not a machine-checked specification.

---

## 1. Auton’s augmented POMDP tuple

Auton defines an **Agentic System** by the tuple

**T = ⟨S, Ω, A, Z, M, P, R⟩**

| Symbol | Name (Auton) | Role |
|--------|----------------|------|
| **S** | Latent world state | True state of the environment (other agents, full ledgers, files, etc.); **not** directly given to the policy. |
| **Ω** | Observation space | Per-timestep partial views **o**_t_ ∼ O(· \| **s**_t_). |
| **A** | External action space | Side-effecting actions; transition **P**(**s**′ \| **s**, **a**) for **a** ∈ **A**. Constrained by a **constraint manifold** (safe subspace of **A**). |
| **Z** | Latent reasoning space | Internal operations (planning, reflection, verification) that **do not** change **S**; cost tokens/time. |
| **M** | Memory context | Sufficient summary of history **H**_t_ = (**o**_0_, **a**_0_, **z**_0_, …, **o**_t_) plus retrieved long-term knowledge. |
| **P** | Transition kernel | **T**(**s**′ \| **s**, **a**); for **z** ∈ **Z**, **T**(**s**′ \| **s**, **z**) = δ(**s**′ = **s**). |
| **R** | Reward | **R** : **S** × **A** × **Z** → ℝ (sparse and/or dense; may penalize bad **z**). |

**Partial observability:** the agent does not see **s**; it acts on a **belief** or **estimate** of **S** built from **Ω** and **M**.

**Factorized policy (Auton §4.3):**

1. **z**_t_ ∼ π_reason(**z**_t_ \| **m**_t_; θ)  
2. **a**_t_ ∼ π_action(**a**_t_ \| **m**_t_, **z**_t_; ϕ)  

The paper notes both maps can share one LLM; the **runtime protocol** enforces *think-then-act*, not necessarily two models.

**Objective (§4.4):** maximize **J** = 𝔼_τ_ [ Σ_t γ^t R(**s**_t_, **a**_t_, **z**_t_) ] over an episode horizon **T**, with discount γ ∈ [0, 1).

---

## 2. Mapping: tuple → this repository

### 2.1 State **S** (latent)

The full **ecosystem** state: contents of all JSONL ledgers, other agents’ private state, full event history, constitution files on disk, research folders, etc. The running process **never** passes **S** as a struct to the model.

### 2.2 Observations **Ω** and memory **M**

At each step, `StateBuilder.build()` constructs a **`StateSnapshot`** — a **deliberately truncated, hand-engineered** view of the world:

- Constitution body and `field_chosen` (from front matter)  
- Last N public events for this agent, last K notebook lines  
- `in_commons` derived by scanning events  

So the “observation” **o**_t_ is **not** raw API bytes; it is **f**(**H**_t_) for a fixed feature map **f**. That is a **pragmatic replacement for an explicit belief state** b(**s**): a point estimate / summary of history rather than a distribution over **S**.

**M** in Auton = working history + long-term store. Here:

- **Short-term:** event slices + notebook snippets in the snapshot (and whatever the executor puts in the prompt).  
- **Long-term:** `notebook.jsonl`, evolving `constitution.md`, research artifacts — loaded only partially into each step.

### 2.3 External actions **A**

The **external** choice is the pair (**top_action**, **sub_action**) from the hierarchical vocabulary (`ActionVocabulary` / `seeds/action_vocabulary.json`). That is a **finite, typed** approximation to **A**, analogous to constraining **A** to a declared manifold.

Sampling is **π_action**-like: `Policy.propose(snapshot)` → distribution → `sample(...)` (`agent/policy.py`, `agent/decision.py`).

### 2.4 Latent reasoning **Z**

Auton treats **z** as steps that **do not** transition **S**.

In this codebase, **Z is not a separate event type on the public ledger.** Reasoning is **folded into** `Executor.execute(...)`: the adapter calls the LLM, which may run chain-of-thought or tool use **inside** that call. So:

- **Architecturally:** one step = (build **M** → choose **a** ∈ **A** → run executor, which internally realizes **z**).  
- **Compared to Auton:** the strict ordering **z** then **a** is **softened**: policy chooses **a** first; **z** is mostly **conditional on **a**** inside generation, not sampled as an explicit first-class variable with δ(**s**′=**s**) at the JSONL layer.

A future alignment path: emit internal-only **z** records (or a scratch channel) that never call `ChainWriter` for side-effecting events, then condition **a** on **z** — matching §4.3 more literally.

### 2.5 Transition **P**

When an action is taken, **ChainWriter** appends to the public (and possibly agent) ledgers; constitution/notebook may update. That defines a **deterministic** transition of **observable** traces given (**s**, **a**) plus **stochastic** LLM outputs inside execution.

The **Markov** property holds **approximately**: history beyond the snapshot window is dropped, so **P**(next \| snapshot) is **not** equivalent to **P**(next \| full **S**).

### 2.6 Reward **R** and horizon

There is **no** on-step reward wired into `decision.step` today. Auton allows sparse terminal and dense process rewards.

- **Horizon:** `max_decisions` in `run_config*.json` acts like a finite **T**.  
- **γ:** not explicit in the runner; could be tied to discounting in future RL/eval loops.  
- **Evaluation / governance:** offline metrics (e.g. `tools/analyze_run.py`, `ecosystems/*/evaluation.jsonl`) play the role of **verifiers** that could supply **R** for analysis or training.

---

## 3. End-to-end step as a POMDP-style update

Using repository symbols:

1. **Belief summary:** **m**_t_ ≈ `StateBuilder.build()` → `StateSnapshot`.  
2. **Policy:** π(**a** \| **m**_t_) implemented by `Policy.propose` + `sample` (hierarchical discrete distribution).  
3. **Execute:** LLM + templates realize internal **z** and observable outputs; side effects via writers.  
4. **Environment:** next step reads updated ledgers → new **m**_t+1_.

So the agent is formally a **POMDP-style** controller: **hidden** **S**, **partial** observations summarized in **M**, **actions** that change the world and the log.

### Action items (§3 — POMDP-style step)

- [ ] Add a short **sequence diagram** (mermaid or ASCII) in this doc or `agent/decision.py` docstring: snapshot → policy → ledger writes → next snapshot.  
- [ ] Expose **window sizes** (e.g. last 20 public / 5 notebook lines) via `run_config` or constants with one doc line tying them to **approximate Markov** error.  
- [ ] Optional: emit **`agent.latent.reasoned`** (or similar) events with **no** side-effecting writes — content = summary of **z** — so traces separate **Z** from **A** in logs.  
- [ ] Optional: refactor `decision.step` into named phases (`build_m`, `sample_a`, `execute_with_z`, `observe`) for clearer alignment with Auton §4.3 ordering experiments.

---

## 4. Layering shorthand (2026 stacks)

- **Experience / orchestration:** CLI, `run_config`, ecosystem layout under `ecosystems/<id>/`.  
- **Cognition + tooling:** `Executor` + `adapters/` (MCP-ready boundary).  
- **Memory:** notebook + constitution + event-derived snapshot = Auton’s hierarchical memory, simplified.  
- **Governance:** schemas, vocabulary hashes, verifiers — constraint manifold on **A** and on emitted payloads.

### Action items (§4 — layering)

- [ ] Add a **one-page diagram** linking experience → orchestration → cognition → memory → tooling → governance → model to **concrete entrypoints** (`__main__`, `runner`, `executor`, `adapters`, `notebook`, `core/verifier`).  
- [ ] Document **MCP** as the default **tooling layer** boundary: list required env, server layout, and how `adapters/` would attach (even if not implemented yet).  
- [ ] For **multi-agent orchestration**, sketch how `ecosystems/<id>/` + public ledger map to **shared POMDP** (other agents as part of **S** and **Ω**).  
- [ ] Align **Grafana / SQLite** exports with “governance / observability” in dashboards (panel titles or variables that match this vocabulary).

---

## 5. Earlier “Auton vs repo” one-liner table

| Auton idea | Where it lives here |
|------------|---------------------|
| Cognitive Blueprint | `run_config*.json`, `seeds/*`, `schemas/` |
| Runtime Engine | `agent/runner.py`, `agent/decision.py`, `agent/executor.py`, `agent/policy.py`, `adapters/` |
| Constraint manifold | Finite vocabulary + event schemas + verification |
| Cognitive persistence | `notebook.jsonl`, constitution, research dirs |
| Observability | JSONL events, analysis/export tools, Grafana starters |

### Action items (§5 — blueprint table)

- [ ] On each **major refactor**, update the table paths and add a **PR checklist** item (“Auton table in `_plans`?”).  
- [ ] Link **`schemas/`** and **`run_config` hash fields** to **AgenticFormat / Cognitive Blueprint** in one sentence each (README or here).  
- [ ] Add a row for **Reward / evaluation** once `R` is wired (`evaluation.jsonl`, verifiers, or training loop).  
- [ ] Add a row for **Belief / snapshot** pointing to `StateBuilder` and any future `belief_state` module.

---

## 6. Cross-cutting backlog (beyond §2 mapping)

Long-term alignment from Auton §4–7: explicit **Z**, learned or factored **beliefs**, and **reward**-connected training.

### Action items (§6)

- [ ] **π_reason then π_action:** prototype runtime flag — first LLM call produces **z** (stored only in scratch or `agent.latent.reasoned`), second call or structured head chooses **a**; compare event logs to baseline.  
- [ ] **Belief:** spike a small **b(s)** or **particle filter** over discrete world features (e.g. commons occupancy) vs current deterministic **f(H)**.  
- [ ] **R:** define sparse terminal **R** from verifier + optional dense **R** from token budget / loop detection; plumb **γ** and **T** from `run_config`.  
- [ ] **Constraint manifold:** hard **action masks** from constitution or policy (illegal leaves removed) before `sample()`.

---

*This file is for reviews and roadmap alignment; §§3–6 track concrete next steps.*
