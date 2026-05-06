# Wave 0 Ready-to-Execute Checklist

Scope label: `[foundation baseline]`  
Wave: `0 — Artiforge Foundation and Stabilization`  
Status: Execution checklist (implementation-facing)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec:
  - [`_plans/waves/wave-0-artiforge-foundation-and-stabilization.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-0-artiforge-foundation-and-stabilization.md)
- Project architecture and standards:
  - [`AGENTS.md`](/home/ubuntu/stateful-indecision/AGENTS.md)

## A) Scope lock and success criteria

- [x] Confirm Wave 0 is the required first wave; no upstream dependencies.
- [x] Confirm Wave 0 non-goals:
  - [x] No new runtime features (memory, safety, formalism are all later waves).
  - [x] No ledger schema changes.
  - [x] No new config keys or toggles.
  - [x] No Artiforge integration (deliberate skip; see section D).
- [x] Record success criteria:
  - [x] PONDER vocabulary invariant resolved (fixed or formally reclassified with test coverage).
  - [x] README pre-release wording aligns with `pyproject.toml` version `1.0.0`.
  - [x] `AGENTS.md` is current and accurate for architecture, operational commands, and coding standards.
  - [x] All baseline validation gates pass (section H).
  - [x] Wave scorecard completed with go/no-go for Wave 1 handoff.

## B) PONDER vocabulary invariant resolution

The `seeds/action_vocabulary.json` PONDER category has three leaves (`SELF_REFLECT`, `THINK_DEEPLY`, `DEEP_PATTERN_RECOGNITION`) whose home-category weights (0.45, 0.40, 0.40) are the lowest primary affinity of any category. This makes PONDER the most diffuse category in the vocabulary.

The existing test `test_primary_category_matches_listing` in `tests/test_action_vocabulary.py` asserts that each leaf's highest-weighted category matches the category it is listed under. This test currently passes because PONDER is still the single highest weight for all three leaves.

**Resolution path — choose one:**

### Option 1: Fix (raise PONDER weights)
- N/A — Option 2 selected.

### Option 2: Reclassify (formal acknowledgment with test coverage) ✓ SELECTED
- [x] Add a new test `test_ponder_leaf_weight_bounds` to `tests/test_action_vocabulary.py` that:
  - [x] Asserts each PONDER leaf has PONDER as its primary (highest-weight) category.
  - [x] Asserts the PONDER weight is ≥ 0.35 (documenting the current design floor).
  - [x] Includes a docstring explaining the diffuse-weight design rationale.
- [x] Leave weights unchanged.

### Shared post-resolution steps
- [x] Run `uv run pytest tests/test_action_vocabulary.py -v` and confirm all vocabulary tests pass. (6 passed)
- [x] `seeds/action_vocabulary.json` was NOT modified; no hash regeneration needed. `check_run_config_hashes` passes.

## C) README / pyproject.toml alignment

### Current state
- `pyproject.toml` declares `version = "1.0.0"` and `Development Status :: 5 - Production/Stable`.
- `README.md` line 1 says "v1.0.0 package baseline" and line 9 mentions "v1.0.0 package baseline is active on `main`".
- README also states "hardened toward a stable v1.0.0 release" which could be read as pre-release language.

### Steps
- [x] Verify `pyproject.toml` `version` field is exactly `"1.0.0"`. ✓
- [x] Verify README does **not** contain phrases like "pre-release", "upcoming release", "not yet stable", or "being hardened toward" that contradict a `1.0.0` release status. ✓ Removed "The system is being hardened toward a stable v1.0.0 release."
- [x] If the README says "being hardened toward a stable v1.0.0 release", update it to say "v1.0.0 release" (remove hedging language) **or** downgrade `pyproject.toml` to a pre-release version if the project is genuinely not stable. Prefer aligning README to pyproject. ✓ Sentence removed entirely (prior sentence already establishes v1.0.0 status).
- [x] Verify the README Quickstart install command is consistent with the package (`pip install -e .[dev]` matches `pyproject.toml` extras). ✓ Matches.
- [x] Verify README `Auton concept mapping table` exists in `README.md` (required by wave spec acceptance criteria). ✓ Present at "## Auton Concept Mapping".
- [x] Verify `_plans/auton_and_agent_layers.md` exists and pins the paper version to v1. ✓ "Pinned paper version for this plan: v1".

## D) Artiforge skip acknowledgment

**Decision: Artiforge is deliberately skipped for Wave 0.** All three required Artiforge calls (`codebase-scanner`, `artiforge-make-project-docs`, `artiforge-make-development-task-plan`) returned empty error objects in prior sessions. Manual fallback was applied.

- [x] Confirm the wave spec runtime log (section "Artiforge Runtime Log") already documents the failures. ✓
- [x] Do **not** invoke any Artiforge tools. ✓
- [x] Record in the scorecard (section I) that Artiforge was skipped with manual fallback, and note residual risk as low (manual outputs were produced). ✓
- [x] If AGENTS.md or README updates were previously generated by Artiforge fallback, verify their accuracy manually. ✓ Verified.

## E) AGENTS.md verification

### Required coverage
- [x] **Project Purpose** — describes ledger-first agent research runtime and v1 objective. ✓
- [x] **Core Architecture** — lists blueprint inputs, runtime engine, persistence/integrity, safety, and observability layers with correct file paths. ✓
- [x] **Key Data Surfaces** — lists all JSONL ledger types (`public`, `evaluation`, `commons`, `roundtable`, `townhall`, `notebook`, `constitution`). ✓
- [x] **Runtime Invariants** — covers append-only hash linking, canonical JSON, path firewall, eval-ledger write protection. ✓
- [x] **Operational Commands** — includes:
  - [x] `uv run pytest -q` ✓
  - [x] `python -m tools.verify_chains --ecosystem alpha` ✓
  - [x] `python -m tools.verify_chains --ecosystem beta` ✓
  - [x] `python -m tools.export_to_sqlite --db dashboard.db --base-dir .` ✓
  - [x] `python -m tools.check_run_config_hashes --base-dir .` ✓ (added in this wave)
  - [x] batch ETL and notebook novelty commands ✓
- [x] **Coding Standards** — covers typed payloads, backward-compatible defaults, focused tests, no silent fallback. ✓
- [x] **Current Wave Priorities** — starts with "Wave 0 stabilization and baseline pass gates." ✓
- [x] **Out of Scope** — lists unbounded complexity, experimental formalism, schema-breaking changes. ✓

### Fix actions
- [x] Add `check_run_config_hashes` to operational commands if absent. ✓ Added both `check` and `sync` commands.
- [x] Correct any stale file paths or command syntax. ✓ No stale paths found.
- [x] Do not introduce new sections unless coverage gaps are found above. ✓ No new sections added.

## F) Test requirements

### Existing test verification
- [x] Run `uv run pytest tests/test_action_vocabulary.py -v` — all must pass. ✓ 6 passed.
- [x] Run `uv run pytest -q` — full suite must pass. ✓ 123 passed, 1 skipped.

### New or modified tests (only if PONDER option 1 or 2 chosen above)
- N/A If Option 1 (fix weights): existing tests should cover the change. Run full suite.
- [x] If Option 2 (reclassify): add `test_ponder_leaf_weight_bounds` as specified in section B. ✓
- [x] Any new test must exercise real vocabulary loading (`ActionVocabulary.load`), not duplicate inline logic. ✓ Uses `ActionVocabulary.load(Path(...))`.
- [x] Tests must not hardcode weight values beyond documented bounds — test invariants, not snapshots. ✓ Only checks primary category and ≥0.35 floor.

### Lessons from E1 to apply
- [x] Boolean config values must be validated strictly (not truthy strings) — verify no Wave 0 changes introduce truthy-string comparisons. ✓ No boolean config changes made.
- [x] Cap enforcement must be strict (truncation within budget) — N/A for Wave 0 but verify no regressions. ✓ No cap changes.
- [x] Hash files must be synced after modifying tracked files — run `check_run_config_hashes` after any seed file changes. ✓ No seed files modified; hashes pass.

## G) Safety and firewall invariants

Wave 0 introduces no new code paths, but verify the baseline:

- [x] No new write paths introduced. ✓ Only doc/test changes.
- [x] No new read paths outside storage firewall. ✓
- [x] Evaluation ledger write protections unchanged. ✓
- [x] `seeds/action_vocabulary.json` was NOT modified. ✓

## H) Validation gates (must all pass)

- [x] `uv run pytest -q` ✓ 123 passed, 1 skipped in 1.07s
- [x] `python -m tools.verify_chains --ecosystem alpha` ✓ No .jsonl files found (expected)
- [x] `python -m tools.verify_chains --ecosystem beta` ✓ 8 chains OK
- [x] `python -m tools.check_run_config_hashes --base-dir .` ✓ 4 file hashes validated
- [x] `seeds/action_vocabulary.json` was NOT modified — hash regeneration not needed.
- [x] Schema models were NOT touched — schema export not needed.

## I) Wave scorecard evidence capture

```
| Criterion                      | Status        | Evidence / Notes                                                            |
|-------------------------------|---------------|-----------------------------------------------------------------------------|
| PONDER invariant resolved     | [x] pass      | Option 2 (reclassify): test_ponder_leaf_weight_bounds added; weights unchanged |
| README/pyproject aligned      | [x] pass      | Removed hedging "being hardened toward"; pyproject.toml version=1.0.0       |
| AGENTS.md verified            | [x] pass      | Added check_run_config_hashes + sync commands to operational commands       |
| Artiforge                     | [x] skipped   | Manual fallback applied; see D. Residual risk: low                          |
| pytest -q                     | [x] pass      | 123 passed, 1 skipped (integration marker) in 1.07s                        |
| verify_chains alpha           | [x] pass      | No .jsonl files found (expected — no alpha ledgers committed)               |
| verify_chains beta            | [x] pass      | 8 chains OK: public(3160), evaluation(705), commons(129), roundtable(124), townhall(9), 3 notebooks |
| check_run_config_hashes       | [x] pass      | 4 file hashes validated                                                     |
| Residual risk                 | [x] low       | Artiforge tooling unavailable; manual outputs verified. No runtime changes. |
| Go/no-go for Wave 1           | [x] go        | All gates pass; foundation stable for contract hardening                    |
```

### Inter-wave role handoff (0 → 1)
- [x] Select a handoff role seed from: `strict-auditor`, `schema-architect`, `release-steward`.
- [x] Record selected role in scorecard.
- [x] Pass role context to Wave 1 kickoff.

**Selected role: `schema-architect`** — Wave 1 focuses on contracts and blueprint hardening; a schema-first perspective aligns with that scope.

## J) Rollback readiness

### Pre-merge rollback plan
- [x] If vocabulary weights were changed: N/A — weights were NOT changed.
- [x] If README wording was changed: revert README only if version/policy changes upstream. ✓ Noted.
- [x] If AGENTS.md was modified: revert is always safe (documentation-only). ✓ Noted.
- [x] If new tests were added: removing tests requires justification in scorecard. ✓ `test_ponder_leaf_weight_bounds` added; removal would require justification.

### Trigger thresholds
- [x] Any validation gate in section H fails after changes → rollback. ✓ All gates pass.
- [x] `test_primary_category_matches_listing` fails → rollback vocabulary change immediately. ✓ Passes; no vocabulary change made.
- [x] Downstream wave tests regress → investigate before rollback (may be pre-existing). ✓ No regressions.

### Evidence archival
- [x] Keep log of all changes made, even if rolled back. ✓ This checklist serves as the log.
- [x] Record Artiforge failure logs for audit trail (already in wave spec). ✓

## K) Exit criteria

- [x] All mandatory validation gates (section H) pass. ✓
- [x] PONDER invariant is resolved via fix or formal reclassification with test coverage. ✓ Option 2 with `test_ponder_leaf_weight_bounds`.
- [x] README and `pyproject.toml` version language are consistent. ✓ Hedging language removed.
- [x] `AGENTS.md` covers all required sections listed in E. ✓ `check_run_config_hashes` added.
- [x] Artiforge skip is documented with manual fallback acknowledgment. ✓ Documented in wave spec runtime log.
- [x] Wave scorecard (section I) is complete with go/no-go decision. ✓ Go.
- [x] Handoff role seed assigned for Wave 1. ✓ `schema-architect`.
- [x] No default runtime behavior changed (Wave 0 is stabilization-only). ✓ Only test/doc changes.
