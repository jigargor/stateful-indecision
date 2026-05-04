# Auton (arXiv:2602.23720) and this codebase

Reference: [The Auton Agentic AI Framework](https://arxiv.org/abs/2602.23720) — declarative “Cognitive Blueprint” vs platform “Runtime Engine,” constraint-based governance, hierarchical memory, MCP for tools, POMDP-style execution framing.

## Mapping (conceptual)

| Auton idea | Where it lives here |
|------------|---------------------|
| Cognitive Blueprint (declarative identity, tools, constraints) | `run_config*.json`, `seeds/constitution_seed.md`, `seeds/field_list.json`, `seeds/action_vocabulary.json`, `schemas/` |
| Runtime Engine | `agent/runner.py`, `agent/executor.py`, `agent/policy.py`, `adapters/` |
| Deterministic / schema-bound acts | Event schemas (`schemas/events.py`), canonical JSON writer, verifier; actions drawn from a fixed vocabulary |
| Constraint / policy projection | `agent/policy.py` (weighted discrete policy over leaves + hints), future: hard masks on illegal actions |
| Episodic / consolidated memory | `notebook.jsonl` with append-time fingerprint dedup; constitution drift via `constitution_manager` |
| Tooling layer | Adapters (mock / OpenAI / Anthropic); optional MCP-style external tools can sit at adapter boundary |
| Observability / governance | JSONL event streams, `tools/analyze_run.py`, `tools/export_to_sqlite.py`, Grafana SQL starters |

## Industry stack (2026 shorthand)

- **Experience / orchestration:** CLI and config-driven runs; multi-agent left to ecosystem layout (`ecosystems/<id>/`).
- **Cognition:** Template-bound generation in `executor` + model adapter.
- **Context / memory:** Notebook + field list + constitution state.
- **Protocols:** Not implementing ANP/A2A in-repo; event log + files are the interoperability surface; MCP remains the standard hook for external context servers.

This file is a bridge note for reviews and roadmap alignment, not a normative spec.
