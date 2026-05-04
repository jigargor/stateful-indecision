# Run Log Template

Copy this file to `_plans/runs/run_<N>_<agent_id>.md` before each episode.
Fill every field before running. Fill the rest immediately after.

---

## Episode Metadata

| Field | Value |
|---|---|
| run_number | |
| agent_id | |
| ecosystem | alpha |
| model | |
| max_decisions | |
| seed | |
| wall_start | |
| wall_end | |
| llm_mode | mock / live |
| scite_live | yes / no |
| zotero_live | yes / no |

---

## Pre-Run

**Hypothesis** (one sentence — what you expect to see or learn):

**What changed from last run** (knobs touched — one change per run ideally):

- [ ] constitution seed text
- [ ] executor prompt templates
- [ ] field list
- [ ] action vocabulary / weights
- [ ] max_decisions
- [ ] seed
- [ ] model
- [ ] corpus / scite query scope
- [ ] other: ___

---

## Run Output

### Chain Verification

```
python tools/verify_chains.py --ecosystem alpha
```

- public.jsonl: PASS / FAIL
- commons.jsonl: PASS / FAIL
- evaluation.jsonl: PASS / FAIL
- notebook.jsonl: PASS / FAIL

### Action Distribution Observed

From `run.completed` payload — fill after run:

| top_action | sub_action | count |
|---|---|---|
| | | |

Notable deviations from expected uniform (~1-2 per category per 10 decisions):

### Web Source Policy

From `web.search.results.received` and `web.fetch.received` events:

- alpha_corpus hits:
- scite hits:
- zotero_cache hits:
- fallback triggered: yes / no

### Constitution

- revision_count:
- revisions interpretable: yes / no / mixed
- amendment text (paraphrase):

Duplicate amendment bug present: yes / no
*(The mock LLM tends to repeat the same SELF_REFLECT output, producing identical amendments. Check constitution.md for exact-duplicate paragraphs.)*

### Notebook Entries (count and summary)

| # | action | key sentence |
|---|---|---|
| 1 | | |

---

## Post-Run Analysis

### Candidate Research Avenues Surfaced

List every plausible new direction or question that emerged, even if the LLM was in mock mode:

1.
2.
3.

### Interesting Moments in the Trace

Reference event_ids for anything worth coming back to:

- event_id: — why it matters:

### Did the Run Meet the Episode Gate?

- [ ] Chain verification passed
- [ ] Can name 2+ candidate research avenues from notebook/trace
- [ ] Can explain *why* those avenues emerged from the action trace
- [ ] Constitution changes (if any) are interpretable

**Gate met: yes / no**

---

## Notes and Flags

Things to fix before next run:

-

Things to watch in next run:

-

---

## Episode 1 (example — agent-001, 2026-05-03, mock LLM, seed 42)

| Field | Value |
|---|---|
| run_number | 1 |
| agent_id | agent-001 |
| ecosystem | alpha |
| model | mock-fallback-claude-sonnet-4-6-20250514 |
| max_decisions | 10 |
| seed | 42 |
| wall_start | 2026-05-03T23:05:13Z |
| wall_end | 2026-05-03T23:05:14Z |
| llm_mode | mock |
| scite_live | no |
| zotero_live | no |

**Hypothesis:** Mock LLM produces structurally valid run with field choice, decisions, and at least one constitution revision.

**What changed:** First run — baseline.

**Gate met: yes**

### Action Distribution (10 decisions)

| top_action | sub_action | count |
|---|---|---|
| RESEARCH | ANALYZE | 1 |
| RIFF | ADMIRE | 1 |
| INDULGE | VENT | 1 |
| PONDER | SELF_REFLECT | 2 |
| SERVE | COLLABORATE | 1 |
| PRACTICE | EXPERIMENT | 1 |
| PONDER | DEEP_PATTERN_RECOGNITION | 1 |
| INDULGE | HOBBY | 1 |
| PONDER | THINK_DEEPLY | 1 |

PONDER ran 4/10 decisions (expected ~1.7). Uniform sampling variance on 10 decisions — not meaningful.

### Constitution

revision_count: 2. Both revisions are identical text — duplicate caused by mock LLM returning the same output for both SELF_REFLECT calls. The amendment text itself is coherent and worth keeping: *"after every broad survey phase, I will select one promising direction and pursue it with sustained attention before broadening again."*

**Fix required:** Deduplicate the constitution amendment. Either strip duplicate paragraphs from `constitution.md` manually before the next run, or add idempotency to `append_revision()` so identical text is not appended twice.

### Candidate Research Avenues Surfaced

1. **Epistemic networks as measurable graph structures** — bridging nodes as bottlenecks for novel idea propagation; power-law distributions in information cascades (COLLABORATE output)
2. **Endogenous preference change in ABMs** — most agent-based models fix utility functions; allowing self-revision would better capture epistemic communities (EXPERIMENT output)
3. **Keystone species model of epistemic authority** — structured analogy from ecological food webs to trust networks; keystone concept maps onto epistemic authorities (HOBBY output)
4. **Standards of evidence in decentralized networks** — recurring question: how do decentralized agents form shared evidentiary standards? (DEEP_PATTERN_RECOGNITION, THINK_DEEPLY)
5. **Boundary work as the productive zone** — "the interesting work is at the boundaries where epistemic norms from one domain collide with another" (THINK_DEEPLY)

### Notes and Flags

Fix before next run:
- Deduplicate constitution (lines 15-17 of `constitution.md` are identical)
- Scite corpus returning 0 results for "cultural_evolution" — either add placeholder corpus docs with that term, or query more broadly

Watch in next run:
- Does HOBBY produce cross-domain analogies consistently, or was ep1 noise?
- What does VENT produce with a real LLM vs mock?
