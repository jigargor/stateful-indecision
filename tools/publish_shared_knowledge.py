"""Publish family shared-knowledge snapshots to S3 and advance HEAD pointer."""
from __future__ import annotations

import argparse
from pathlib import Path

from infra.object_store import s3_object_store_from_env
from infra.shared_knowledge import validate_family_id
from infra.shared_knowledge_s3 import (
    SharedKnowledgeHeadPointer,
    sha256_bytes,
    shared_head_key,
    shared_snapshot_key,
    utc_now_compact,
)
from infra.storage import EcosystemStorage, validate_ecosystem_id
from tools.index_shared_knowledge import append_candidates, collect_candidates
from tools.materialize_shared_grants import materialize_grant_state
from tools.promote_shared_knowledge import _load_jsonl, append_promotions, promote_candidates


def _read_optional_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return path.read_bytes()


def publish_snapshot(
    *,
    base_dir: Path,
    family_id: str,
    ecosystem_id: str,
    ecosystems: list[str],
    min_quality: float,
    include_candidates: bool,
) -> SharedKnowledgeHeadPointer:
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    candidates_path = storage.shared_knowledge_candidates(family_id)
    promoted_path = storage.shared_knowledge_promoted(family_id)
    grant_ledger_path = storage.shared_knowledge_grant_ledger(family_id)
    grant_state_path = storage.shared_knowledge_grant_state(family_id)

    # Local staging phases
    candidate_entries = collect_candidates(base_dir=base_dir, family_id=family_id, ecosystems=ecosystems)
    append_candidates(candidates_path, candidate_entries)
    promoted_rows = promote_candidates(
        family_id=family_id,
        candidates=_load_jsonl(candidates_path),
        min_quality=min_quality,
    )
    append_promotions(promoted_path, promoted_rows)
    materialize_grant_state(
        ledger_path=grant_ledger_path,
        state_path=grant_state_path,
        family_id=family_id,
    )

    promoted_bytes = promoted_path.read_bytes() if promoted_path.exists() else b""
    grant_state_bytes = grant_state_path.read_bytes() if grant_state_path.exists() else b""
    candidates_bytes = _read_optional_bytes(candidates_path)
    grant_ledger_bytes = _read_optional_bytes(grant_ledger_path)

    snapshot_id = utc_now_compact()
    promoted_key = shared_snapshot_key(family_id, snapshot_id, "promoted.jsonl")
    grant_state_key = shared_snapshot_key(family_id, snapshot_id, "grant_state.json")
    candidates_key = shared_snapshot_key(family_id, snapshot_id, "candidates.jsonl")
    grant_ledger_key = shared_snapshot_key(family_id, snapshot_id, "grant_ledger.jsonl")

    store = s3_object_store_from_env()
    if store is None:
        raise RuntimeError("S3 object store is not configured (S3_OFFLOAD_ENABLED/S3_OFFLOAD_BUCKET)")

    store.put_bytes(key=promoted_key, payload=promoted_bytes, content_type="application/x-ndjson")
    store.put_bytes(key=grant_state_key, payload=grant_state_bytes, content_type="application/json")
    if include_candidates and candidates_bytes is not None:
        store.put_bytes(key=candidates_key, payload=candidates_bytes, content_type="application/x-ndjson")
    if grant_ledger_bytes is not None:
        store.put_bytes(key=grant_ledger_key, payload=grant_ledger_bytes, content_type="application/x-ndjson")

    pointer = SharedKnowledgeHeadPointer(
        family_id=family_id,
        snapshot_id=snapshot_id,
        updated_at=snapshot_id,
        promoted_key=promoted_key,
        grant_state_key=grant_state_key,
        candidates_key=candidates_key if include_candidates and candidates_bytes is not None else None,
        grant_ledger_key=grant_ledger_key if grant_ledger_bytes is not None else None,
        promoted_sha256=sha256_bytes(promoted_bytes),
        grant_state_sha256=sha256_bytes(grant_state_bytes),
        candidates_sha256=sha256_bytes(candidates_bytes) if include_candidates and candidates_bytes is not None else None,
        grant_ledger_sha256=sha256_bytes(grant_ledger_bytes) if grant_ledger_bytes is not None else None,
        metadata={
            "source_ecosystems": ecosystems,
            "min_quality": min_quality,
        },
    )
    store.put_bytes(
        key=shared_head_key(family_id),
        payload=pointer.to_json_bytes(),
        content_type="application/json",
    )
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish shared knowledge snapshot to S3")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystem", required=True, help="Any ecosystem in the family for base path resolution")
    parser.add_argument("--ecosystems", nargs="+", required=True, help="Source ecosystems for candidates")
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--min-quality", type=float, default=0.4)
    parser.add_argument("--include-candidates", action="store_true")
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    ecosystem_id = validate_ecosystem_id(args.ecosystem)
    ecosystems = [validate_ecosystem_id(value) for value in args.ecosystems]
    base_dir = args.base_dir.resolve()
    pointer = publish_snapshot(
        base_dir=base_dir,
        family_id=family_id,
        ecosystem_id=ecosystem_id,
        ecosystems=ecosystems,
        min_quality=args.min_quality,
        include_candidates=args.include_candidates,
    )
    print(
        "[publish_shared_knowledge] "
        f"family={pointer.family_id} snapshot={pointer.snapshot_id} promoted_key={pointer.promoted_key}"
    )


if __name__ == "__main__":
    main()
