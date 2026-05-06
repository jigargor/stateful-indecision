# Wave 3 Ready-to-Execute Checklist

Scope label: `[safety-critical]`  
Wave: `3 — Safety and Governance`  
Status: Execution checklist (implementation-facing)

> **Escalation note.** Wave 3 changes decision admissibility and enforcement
> behavior — the highest safety-risk wave. Errors here can silently alter
> agent policy semantics and safety posture. Every item below carries an
> explicit "no silent fallback" gate.

## Spec and resource links

- Canonical source for strategy and resource links:
  - [`_plans/strategy/strategy-index.md`](/home/ubuntu/stateful-indecision/_plans/strategy/strategy-index.md)
- Wave-specific spec anchor:
  - [`_plans/waves/wave-3-safety-and-governance.md`](/home/ubuntu/stateful-indecision/_plans/waves/wave-3-safety-and-governance.md)

---

## A) Scope lock and success criteria

- [ ] Confirm Wave 3 scope is limited to safety and governance controls:
  - [ ] hard action masks (pre-sampling)
  - [ ] tool allowlist configuration and enforcement
  - [ ] deterministic verifier hooks at step and terminal boundaries
  - [ ] kill-switch pass/warn/fail outcomes
- [ ] Confirm Wave 3 non-goals:
  - [ ] no changes to action vocabulary structure or category definitions
  - [ ] no changes to memory/context exposure (Wave 2/E1 scope)
  - [ ] no new LLM-facing prompt changes beyond safety annotations
  - [ ] no changes to ledger schema structure (only new event types)
  - [ ] no changes to S3 sync, ETL, or observability tooling
- [ ] Record baseline thresholds for this wave:
  - [ ] safety fail budget (max acceptable fail events per run)
  - [ ] false-positive mask rate (legal actions incorrectly blocked)
  - [ ] false-negative allowlist rate (disallowed tools incorrectly permitted)
  - [ ] expected action-distribution drift from mask introduction

---

## B) Hard action masks — `mask-worker`

### B.1) Current state audit (read-first)

- [ ] Audit `agent/policy.py`:
  - [ ] `Policy.__init__` accepts `blocked_leaves: set[str] | None`, defaults to empty set.
  - [ ] `_allowed_leaves()` filters via `self.blocked_leaves` membership.
  - [ ] `propose()` excludes top-level categories when all child leaves are masked.
  - [ ] `propose()` raises `ValueError` when all leaves are masked (no legal action).
- [ ] Audit `agent/runner.py` lines 501–504:
  - [ ] `blocked_leaf_actions` loaded from `run_config` as `set[str]`.
  - [ ] No constitution-driven masks are wired yet.
- [ ] Audit `agent/decision.py`:
  - [ ] `_sample_with_reason_bias()` operates on already-masked distributions from `policy.propose()`.
  - [ ] Confirm masking happens before both standard and reason-biased sampling paths.

### B.2) Hardening tasks

- [ ] Validate `blocked_leaf_actions` entries against the loaded `ActionVocabulary`:
  - [ ] Reject unknown leaf names with an explicit `ValueError`.
  - [ ] **No silent fallback**: do not silently ignore invalid leaf names.
- [ ] Make `Policy.blocked_leaves` immutable after init (`frozenset`).
- [ ] Add optional constitution-driven masks:
  - [ ] Define mask extraction from constitution frontmatter or body markers.
  - [ ] Merge config-driven and constitution-driven masks (union).
  - [ ] Log merged mask set to public ledger as `agent.policy.masks_applied` event.
- [ ] Emit a `agent.policy.masks_applied` event before first sampling:
  - [ ] Include `blocked_leaves`, `source` (config / constitution / merged), `vocab_version`.
  - [ ] **No silent fallback**: if mask application fails, raise — do not proceed with unmasked policy.
- [ ] Verify the `ValueError("all action leaves are masked")` path:
  - [ ] Confirm it propagates to runner and triggers a clean shutdown (not a silent empty run).
  - [ ] Add a test for this edge case.

