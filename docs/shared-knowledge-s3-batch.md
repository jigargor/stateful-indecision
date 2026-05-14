# Shared Knowledge S3 Batch Runbook

This runbook describes the minutes-latency batch flow for shared knowledge publication and retrieval.

## S3 Key Layout

- `shared_knowledge/<family_id>/HEAD.json`
- `shared_knowledge/<family_id>/snapshots/<snapshot_id>/promoted.jsonl`
- `shared_knowledge/<family_id>/snapshots/<snapshot_id>/grant_state.json`
- Optional:
  - `.../candidates.jsonl`
  - `.../grant_ledger.jsonl`

`HEAD.json` points runtime and ingest jobs to the active snapshot and includes SHA256 checksums for integrity verification.

## Batch Cycle

Run every 5-15 minutes:

```bash
uv run python -m tools.run_shared_knowledge_batch \
  --family-id research-family \
  --ecosystem alpha \
  --ecosystems alpha beta \
  --base-dir .
```

What it does:

1. Build candidate records from source ecosystems.
2. Promote + deduplicate records.
3. Materialize `grant_state.json`.
4. Publish immutable snapshot artifacts to S3.
5. Update `HEAD.json`.
6. Ingest promoted records from `HEAD.json` into the vector index.
7. Record ingest checkpoint in `.sync_state/shared_ingest_<family_id>.json`.

## Subsequent Run Retrieval

Enable in run config:

- `enable_shared_knowledge_retrieval: true`
- `shared_knowledge_family_id: <family_id>`
- `shared_knowledge_access_profile: <profile>`
- `shared_knowledge_use_s3_head: true`

When enabled, runtime resolves `HEAD.json`, loads the referenced `grant_state.json`, evaluates grants, and only then queries shared vector records.

## Rollback

To roll back shared retrieval to a prior snapshot, replace `HEAD.json` with a previous version (or re-upload older pointer content). No vector IDs change because IDs are stable `promotion_id` values.
