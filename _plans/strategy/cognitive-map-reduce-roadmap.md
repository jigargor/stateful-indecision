# Cognitive Map-Reduce Roadmap

This roadmap defines staged orchestration growth from current single-process behavior toward potential multi-team federation.

## Scope label

- Stage A: `[docs-only now]`
- Stage B: `[flagged runtime later]`
- Stage C: `[v2+]`

## Decision premise

Do not assume more teams are always better. Start from current single-team mode and escalate only with evidence.

## Stage A: Simulated map-reduce (`[docs-only now]`)

Current v1-compatible model:

- one runtime process,
- role-conditioned behavior through prompt pack (`research_lead`, `assistant_researcher`, `checker`),
- append-only forum/public communication events.

### Use when

- domain scope is narrow,
- web search + citation tooling is enough,
- checker quality remains high without external handoff overhead.

### Success criteria

- novelty and artifact quality increasing,
- contradiction backlog controlled,
- token/latency within budget.

## Stage B: Offline multi-run map-reduce (`[flagged runtime later]`)

Model:

- separate runs per role/team,
- shared ecosystem ledger surface for communication,
- no in-process parallel scheduler.

### Protocol elements

- handoff event schema (task, refs, expected output, deadline),
- cadence policy (cycle interval + termination conditions),
- conflict resolution (checker arbitration, lead tie-break),
- escalation rules (when a cross-team review is required).

### Best-fit scenarios

- sparse domains where one team’s search frontier stagnates,
- high uncertainty requiring independent checking perspectives.

## Stage C: Live multi-agent federation (`[v2+]`)

Model:

- scheduler-level supervision of concurrent specialized agents/teams.

### Entry conditions

- Stage B proves repeatable gains without safety regressions,
- communication protocol stability demonstrated,
- resource budget supports concurrent execution.

### Deferred

- scheduler internals,
- concurrency semantics,
- fault-tolerant distributed orchestration.

## Single team vs multi-team decision rubric

Choose single team if:

- novelty remains above threshold,
- checker passes remain stable,
- backlog is manageable,
- orchestration overhead outweighs gains.

Choose extra team(s) if:

- novelty plateaus for at least two accepted waves,
- unresolved contradiction rate exceeds threshold,
- lead backlog persists despite scorecard-constrained wave tuning.

## External pattern references

- AutoGen:
  - round-robin for deterministic turn-taking,
  - selector-group for context-aware speaker routing.
- LangGraph supervisor:
  - explicit supervisor-controlled delegation,
  - configurable history modes,
  - memory/checkpointer support.
- Hugging Face smolagents:
  - manager + specialist hierarchy pattern.
- CAMEL:
  - role-playing collaboration and common multi-agent failure patterns.

## Cross-team communication contract (docs-level)

Required fields:

- `team_id`
- `role`
- `task_id`
- `input_refs`
- `claim_set`
- `checker_verdict`
- `confidence`
- `next_action`

Non-negotiables:

- every claim linked to evidence refs,
- checker verdict required before promotion,
- unresolved conflicts explicitly tracked (no silent merge).

## Acceptance and rollback summary

- **Acceptance gate:** stage transition requires measurable rubric evidence, not narrative preference.
- **Rollback gate:** unresolved conflict growth or safety regressions return operation to prior stage.