### B.3) No-silent-fallback gates for masks

- [ ] `blocked_leaves=None` must resolve to empty set (no masking), not silently permissive.
- [ ] Invalid leaf name in `blocked_leaf_actions` must raise, not skip.
- [ ] Mask application must be logged; absence of mask event at run start is a verifier-detectable gap.

---

## C) Tool allowlist — `allowlist-worker`

### C.1) Current state audit (read-first)

- [ ] Audit `agent/executor.py`:
  - [ ] `Executor.__init__` accepts `tool_allowlist: set[str] | None`.
  - [ ] `_tool_allowed()` returns `True` when allowlist is `None` (permissive), checks membership otherwise.
  - [ ] Every tool-using code path gates on `_tool_allowed()` (DISCOVER, READ, ANALYZE, ANNOTATE).
- [ ] Audit `agent/runner.py`:
  - [ ] `_parse_tool_allowlist(None)` returns `set()` — meaning "block all" when key is absent from config.
  - [ ] `_validate_run_config_modes` stores `sorted(result or [])` back to config.
  - [ ] Runner constructs `set(...)` from config value, passing empty set (not `None`) to Executor.
  - [ ] **Semantic gap**: when `run_config` exists but omits `tool_allowlist`, all tools are blocked.
    Verify this is intentional secure-by-default or fix to preserve `None` (allow-all) semantics.

### C.2) Hardening tasks

- [ ] Decide and document the default tool allowlist policy:
  - [ ] Option A: absent key = `None` (allow all) — explicit opt-in to restrictions.
  - [ ] Option B: absent key = `set()` (block all) — secure by default.
  - [ ] Whichever is chosen, **no silent fallback**: document the policy in `run_config` schema.
- [ ] Validate allowlist entries against a known tool registry:
  - [ ] Known tools: `web.search`, `web.fetch`, `scite.citations`, `zotero.catalog`.
  - [ ] Reject unknown tool names with explicit `ValueError`.
  - [ ] **No silent fallback**: do not silently ignore misspelled tool names.
- [ ] Emit a `agent.tool.allowlist_applied` event at run start:
  - [ ] Include `tool_allowlist` (list), `policy` (`allow_all` / `explicit_list`), `config_version`.
- [ ] Verify every tool call site in `Executor.execute()` has an `else` branch:
  - [ ] Each blocked tool must emit a `tool.blocked:<tool_name>` side effect (already present for some paths).
  - [ ] Audit all branches: DISCOVER, READ, ANALYZE, ANNOTATE — confirm no tool call can bypass `_tool_allowed()`.
- [ ] Ensure `_dependency_aware_tool_plan()` does not create paths that skip allowlist checks.

### C.3) No-silent-fallback gates for allowlist

- [ ] `_tool_allowed()` with empty set must block (not silently allow).
- [ ] `_tool_allowed()` with `None` must allow (not silently block).
- [ ] Misspelled tool names in config must raise at config load time, not silently pass through.
- [ ] Blocked tool calls must always produce `tool.blocked:*` side effects — never silently skip.

---

## D) Verifier hooks — `verifier-hook-worker`

### D.1) Current state audit (read-first)

- [ ] Audit `core/verifier.py`:
  - [ ] `verify_chain()` is batch/offline: reads a JSONL file, checks `prev_hash`/`record_hash` linkage.
  - [ ] No runtime (per-step) verification hooks exist.
  - [ ] `ChainError` dataclass and `VerificationResult` are the output types.
- [ ] Audit `agent/runner.py` decision loop (lines 674–718):
  - [ ] `monitor.evaluate()` fires after each step — but this is kill-switch, not chain verification.
  - [ ] No runtime chain integrity check between steps.
- [ ] Audit `core/writer.py`:
  - [ ] Confirm `ChainWriter.append()` computes `prev_hash`/`record_hash` at write time.
  - [ ] Identify whether a post-write verification callback exists (likely not).

### D.2) Implementation tasks

