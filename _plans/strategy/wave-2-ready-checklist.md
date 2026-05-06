# Wave 2 Ready-to-Execute Checklist

Scope label: `[flagged runtime later]`  
Wave: `2 — Memory Window and Consolidation`  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/waves/wave-2-memory-window-and-consolidation.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-2-memory-window-and-consolidation.md)
- Memory architecture protocol:
  - [`_plans/strategy/memory-architecture.md`](/home/ubuntu/stateful-indecision/_plans/strategy/memory-architecture.md)

## A) Scope lock and success criteria

- [ ] Confirm Wave 2 does NOT introduce new write paths to evaluation ledger.
- [ ] Confirm Wave 2 does NOT modify ledger schema or event envelope structure.
- [ ] Confirm Wave 2 non-goals:
  - [ ] no RAG implementation beyond existing stub (stays optional/flag-gated)
  - [ ] no cross-ecosystem memory sharing
  - [ ] no automatic rewriting of durable ledger content
  - [ ] no migration of historical notebook entries
- [ ] Record baseline thresholds for this wave:
  - [ ] context-pressure resilience (token budget ceiling per prompt)
  - [ ] memory stability (no regressions in chain verification)
  - [ ] notebook consolidation quality (unique vs duplicate ratio)
  - [ ] rolling summary accuracy (covers all older entry themes)

## B) Config contract verification (ALREADY DONE — verify only)

Status: `recent_events_cap` and `recent_notebook_cap` were implemented in E1 and are wired from run_config in `agent/runner.py` (lines 508-509) as `memory_recent_events_cap` and `memory_recent_notebook_cap`.

- [ ] Verify `memory_recent_events_cap` reads from run_config with default `20`.
- [ ] Verify `memory_recent_notebook_cap` reads from run_config with default `5`.
- [ ] Verify both are passed to `StateBuilder.__init__` and enforced via slicing.
- [ ] Verify `_validate_run_config_modes` in `runner.py` validates the int keys correctly (non-negative enforcement exists for `peer_context_cap`, `forum_digest_cap`, `memory_context_total_cap` — confirm same pattern applies or add for memory caps).
- [ ] Document that these keys are stable and part of the v1 contract.

## C) STM/LTM boundary documentation

Status: `_plans/strategy/memory-architecture.md` already defines the mode table and boundary contract. Needs verification and discoverability.

- [ ] Verify `memory-architecture.md` mode table is accurate against current implementation:
  - [ ] **Windowed STM**: confirm `StateBuilder` slices recent events/notebook to cap (lines 104, 110).
  - [ ] **Rolling notebook summary**: confirm `_summarize_notebook_prefix` exists and produces summary from older entries (line 112, lines 230-241).
  - [ ] **Belief snapshot**: confirm `_build_belief_state` returns `event_density`, `notebook_dup_ratio`, `in_commons` (lines 467-487).
  - [ ] **RAG retrieval**: confirm flag-gated behind `enable_rag` (line 129).
  - [ ] **External visitor briefing**: confirm `_latest_external_visitor_briefing` loads from townhall ledger (line 134).
- [ ] Verify STM/LTM boundary definitions match implementation:
  - [ ] STM = `recent_events[-cap:]` + `recent_notebook[-cap:]` + `recent_notebook_summary` (bounded, reconstructable).
  - [ ] LTM = full notebook.jsonl + constitution revisions + ledger history (append-only, durable).
- [ ] Add cross-reference from `memory-architecture.md` to relevant code locations.
- [ ] Ensure `_plans/strategy/strategy-index.md` links to `memory-architecture.md` for discoverability.
- [ ] Add an explicit STM/LTM diagram or summary table at the top of `memory-architecture.md` if not present.

## D) Notebook consolidation implementation

Status: `tools/consolidate_notebook.py` already provides `group_into_ltm_chunks` and `embed_ltm_chunks`. Needs a reflector-style hook callable from the runtime (not just CLI).

- [ ] Implement `consolidate_older_entries(entries, recent_cap, chunk_size)` as a library function importable by the runtime.
  - Current `group_into_ltm_chunks` already groups older entries. Confirm it can be called programmatically without argparse.
- [ ] Add a consolidation hook interface that can be invoked:
  - [ ] After a run completes (post-run consolidation).
  - [ ] Optionally per-N-decisions (configurable via run_config key `notebook_consolidation_interval`, default `0` = off).
- [ ] Consolidation must:
  - [ ] Preserve source event IDs (traceability to original notebook entries).
  - [ ] Deduplicate (use existing fingerprint logic from `Notebook._existing_fingerprints`).
  - [ ] Produce a deterministic summary chunk (no non-attributed text).
  - [ ] Not modify the source notebook.jsonl (append-only invariant preserved).
- [ ] Wire optional `notebook_consolidation_interval` from run_config in `runner.py` with default `0` (off).
- [ ] Validate `notebook_consolidation_interval` as non-negative int in `_validate_run_config_modes`.

## E) Rolling summary hook verification and documentation

Status: `_summarize_notebook_prefix` in `state_builder.py` (lines 230-241) already provides a deterministic rolling summary. Needs verification, documentation, and test coverage.

- [ ] Verify `_summarize_notebook_prefix` behavior:
  - [ ] Empty input returns `None`.
  - [ ] Non-empty input produces summary with entry count, unique count, and last 2 excerpts.
  - [ ] Excerpts are capped at 120 chars each (whitespace-normalized).
  - [ ] Return value is included in `StateSnapshot.recent_notebook_summary`.
- [ ] Verify prompt assembly uses `recent_notebook_summary` when non-None:
  - [ ] Check `agent/executor.py` includes it in prompt context.
