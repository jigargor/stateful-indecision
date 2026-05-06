# Strategy Index

Control surface for the Axis-aligned strategy package.

## Scope label

- `[docs-only now]` for the strategy package itself.

## Status table

| Doc | Purpose | Owner surface | Dependencies | Implementation wave | Acceptance gate | Rollback gate | Status |
|---|---|---|---|---|---|---|---|
| `baseline-gap-map.md` | Canonical baseline and Auton mapping matrix | Docs + architecture | `README.md`, `AGENTS.md`, `_plans/auton_and_agent_layers.md` | Strategy pass | Baseline matrix complete and consistent with code paths | Any contradiction with shipped controls requires doc correction before promotion | Drafted |
| `autogen-iteration-protocol.md` | Micro-wave protocol and scorecard standard | Runner/config + policy + docs | `tools/README-Level1-Adaptation.md`, wave docs | Strategy pass | Scorecard template includes safety/novelty/token/latency + rollback fields | Missing rollback fields blocks use in promotion decisions | Drafted |
| `training-protocol.md` | Three-level evolution gates (L1/L2/L3) | Adaptation/research governance | `tools/export_to_sqlite.py`, `tools/batch_etl.py` | Strategy pass | Explicit promotion/rejection criteria per level | Any auto-promotion path without human gate is rejected | Drafted |
| `memory-architecture.md` | Disambiguated STM/LTM modes and enablement rules | State builder + notebook + constitution + docs | `agent/state_builder.py`, `agent/notebook.py` | Strategy pass | Mode table with source/provenance/failure behavior complete | Any uncapped memory expansion path requires rollback note | Drafted |
| `cognitive-map-reduce-roadmap.md` | Stage A/B/C orchestration escalation model | Executor + forums + orchestration docs | `agent/executor.py`, `forums/*`, prompt pack | Strategy pass | Single-team vs multi-team rubric and communication contract present | If escalation criteria are not measurable, stage advancement blocked | Drafted |
| `ecosystem-soft-unification.md` | Alpha/beta to prod+sandbox migration contract | Storage + S3 + ETL + run config | `infra/storage.py`, `infra/s3_sync.py`, export/etl tools | Strategy pass | Compatibility contract and staged path defined | Any in-place historical ledger rewrite invalidates plan | Drafted |
| `implementation-wave-plan.md` | Post-approval execution waves for runtime changes | Engineering execution | All strategy docs above | Follow-up | Wave sequencing and test gates defined | Missing rollback rehearsal criteria blocks execution | Drafted |
| `wave-e1-ready-checklist.md` | Ready-to-execute checklist for Wave E1 implementation | Execution coordination | `implementation-wave-plan.md`, `memory-architecture.md`, runtime control surfaces | Follow-up | All E1 execution checkboxes and mandatory gates complete | Any failed gate or unmet rollback readiness blocks promotion | Drafted |

## External evidence set used

- Auton paper (`2602.23720v1`) uploaded markdown.
- AutoGen team docs (`Teams`, `SelectorGroupChat`).
- Hugging Face smolagents docs (`Multi-Agent Systems`, memory guide).
- LangGraph supervisor reference.
- CAMEL (NeurIPS 2023) for role-based cooperation risks.

## Promotion policy for this strategy package

- This package is planning-only until explicitly approved.
- Any runtime change proposal must reference at least one row in this table and include acceptance/rollback gates.

## Acceptance and rollback summary

- **Acceptance gate:** each strategy document has explicit scope labels plus acceptance/rollback criteria.
- **Rollback gate:** any contradiction between strategy claims and shipped code behavior blocks promotion until corrected.