- [ ] Add a `verifier.step_checked` event at each step boundary:
  - [ ] After `action.executed` is written, verify the last N events in the public ledger.
  - [ ] Emit `verifier.step_checked` to evaluation ledger with `outcome: pass | fail`, `events_checked`, `step_number`.
  - [ ] **No silent fallback**: if verification fails at a step, emit `fail` and respect `verifier_mode` (warn/enforce).
- [ ] Add a `verifier.terminal_checked` event at run completion:
  - [ ] Verify the full public ledger chain after `run.completed`.
  - [ ] Emit `verifier.terminal_checked` to evaluation ledger with `outcome`, `total_events`, `errors`.
  - [ ] **No silent fallback**: terminal verification failure must be recorded even in `warn` mode.
- [ ] Wire verifier hooks into the runner decision loop:
  - [ ] Step hook: after each `step()` call, before `monitor.evaluate()`.
  - [ ] Terminal hook: after `_log_run_summary()`, before final `monitor.evaluate()`.
- [ ] Define deterministic behavior:
  - [ ] Verifier results must be reproducible given the same ledger state.
  - [ ] No randomness or wall-clock dependency in verification logic.

### D.3) No-silent-fallback gates for verifier

- [ ] Chain corruption detected at runtime must emit a `fail` event — never silently continue.
- [ ] Missing `verifier.step_checked` events are a detectable gap (step count vs. verifier event count).
- [ ] `verifier_mode=enforce` + chain corruption must halt the run (raise, not warn-and-continue).

---

## E) Kill-switch outcomes — `killswitch-worker`

### E.1) Current state audit (read-first)

- [ ] Audit `safety/kill_switch.py`:
  - [ ] `KillSwitchMonitor.__init__` accepts `mode` (`warn`/`enforce`) and `reward_mode` (`sparse`/`dense`).
  - [ ] `arm()` emits `safety.trigger.armed` to evaluation ledger.
  - [ ] `evaluate()` calls `_classify()`, emits `safety.trigger.evaluated` with `outcome`/`mode`/`reward_signal`.
  - [ ] `evaluate()` raises `RuntimeError` on `fail` + `enforce` mode.
  - [ ] `_classify()` handles `agent.step.completed` and `agent.run.completed`; returns `"warn"` for all others.
  - [ ] `_violates_rubric()` is keyword-based against rubric text.
  - [ ] `_reward_signal()` maps outcomes to floats per reward mode.
- [ ] Audit existing tests in `test_wave2_wave3_controls.py`:
  - [ ] `test_killswitch_emits_pass_warn_fail` covers pass/warn/fail outcomes and reward signals.

### E.2) Hardening tasks

- [ ] Harden `_classify()` default return:
  - [ ] **No silent fallback**: returning `"warn"` for all unrecognized event types is a silent fallback.
  - [ ] Define an explicit allowlist of recognized event types.
  - [ ] Unrecognized event types should return `"warn"` with an `unrecognized_event_type` flag in the payload.
- [ ] Harden `_violates_rubric()`:
  - [ ] Audit keyword list completeness against current event vocabulary.
  - [ ] Add test for each rubric check category (ecosystem scope, malformed writes, constitution bypass, alpha-corpus, emergency).
  - [ ] **No silent fallback**: missing rubric file should emit a `warn` event (not silently pass all events).
- [ ] Validate `mode` and `reward_mode` strictly:
  - [ ] Reject invalid mode values at init with `ValueError` (not silent default).
  - [ ] Confirm `_validate_run_config_modes()` in runner already validates these (it does — verify alignment).
- [ ] Add `enforce` mode integration test:
  - [ ] Test that `mode=enforce` + `outcome=fail` raises `RuntimeError`.
  - [ ] Test that the runner catches this and exits cleanly (exit code 1 or dedicated exit).
- [ ] Add reward signal boundary tests:
  - [ ] `sparse`: pass=1.0, warn=0.0, fail=-1.0.
  - [ ] `dense`: pass=1.0, warn=0.2, fail=-1.0.
  - [ ] Unknown outcome returns 0.0.

