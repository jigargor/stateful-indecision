# Stateful Indecision (v1)

This repository contains the v1 runtime scaffold for a single-agent, ledger-first research system.

## Scope

- Ecosystem support: `alpha` (active), `beta` (stubbed)
- Single-threaded, single-agent runner
- Hash-chained ledgers with verification tooling
- Frozen-uniform policy across 23 action leaves
- No live beta web calls, no embeddings retrieval, no multi-agent runtime

## Quickstart

1. Create a Python 3.12+ virtual environment.
2. Install dependencies:
   - `pip install -e .[dev]`
3. Run tests:
   - `pytest`
4. Run the agent:
   - `python -m agent --ecosystem alpha --agent-id agent-001 --max-decisions 5`

## Repository Layout

Key packages:

- `core/`: canonical serialization, hash-chain writer, verification, timestamps
- `infra/`: ecosystem storage + firewall paths, LLM client
- `schemas/`: pydantic models for events, constitution, state, action vocabulary
- `agent/`: policy, state builder, decision loop, executor, runner, constitution/notebook managers
- `forums/`: commons implementation + v2 stubs
- `workload/`: alpha corpus adapter + beta stubs
- `safety/`: firewall validator + kill-switch monitor
- `tools/`: ledger and constitution inspection CLIs
- `tests/`: unit + integration tests (with mock fallback)