- [ ] Document summary strategy in `memory-architecture.md`:
  - [ ] Explain deterministic approach (count + excerpts, no LLM-generated text).
  - [ ] Note this is the "Rolling notebook summary" mode in the mode table.
- [ ] Evaluate whether summary quality is sufficient:
  - [ ] For notebooks with 50+ entries, does count + 2 excerpts convey enough?
  - [ ] If enhancement needed, add under a flag (do not change default behavior).

## F) Safety and firewall invariants

- [ ] Verify consolidation reads stay under storage firewall constraints:
  - [ ] `consolidate_notebook.py` reads only from `ecosystems/<id>/agents/<agent-id>/notebook.jsonl`.
  - [ ] No path traversal outside ecosystem boundary.
- [ ] Verify no new write paths to evaluation ledger are introduced.
- [ ] Verify consolidation vector-store writes (if `--embed` used) go only to `.vectordb/` directory.
- [ ] Verify notebook append-only invariant: consolidation never modifies or truncates `notebook.jsonl`.
- [ ] Verify memory caps cannot be set to values that bypass budget constraints:
  - [ ] `recent_events_cap` and `recent_notebook_cap` enforce strict truncation.
  - [ ] `_truncate_to_cap` marker fits within budget (existing logic lines 19-26).

## G) Test implementation

### G1) Already covered by E1 tests (verify still passing)

- [ ] `test_wave_e1_memory_exposure.py` — cap enforcement at boundary values.
- [ ] `test_wave2_wave3_controls.py::test_state_builder_respects_memory_caps` — basic cap test.
- [ ] `test_wave_e1_memory_exposure.py` — provenance fields for peer/forum context.
- [ ] `test_wave_e1_memory_exposure.py` — graceful fallback with empty/missing data.

### G2) New tests needed for Wave 2

- [ ] **Rolling summary unit tests:**
  - [ ] `_summarize_notebook_prefix([])` returns `None`.
  - [ ] `_summarize_notebook_prefix(["a"])` returns a non-None summary.
  - [ ] `_summarize_notebook_prefix(["a"]*50)` produces bounded output.
  - [ ] Excerpt truncation at 120 chars works correctly.
  - [ ] Summary is deterministic (same input → same output).
- [ ] **Consolidation logic tests:**
  - [ ] `group_into_ltm_chunks` with fewer entries than `recent_cap` returns empty list.
  - [ ] `group_into_ltm_chunks` correctly splits older entries into chunk-sized groups.
  - [ ] `group_into_ltm_chunks` deduplicates within chunks.
  - [ ] Chunk metadata includes correct `time_range_start`/`time_range_end` and `decision_ids`.
  - [ ] `content_hash` is deterministic for same input.
- [ ] **Integration: consolidation preserves traceability:**
  - [ ] Each chunk references the source event IDs from original notebook entries.
  - [ ] Consolidation does not modify the source file.
- [ ] **Config wiring tests:**
  - [ ] `notebook_consolidation_interval=0` means consolidation is off (default behavior preserved).
  - [ ] Invalid consolidation interval (negative) raises `ValueError`.
- [ ] **Regression: defaults unchanged:**
  - [ ] `StateBuilder` with default caps produces same behavior as pre-Wave-2.
  - [ ] `recent_notebook_summary` is `None` when there are no older entries (≤ cap entries total).

## H) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Verify no schema changes needed (consolidation uses existing event types):
  - [ ] `agent.notebook.appended` payload unchanged.
  - [ ] No new event types added (consolidation is a read/analysis tool, not a ledger writer).
- [ ] Run `python -m tools.consolidate_notebook --ecosystem alpha --agent-id <id>` to verify CLI works.
- [ ] Run `python -m tools.consolidate_notebook --ecosystem beta --agent-id <id>` to verify CLI works.

## I) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] memory stability: no chain verification regressions.
  - [ ] context-pressure resilience: prompt size under budget with caps active.
  - [ ] notebook consolidation ratio: entries consolidated vs total.
  - [ ] rolling summary token count: bounded and stable.
- [ ] Compare observed deltas against expected deltas:
  - [ ] Caps reduce prompt size proportionally to cap value.
  - [ ] Consolidation chunks cover all older entries without loss.
  - [ ] Summary provides useful context without exceeding budget.
- [ ] Mark decision outcome: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback steps before merge:
  - [ ] Memory caps revert to hard-coded defaults (20 events, 5 notebook) if config keys removed.
  - [ ] Consolidation hook disabled by setting interval to 0.
  - [ ] Rolling summary degrades gracefully (returns `None` if no older entries).
- [ ] Define trigger thresholds:
  - [ ] Chain verification fails → immediate rollback.
  - [ ] Consolidation produces non-attributed text → disable hook.
  - [ ] Rolling summary exceeds token budget → revert to simpler format.
  - [ ] Memory caps cause prompt assembly failures → revert to defaults.
- [ ] Validate rollback can disable all Wave 2 features via config:
  - [ ] `notebook_consolidation_interval: 0` disables consolidation.
  - [ ] Removing cap keys falls back to defaults.
  - [ ] Summary logic already degrades to `None` safely.
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory gates pass (section H).
- [ ] No default behavior changes when Wave 2 config keys are absent.
- [ ] Memory caps are explicitly configurable and well-tested (verified from E1).
- [ ] STM/LTM boundary documented, accurate, and discoverable.
- [ ] Consolidation flow exists, is importable as library, and test-covered.
- [ ] Rolling summary hook verified, documented, and test-covered.
- [ ] Wave scorecard complete with acceptance/rollback evidence.
- [ ] `memory-architecture.md` reflects implemented reality.