### E.3) No-silent-fallback gates for kill-switch

- [ ] `mode=enforce` must halt on `fail` — never downgrade to `warn` silently.
- [ ] Missing rubric file must not silently pass all events (emit armed event with `rubric_missing: true`).
- [ ] All `_classify()` code paths must be tested (no untested branches).
- [ ] Reward signals must match documented mode contracts exactly.

---

## F) Config contract definition

- [ ] Define/update run-config keys for Wave 3:
  - [ ] `blocked_leaf_actions: list[str]` — leaf names to mask pre-sampling.
  - [ ] `tool_allowlist: list[str] | null` — tools permitted; `null` = allow all.
  - [ ] `verifier_mode: "warn" | "enforce"` — already exists, verify semantics.
  - [ ] `reward_mode: "sparse" | "dense"` — already exists, verify semantics.
- [ ] Set deterministic defaults:
  - [ ] `blocked_leaf_actions`: `[]` (no masking by default).
  - [ ] `tool_allowlist`: `null` (allow all by default) or `[]` (block all) — document which.
  - [ ] `verifier_mode`: `"warn"` (default).
  - [ ] `reward_mode`: `"sparse"` (default).
- [ ] Define invalid-value handling policy:
  - [ ] All mode strings validated at config load (`_validate_run_config_modes`).
  - [ ] All list entries validated against known registries.
  - [ ] **No silent fallback**: invalid config must raise `ValueError`, not silently default.
- [ ] Export updated run-config schema via `tools.export_event_schemas` if payload models changed.

---

## G) Safety and firewall invariants

- [ ] Verify no new write paths introduced by Wave 3:
  - [ ] Verifier hooks write only to evaluation ledger (existing write path).
  - [ ] Mask/allowlist events write only to public ledger (existing write path).
  - [ ] No new filesystem writes outside ecosystem boundaries.
- [ ] Verify `safety/firewalls.py` `validate_agent_access` unchanged:
  - [ ] Ecosystem scope check intact.
  - [ ] Evaluation ledger write protection intact.
  - [ ] Cross-agent directory protection intact.
- [ ] Verify evaluation ledger remains unwritable by standard agent action paths:
  - [ ] Only `KillSwitchMonitor` and verifier hooks write to evaluation ledger.
  - [ ] No Executor code path writes to evaluation ledger.
- [ ] Verify `agent/runner.py` error handling covers new safety paths:
  - [ ] `RuntimeError` from kill-switch enforce mode caught and exits cleanly.
  - [ ] `ChainCorruptionError` from verifier hooks caught and exits with code 2.

---

## H) Test implementation

### H.1) Hard mask tests

- [ ] Test: blocked leaf is excluded from proposal distribution.
- [ ] Test: all leaves of a top-level category blocked → category excluded from `top_dist`.
- [ ] Test: all leaves blocked → `ValueError("all action leaves are masked")`.
- [ ] Test: invalid leaf name in `blocked_leaf_actions` → `ValueError` at config load.
- [ ] Test: `blocked_leaves=None` → no masking (same as empty set).
- [ ] Test: mask event emitted to public ledger at run start.
- [ ] Test: reason-biased sampling respects masks (distribution contains only allowed actions).

### H.2) Tool allowlist tests

- [ ] Test: `tool_allowlist=None` → all tools allowed.
- [ ] Test: `tool_allowlist={"web.search"}` → only `web.search` allowed, others blocked.
- [ ] Test: `tool_allowlist=set()` → all tools blocked.
- [ ] Test: blocked tool produces `tool.blocked:<name>` side effect.
- [ ] Test: invalid tool name in config → `ValueError` at config load.
- [ ] Test: allowlist event emitted to public ledger at run start.
- [ ] Test: every tool call site in Executor respects allowlist (no bypass path).

### H.3) Verifier hook tests

