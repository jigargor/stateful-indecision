# Memory Architecture Protocol

This protocol disambiguates current memory modes and defines safe expansion rules aligned with Axis memory-context preservation.

## Scope label

- Current protocol authority: `[docs-only now]`
- Future mode extensions: `[config convention later]` and `[flagged runtime later]`

## Design goals

- Preserve durable provenance in append-only ledgers.
- Keep prompt context bounded and auditable.
- Expand memory utility through explicit gates, not hidden behavior.

## Quick reference: STM vs LTM

| Layer | Contents | Bounded? | Source code |
|---|---|---|---|
| **STM** | `recent_events[-cap:]` + `recent_notebook[-cap:]` + `recent_notebook_summary` | Yes (configurable caps) | `agent/state_builder.py` → `build()` |
| **LTM** | Full `notebook.jsonl` + constitution revisions + ledger history | No (append-only, durable) | `ecosystems/<id>/agents/<agent-id>/notebook.jsonl`, `constitution.md` |

STM is reconstructable from LTM via cap+slice; LTM is never truncated or rewritten.

## Shipped memory modes

| Mode | Source | Prompt exposure | Failure behavior | Ledger write rights | Code location |
|---|---|---|---|---|---|
| Windowed STM | Recent events + notebook slices in `StateSnapshot` | Included as bounded slices | Empty/missing data degrades gracefully | None | `state_builder.py` lines 104-110 |
| Rolling notebook summary | Deterministic summary over older notebook entries | Included as compact summary text | Falls back to `None` | None | `state_builder.py` `_summarize_notebook_prefix` |
| Belief snapshot | Derived numeric metrics (`event_density`, dup ratio, commons flag) | Used by policy/control, not full prose memory | Defaults from available history | None | `state_builder.py` `_build_belief_state` |
| RAG retrieval (optional) | Vector store retrieval path in `StateBuilder` | Optional/flag-gated | Degrades on import/relevance miss | None | `state_builder.py` `_retrieve_context` (behind `enable_rag`) |
| External visitor briefing | Latest `townhall` external-visitor session | Included when present | Omitted if no eligible event | None | `state_builder.py` `_latest_external_visitor_briefing` |
| Notebook consolidation (optional) | Groups older entries into LTM chunks (read-only) | None (offline analysis only; chunks are computed but not injected into prompt context) | Off by default (interval=0) | None | `tools/consolidate_notebook.py` `consolidate_older_entries` |

## STM/LTM boundary contract

### STM (Short-Term Memory)

- Bounded prompt-time context only.
- Must have explicit caps (`memory_recent_events_cap`, `memory_recent_notebook_cap` in run_config).
- Must be reconstructable from source references.
- Implementation: `StateBuilder.build()` in `agent/state_builder.py` — slices events and notebook texts to cap, produces `StateSnapshot`.

### LTM (Long-Term Memory)

- Durable append-only or versioned artifacts:
  - ledgers (`ecosystems/<id>/public.jsonl`)
  - notebooks (`ecosystems/<id>/agents/<agent-id>/notebook.jsonl`)
  - constitution revisions (`ecosystems/<id>/agents/<agent-id>/constitution.md`)
  - research artifacts (vector store, `.vectordb/`)
- Any consolidation must preserve traceability to source IDs.
- Implementation: `agent/notebook.py` (append interface), `tools/consolidate_notebook.py` (read-only consolidation).

## Rolling notebook summary strategy

The rolling summary (`_summarize_notebook_prefix` in `agent/state_builder.py`) is purely deterministic:

- Counts total and unique older entries.
- Extracts the last 2 entries (whitespace-normalized, capped at 120 chars each).
- Returns a compact string: `"Older notebook context: N entries (M unique). Recent older excerpts: [...]"`.
- Returns `None` when there are no older entries (all entries fit within the STM cap).

This avoids LLM-generated summaries and ensures reproducible, traceable memory context.

## Enablement rules

### RAG retrieval

Enable only when:

- dependency availability confirmed,
- retrieval provenance can be logged,
- prompt budget impact stays within wave scorecard ceiling.

Disable/fallback when:

- relevance below threshold,
- dependency import fails,
- retrieval source cannot be attributed.

### Peer/forum memory expansion (`[config convention later]`)

Optional additions:

- peer notebook snippets,
- roundtable/townhall digest previews.

Must be:

- opt-in,
- capped,
- provenance-tagged (`event_id`, `agent_id`, `ledger_path`).

## Memory continuity checkpoints

At each accepted wave:

- capture summary checkpoint artifact,
- record novelty proxy and contradiction status,
- verify no chain/hash regressions,
- archive config hash snapshot.

## Anti-patterns (forbidden in v1 strategy)

- hidden automatic rewriting of durable memory,
- uncapped peer memory injection,
- non-attributed “summary” text that cannot be traced to sources,
- migration operations that rewrite historical ledger lines.

## External guidance references

- Axis/Auton section 5: hierarchical memory + consolidation.
- Hugging Face memory controls:
  - replay, explicit memory object, step callbacks for bounded memory maintenance.
- LangGraph supervisor memory modes:
  - message-history control and checkpointer/store-backed persistence.

## Suggested future experiments (not implementation in this pass)

- Opt-in cross-agent context view with strict cap and provenance marker.
- Digest events for forum channels to reduce token footprint.
- Controlled A/B on summary strategies (deterministic vs learned) under strict rollback gates.

## Acceptance and rollback summary

- **Acceptance gate:** mode definitions include source, prompt exposure, cap, provenance, and failure behavior.
- **Rollback gate:** uncapped or non-attributed memory expansion paths are rejected until corrected.
