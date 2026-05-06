# Wave E4 Ready-to-Execute Checklist

Scope label: `[flagged runtime later]`  
Wave: `E4 — Promotion defaults and deprecation`  
Status: Execution checklist (implementation-facing)  
Pipeline position: **FINAL WAVE** (all prior waves complete)

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/strategy/implementation-wave-plan.md`](/home/ubuntu/stateful-indecision/_plans/strategy/implementation-wave-plan.md) (lines 98–120)
- Prior wave checklists (all complete):
  - `wave-0-ready-checklist.md` through `wave-5-ready-checklist.md`
  - `wave-e1-ready-checklist.md` through `wave-e3-ready-checklist.md`

## Critical constraint

> "No default flips without acceptance and rollback gates passing."

Every default change in this wave MUST have:
1. An explicit before/after value documented.
2. A rollback instruction that restores the prior default.
3. Full regression + chain + hash checks passing after the change.
4. A rehearsed migration (not just documented).

---

## A) Scope lock and success criteria

- [ ] Confirm E4 scope is limited to: promotion of approved conventions to defaults, deprecation of legacy assumptions, and documentation updates.
- [ ] Confirm E4 non-goals:
  - [ ] no new runtime features or code paths
  - [ ] no in-place rewrite of historical ledger lines
  - [ ] no undocumented defaults
  - [ ] no irreversible migration without rehearsal evidence
  - [ ] no seed file modifications (Wave 0 lesson)
- [ ] Record baseline thresholds for this wave:
  - [ ] current test count (370 tests) and pass rate
  - [ ] safety fail budget (carry forward from prior wave scorecards)
  - [ ] chain verification status for all ecosystems
  - [ ] hash integrity check status for all run configs

## B) Default promotion inventory

Audit every opt-in feature from prior waves and decide: promote, keep opt-in, or deprecate.

### B.1) Run-config default changes

For each change below, document before/after values and rollback instruction.

- [ ] **`verifier_mode`**: Evaluate promotion from `"warn"` to `"strict"`.
  - Before: `"warn"` (all 4 configs)
  - Proposed: `"strict"` (Wave 3 validated hard verification)
  - Rollback: revert to `"warn"` in all configs
  - Gate: full regression must pass with `"strict"` before promotion
- [ ] **`enable_pi_reason_then_action`**: Evaluate promotion from `false` to `true`.
  - Before: `false` (all 4 configs)
  - Proposed: `true` (Wave 5 validated decision phases)
  - Rollback: revert to `false` in all configs
  - Gate: confirm latent event emission remains independently controllable
- [ ] **`emit_latent_reasoning_events`**: Evaluate promotion from `false` to `true`.
  - Before: `false` (all 4 configs)
  - Proposed: `true` (Wave 5 validated latent events)
  - Rollback: revert to `false` in all configs
  - Gate: confirm observability pipeline handles the additional events
- [ ] **`blocked_leaf_actions`**: Evaluate whether a baseline mask should be set.
  - Before: `[]` (all 4 configs)
  - Proposed: determine if Wave 3 testing identified any actions that should be masked by default
  - Rollback: revert to `[]`
  - Gate: action-distribution drift must remain within bounds
- [ ] **`prompt_progression`**: Evaluate adding explicit key (currently absent, defaults to `"off"` implicitly).
  - Before: key absent from all configs (implicit `"off"`)
  - Proposed: add explicit `"prompt_progression": "off"` to all configs (explicit is better than implicit)
  - Rollback: remove key (behavior unchanged)
  - Gate: no behavioral change expected; validation-only
- [ ] **Memory exposure toggles** (E1 features): Evaluate whether peer context, forum digest, or RAG retrieval should be enabled by default.
  - Before: opt-in / off by default
  - Proposed: decide per config based on E1 scorecard evidence
  - Rollback: set all E1 toggles back to off/disabled
  - Gate: token/latency budget must remain within ceiling
- [ ] **Handoff schema defaults** (E2 features): Evaluate whether map-reduce protocol conventions should be reflected in configs.
  - Before: opt-in
  - Proposed: decide based on E2 scorecard evidence
  - Rollback: remove E2-specific config keys
- [ ] **Ecosystem ID format** (E3): Confirm all configs use validated ID grammar.
  - Before: literal `"alpha"` / `"beta"` strings
  - Proposed: retain values but confirm they pass E3 validation grammar
  - Rollback: N/A (no value change, only validation path change)

### B.2) Per-config file review

Each `run_config*.json` must be individually reviewed and updated:

- [ ] `run_config.json` (alpha / sweng-lead): apply promotion decisions
- [ ] `run_config_beta_a1.json` (beta / beta-agent-1 / research_lead): apply promotion decisions
- [ ] `run_config_beta_a2.json` (beta / beta-agent-2 / assistant_researcher): apply promotion decisions
- [ ] `run_config_beta_a3.json` (beta / beta-agent-3 / checker): apply promotion decisions
- [ ] Bump `config_version` in each file to reflect E4 changes
- [ ] Update `knob_changelog` in each file to document E4 promotion changes
- [ ] Sync hashes after any tracked-file changes: `python -m tools.sync_run_config_hashes --base-dir .`

## C) Deprecation inventory

Identify legacy assumptions and behaviors that should be deprecated with transition windows.

- [ ] **Implicit `prompt_progression` default**: Deprecate reliance on absent key implying `"off"`. Require explicit key in all configs.
- [ ] **`verifier_mode: "warn"`**: If promoted to `"strict"`, mark `"warn"` as deprecated-but-supported with a transition window (e.g., 2 config versions).
- [ ] **Implicit memory cap defaults**: If any caps were previously inferred rather than explicit, deprecate the inference path.
- [ ] **Legacy ecosystem ID handling**: If E3 introduced validated grammar, deprecate any code paths that bypass validation for known literal IDs.
- [ ] **Undocumented config keys**: Audit for any config keys that exist in code but lack documentation; either document or deprecate.
- [ ] For each deprecation, define:
  - [ ] transition window (number of config versions or calendar period)
  - [ ] warning mechanism (log message, validation warning, or doc notice)
  - [ ] removal target version

## D) Documentation updates — AGENTS.md

- [ ] **Current Wave Priorities** section: Update from Wave 0 references to reflect completed pipeline status.
  - Before: references Wave 0 stabilization and contract hardening
  - After: reflect that all waves (0–5, E1–E4) are complete; state post-pipeline priorities
- [ ] **Operational Commands** section: Verify all commands are current and complete.
  - [ ] Confirm `verify_chains` supports generalized ecosystem IDs (E3)
  - [ ] Confirm `export_to_sqlite` and `batch_etl` commands reflect current interfaces
  - [ ] Add any new operational commands introduced in Waves 4/5/E1–E3
- [ ] **Coding Standards** section: Add any conventions that emerged from the wave pipeline.
  - [ ] Fixed-shape models, no `extra="allow"` for stable payloads (Wave 1 lesson)
  - [ ] Boolean config must be strictly validated (E1 lesson)
  - [ ] Cross-validation between related fields (E2 lesson)
  - [ ] Docstrings must match actual code flow (Wave 5 lesson)
- [ ] **Key Data Surfaces** section: Verify accuracy against current state.
  - [ ] Confirm all ledger paths reflect E3 generalized IDs
  - [ ] Confirm forum ledger documentation is complete
- [ ] **Out of Scope** section: Update to reflect post-pipeline state.
- [ ] **Runtime Invariants**: Verify all listed invariants still hold after all waves.

## E) Documentation updates — README.md

- [ ] **Status** section: Update to reflect post-pipeline maturity.
  - [ ] "What is working" list: add capabilities from Waves 1–5 and E1–E4
  - [ ] "What is not in v1 scope" list: review and update based on what was actually delivered
- [ ] **Quickstart** section: Verify commands still work with promoted defaults.
- [ ] **Repository Layout**: Update if any new directories or files were added across waves.
- [ ] **Auton Concept Mapping**: Verify mapping is current.
- [ ] **Memory Boundaries**: Verify caps and consolidation docs match promoted defaults.
- [ ] **Runtime Decision Phases**: Verify documentation matches Wave 5 implementation.
- [ ] **Privilege and Tool Controls**: Verify documentation matches Wave 3 hardened controls.
- [ ] **Reward and Evaluation Signals**: Verify against current implementation.
- [ ] **Versioning**: Consider version bump to reflect pipeline completion.
- [ ] Ensure no documentation overstates feature capabilities (Wave 4 lesson).

## F) Migration rehearsal

The spec requires rehearsal, not just documentation. Each default change must be applied and validated in sequence.

- [ ] **Pre-rehearsal snapshot**: Record current state of all validation gates.
- [ ] **Rehearsal step 1**: Apply each default promotion one at a time in an isolated branch.
  - [ ] After each change, run: `uv run pytest -q`
  - [ ] After each change, run: `python -m tools.verify_chains --ecosystem alpha`
  - [ ] After each change, run: `python -m tools.verify_chains --ecosystem beta`
  - [ ] After each change, run: `python -m tools.check_run_config_hashes --base-dir .`
  - [ ] Record pass/fail for each individual promotion
- [ ] **Rehearsal step 2**: Apply all promotions together.
  - [ ] Run full gate suite (same 4 commands)
  - [ ] Compare results against individual-change results
  - [ ] Flag any interaction effects between promotions
- [ ] **Rehearsal step 3**: Rollback dry-run.
  - [ ] Revert all promotions to prior defaults
  - [ ] Run full gate suite
  - [ ] Confirm clean rollback with no residual state changes
- [ ] **Rehearsal evidence**: Archive rehearsal logs and pass/fail records.

## G) Test implementation

- [ ] Add tests verifying promoted defaults are correctly loaded.
- [ ] Add tests verifying deprecated values emit appropriate warnings.
- [ ] Add tests verifying transition-window behavior (deprecated values still functional).
- [ ] Add regression tests confirming no behavioral change for configs that were already using the promoted values.
- [ ] Verify zero-cap edge cases still pass (Wave 2 lesson).
- [ ] Verify kill-switch event types match actual ledger events (Wave 3 lesson).
- [ ] Verify path resolution with validated ecosystem IDs (E3 lesson).

## H) Validation gates (must pass)

- [ ] `uv run pytest -q` — all tests pass (target: 417+ tests)
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] review schema diff for intended-only changes
- [ ] Verify no new linter errors in modified files.
- [ ] Verify documentation links are not broken.

## I) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] safety outcomes (`pass`/`warn`/`fail`) across all ecosystems
  - [ ] novelty proxy (notebook novelty)
  - [ ] token/latency budget
  - [ ] action distribution
- [ ] Compare observed deltas against expected deltas.
  - [ ] Expected: minimal delta (promotion should codify existing behavior, not change it)
  - [ ] Flag any unexpected drift as potential rollback trigger
- [ ] Mark decision outcome per promotion: `accept | reject | extend`.

## J) Rollback readiness

- [ ] Pre-write rollback steps for EVERY default change before merge.
- [ ] Define trigger thresholds:
  - [ ] operator confusion from ambiguous defaults (spec rollback trigger)
  - [ ] dashboard/export breakage (spec rollback trigger)
  - [ ] missed deprecation compatibility windows (spec rollback trigger)
  - [ ] safety outcome regression
  - [ ] chain verification failure
  - [ ] hash integrity check failure
- [ ] Validate rollback can restore ALL prior defaults via config-only changes (no code changes required).
- [ ] Confirm rollback does not require historical ledger rewrite (global non-goal).
- [ ] Archive rollback evidence and rationale.

## K) Exit criteria

- [ ] All mandatory gates pass (section H).
- [ ] Every default change has documented before/after, rollback instruction, and rehearsal evidence (section B + F).
- [ ] Every deprecation has a defined transition window and warning mechanism (section C).
- [ ] AGENTS.md reflects the completed pipeline state (section D).
- [ ] README.md reflects promoted capabilities and updated defaults (section E).
- [ ] Migration rehearsal completed and archived (section F).
- [ ] Wave scorecard complete with acceptance/rollback evidence (section I).
- [ ] Rollback procedure tested, not just written (section J).
- [ ] No undocumented defaults remain in any run config.
- [ ] No irreversible changes were made without rehearsal evidence.

---

## L) Final pipeline summary — all waves complete

This section documents the full pipeline accomplishment across all waves.

### Wave completion record

| Wave | Scope | Key deliverables |
|---|---|---|
| **Wave 0** | Stabilization and baseline | PONDER reclassification, baseline gates, initial test suite |
| **Wave 1** | Contracts and blueprint | 30+ Pydantic payload models, full schema export, strict validation |
| **Wave 2** | Memory window and consolidation | Memory caps validated (including zero-cap edge cases), consolidation hook, rolling summary |
| **Wave 3** | Safety and governance | Hard masks, tool allowlist, boundary verification, kill-switch hardening |
| **E1** | Memory exposure controls | Peer context, forum digest, RAG retrieval in prompts, strict caps and provenance |
| **E2** | Multi-run map-reduce protocol | Handoff schema, checker verdict, map-reduce protocol surfaces |
| **Wave 4** | Observability | Grafana metrics, trajectory export, Level 1 adaptation guide |
| **E3** | Ecosystem ID generalization | Validated ID grammar, reserved words, firewall hardening, alias compatibility |
| **Wave 5** | Formalism and integration | Decision phases, latent events verified, integration guide, diagrams |
| **E4** | Promotion and deprecation | Default promotion, deprecation windows, documentation refresh, migration rehearsal |

### Cumulative test baseline (actual E4 session results)

- **417 tests** pass (370 baseline + 47 new E4 tests), 2 skipped
- Chain verification passing for beta ecosystem (8 ledgers, 4,279 total events)
- Alpha ecosystem has no ledger files (expected — no alpha run in this environment)
- Hash integrity checks passing for all 4 run config files
- Schema export: 35 schema files generated successfully

### Cross-wave lessons applied

1. **Wave 0**: Seeds are locked inputs — never modify without explicit requirement.
2. **Wave 1**: Use fixed-shape Pydantic models; no `extra="allow"` for stable payloads.
3. **Wave 2**: Zero-cap edge cases are real failure modes — always test boundary values.
4. **Wave 3**: Kill-switch event types must exactly match actual ledger event strings.
5. **E1**: Boolean config fields must be strictly validated — no truthy/falsy shortcuts.
6. **E2**: Cross-validate related config fields to prevent inconsistent state.
7. **E3**: Path resolution bugs are high risk — always use validated IDs through the grammar.
8. **Wave 4**: Documentation must not overstate what the code actually does.
9. **Wave 5**: Docstrings must match actual code flow — audit after refactors.
10. **E4**: No default flips without acceptance AND rollback gates passing.

### Architecture maturity at pipeline completion

- **Blueprint layer**: Fully typed run configs with hash-tracked seed files, schema exports, and explicit knob changelogs.
- **Runtime engine**: Decision phases, policy sampling with masks, executor with tool allowlist, memory consolidation.
- **Persistence**: Append-only hash-chained ledgers with strict verification, generalized ecosystem IDs, firewall-enforced paths.
- **Safety**: Hard action masks, tool allowlist enforcement, kill-switch monitoring, evaluation ledger isolation.
- **Observability**: JSONL ledgers, SQLite export, Grafana dashboards, Parquet ETL, trajectory export, latent reasoning events.
- **Multi-agent surfaces**: Forum ledgers (commons, roundtable, townhall), peer context bridges, map-reduce handoff protocol.
- **Documentation**: AGENTS.md, README.md, operational playbooks, Level 1 adaptation guide, integration guide.

### E4 promotion decisions (actual)

| Config key | Before | After | Decision | Rollback |
|---|---|---|---|---|
| `prompt_progression` | absent (implicit `"off"`) | explicit `"off"` | Promoted to explicit | Remove key |
| `enable_peer_context` | absent | explicit `false` | Promoted to explicit | Remove key |
| `peer_context_cap` | absent | explicit `0` | Promoted to explicit | Remove key |
| `enable_forum_digest` | absent | explicit `false` | Promoted to explicit | Remove key |
| `forum_digest_cap` | absent | explicit `0` | Promoted to explicit | Remove key |
| `enable_rag_retrieval` | absent | explicit `false` | Promoted to explicit | Remove key |
| `memory_context_total_cap` | absent | explicit `0` | Promoted to explicit | Remove key |
| `notebook_consolidation_interval` | absent | explicit `0` | Promoted to explicit | Remove key |
| `verifier_mode` | `"warn"` | `"warn"` (unchanged) | Kept — pending operator acceptance | N/A |
| `enable_pi_reason_then_action` | `false` | `false` (unchanged) | Kept — experimental | N/A |
| `emit_latent_reasoning_events` | `false` | `false` (unchanged) | Kept — experimental | N/A |
| `blocked_leaf_actions` | `[]` | `[]` (unchanged) | Kept — no evidence for default masks | N/A |
| `config_version` | varies | bumped +1 per file | Version bump for E4 | Revert version |

### E4 deprecation markers (actual)

| Deprecated pattern | Location | Transition window | Removal target |
|---|---|---|---|
| Absent `prompt_progression` key implying `"off"` | `agent/runner.py` | 2 config versions | v2.0.0 |
| Implicit memory cap defaults (absent keys) | `agent/runner.py` | 2 config versions | v2.0.0 |
| `verifier_mode: "warn"` (supported but promotion pending) | `agent/runner.py` | Pending operator acceptance | v2.0.0 evaluation |

### Migration rehearsal evidence

- Rollback rehearsal: removed all E4-promoted keys from alpha config, validated safe defaults applied (prompt_progression=off, verifier_mode=warn, reward_mode=sparse, absent memory keys cause no errors)
- Full regression after promotion: 417 tests pass, 0 failures
- Chain integrity preserved: all beta ledgers verified post-change
- Hash integrity preserved: all 4 config files pass hash checks post-change

### Post-pipeline priorities

With all waves complete, the project transitions from pipeline execution to steady-state operation:
1. Monitor promoted defaults across live runs for unexpected drift.
2. Enforce deprecation transition windows per the schedule set in section C.
3. Collect scorecard evidence for potential v2 scope decisions.
4. Maintain the 417-test baseline as a regression floor.