- [ ] Test: step-boundary verification emits `verifier.step_checked` with `pass` for valid chain.
- [ ] Test: step-boundary verification emits `verifier.step_checked` with `fail` for corrupted chain.
- [ ] Test: terminal verification emits `verifier.terminal_checked` with `pass` / `fail`.
- [ ] Test: `verifier_mode=enforce` + `fail` halts the run.
- [ ] Test: `verifier_mode=warn` + `fail` continues (but records the failure).
- [ ] Test: verifier results are deterministic (same ledger → same result).

### H.4) Kill-switch outcome tests

- [ ] Test: pass/warn/fail outcomes with correct reward signals (existing test, extend).
- [ ] Test: `mode=enforce` + `fail` raises `RuntimeError`.
- [ ] Test: unrecognized event type produces `warn` with flag.
- [ ] Test: missing rubric file does not silently pass all events.
- [ ] Test: each `_violates_rubric` category triggers `fail` when matched.
- [ ] Test: `_violates_rubric` returns `False` when rubric is empty.

### H.5) Regression tests

- [ ] Test: default run (no Wave 3 config) has unchanged behavior.
- [ ] Test: `blocked_leaf_actions=[]` produces identical distribution to no-config run.
- [ ] Test: `tool_allowlist=null` produces identical execution to no-config run.
- [ ] Test: chain verification passes for alpha and beta ecosystems (existing gate).

---

## I) Validation gates (must pass)

- [ ] `uv run pytest -q`
- [ ] `python -m tools.verify_chains --ecosystem alpha`
- [ ] `python -m tools.verify_chains --ecosystem beta`
- [ ] `python -m tools.check_run_config_hashes --base-dir .`
- [ ] Regenerate schemas if payload models changed:
  - [ ] `python -m tools.export_event_schemas`
  - [ ] Review schema diff for intended-only changes.
- [ ] Manual audit: read each modified file and confirm no silent fallback paths exist.

---

## J) Wave scorecard evidence capture

- [ ] Record baseline and post-change:
  - [ ] safety outcomes (`pass`/`warn`/`fail` counts per run)
  - [ ] mask effectiveness (blocked actions never sampled)
  - [ ] allowlist effectiveness (blocked tools never called)
  - [ ] verifier coverage (step_checked count = decision count)
  - [ ] action distribution with and without masks
- [ ] Compare observed deltas against expected deltas.
- [ ] Assign handoff role seed for Wave 4:
  - [ ] Candidate roles: `safety-warden`, `determinism-keeper`, `policy-guardian`.
  - [ ] Record selected role in scorecard.
- [ ] Mark decision outcome: `accept | reject | extend`.

---

## K) Rollback readiness

- [ ] Pre-write rollback steps before merge:
  - [ ] Masks: set `blocked_leaf_actions: []` to disable.
  - [ ] Allowlist: set `tool_allowlist: null` to restore allow-all.
  - [ ] Verifier hooks: set `verifier_mode: "warn"` (already default).
  - [ ] Kill-switch: mode already defaults to `"warn"`.
- [ ] Define trigger thresholds:
  - [ ] Safety: any unexpected `fail` outcomes not caused by intentional masks.
  - [ ] False positive: legal actions blocked by mask misconfiguration.
  - [ ] Chain: verifier detects corruption introduced by Wave 3 changes.
  - [ ] Regression: default-config behavior differs from pre-Wave-3.
- [ ] Validate rollback can disable all Wave 3 features via config alone.
- [ ] Maintain event schema compatibility (new event types are additive).
- [ ] Archive rollback evidence and rationale.

---

## L) Exit criteria

- [ ] All mandatory validation gates pass (section I).
- [ ] No default behavior changes when Wave 3 features are unconfigured.
- [ ] Every safety control is auditable via ledger events (masks, allowlist, verifier, kill-switch).
- [ ] Zero silent-fallback paths in mask, allowlist, verifier, or kill-switch code.
- [ ] Wave scorecard complete with acceptance/rollback evidence.
- [ ] Handoff role recorded for Wave 4.
