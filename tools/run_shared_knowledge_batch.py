"""Scheduled batch entrypoint for shared knowledge publish + ingest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from infra.shared_knowledge import validate_family_id
from infra.storage import validate_ecosystem_id
from tools.ingest_shared_knowledge import ingest_promotions_from_head
from tools.publish_shared_knowledge import publish_snapshot


def _state_file(base_dir: Path) -> Path:
    return base_dir / ".sync_state" / "shared_knowledge_batch_state.json"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run shared knowledge batch cycle")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystem", required=True, help="Any ecosystem in the family for base path resolution")
    parser.add_argument("--ecosystems", nargs="+", required=True, help="Source ecosystems for candidates")
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--min-quality", type=float, default=0.4)
    parser.add_argument("--vectordb-dir", type=Path, default=None)
    parser.add_argument("--collection", default="shared_knowledge")
    parser.add_argument("--include-candidates", action="store_true")
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    ecosystem_id = validate_ecosystem_id(args.ecosystem)
    ecosystems = [validate_ecosystem_id(value) for value in args.ecosystems]
    base_dir = args.base_dir.resolve()
    vectordb_dir = args.vectordb_dir or (base_dir / ".vectordb")

    pointer = publish_snapshot(
        base_dir=base_dir,
        family_id=family_id,
        ecosystem_id=ecosystem_id,
        ecosystems=ecosystems,
        min_quality=args.min_quality,
        include_candidates=args.include_candidates,
    )
    ingested = ingest_promotions_from_head(
        family_id=family_id,
        collection=args.collection,
        vectordb_dir=vectordb_dir,
    )

    state_path = _state_file(base_dir)
    state = _load_state(state_path)
    state.setdefault("families", {})
    state["families"][family_id] = {
        "last_snapshot_id": pointer.snapshot_id,
        "last_promoted_key": pointer.promoted_key,
        "last_grant_state_key": pointer.grant_state_key,
        "last_ingested_count": ingested,
    }
    _save_state(state_path, state)
    print(
        "[run_shared_knowledge_batch] "
        f"family={family_id} snapshot={pointer.snapshot_id} ingested={ingested}"
    )


if __name__ == "__main__":
    main()
