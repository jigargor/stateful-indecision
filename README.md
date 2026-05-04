# stateful-indecision

A ledger-first, single-agent research system building toward v1.0.0.

## Status

**Pre-release — `v0.x.x` branch tracks this phase.**

The substrate is built and verified. Three agents (`biochem-lead`, `psych-lead`, `sweng-lead`) have completed alpha runs with a combined 1,632 public ledger events and 118 notebook entries across 5 agent namespaces. The system is being hardened toward a stable v1.0.0 release.

What is working:
- Hash-chained ledgers (`public`, `commons`, `evaluation`, per-agent `notebook`) with full verification
- Frozen-uniform policy sampling across 23 action leaves
- Constitution manager with atomic append and frontmatter tracking
- Executor with prompt templates for all action types
- Alpha corpus loader and web adapter
- Commons dual-write protocol
- Firewall-enforced ecosystem path scoping
- CLI tools: `verify_chains`, `inspect_ledger`, `diff_constitution`

What is not in v1 scope (deferred to v2+):
- Multiple simultaneous agents and roundtable protocol
- Embedding-based memory retrieval
- State-conditioned policy (currently frozen-uniform)
- Live beta ecosystem web access
- User-facing UI (everything is CLI + ledger files)

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest
```

Run an agent:

```bash
python -m agent --ecosystem alpha --agent-id agent-001 --model claude-sonnet-4-6-20250514 --max-decisions 100
```

Verify and inspect after a run:

```bash
python tools/verify_chains.py --ecosystem alpha
python tools/inspect_ledger.py --ecosystem alpha --agent agent-001 --tail 50
python tools/diff_constitution.py --agent agent-001 --revisions all
```

## Repository Layout

```
stateful-indecision/
├── seeds/                  # Locked inputs: action vocabulary, field list, constitution seeds
├── schemas/                # Pydantic models for events, constitution, state, action vocabulary
├── core/                   # Canonical JSON, hash-chain writer, verifier, timestamps
├── infra/                  # Ecosystem storage + path firewall, LLM client
├── agent/                  # Policy, state builder, decision loop, executor, runner, managers
├── forums/                 # Commons implementation + v2 stubs (roundtable, townhall, t1_pulse)
├── workload/               # Alpha corpus adapter, field list loader, beta stub
├── safety/                 # Firewall validator, kill-switch monitor, kill-switch rubric
├── tools/                  # verify_chains, inspect_ledger, diff_constitution, merge_chains
├── tests/                  # Unit tests (canonical JSON, chain, firewall, vocabulary) + integration
├── corpora/alpha/          # Curated paper corpus for alpha ecosystem
└── ecosystems/alpha/       # Live ledger files and agent state (gitignored at runtime)
```

## Versioning

| Branch | Purpose |
|---|---|
| `main` | Active development toward v1.0.0 |
| `v0.x.x` | Pre-release snapshot — current merged state of all alpha runs |

v1.0.0 is defined as: all three verification commands pass, the agent runs 100 decisions cleanly, and the constitution shows at least one revision from a `REFLECT_ON_SELF` cycle.
