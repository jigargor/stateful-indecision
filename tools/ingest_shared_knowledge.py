"""Ingest promoted shared-knowledge records into the vector store."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from infra.shared_knowledge import validate_family_id
from infra.storage import EcosystemStorage, validate_ecosystem_id


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def ingest_promotions(
    promoted_path: Path,
    *,
    vectordb_dir: Path,
    collection: str,
) -> int:
    from infra.embeddings import get_embedder
    from infra.vector_store import VectorStore

    rows = _load_jsonl(promoted_path)
    rows = [row for row in rows if str(row.get("content", "")).strip()]
    if not rows:
        return 0

    ids = [str(row["promotion_id"]) for row in rows]
    texts = [str(row["content"])[:4000] for row in rows]
    metadatas = [{
        "promotion_id": str(row.get("promotion_id", "")),
        "family_id": str(row.get("family_id", "")),
        "content_hash": str(row.get("content_hash", "")),
        "action": str(row.get("action", "")),
        "quality_score": float(row.get("quality_score", 0.0)),
        "visibility": "promoted",
        "source_type": "shared_knowledge",
    } for row in rows]

    store = VectorStore(persist_dir=vectordb_dir)
    embedder = get_embedder()
    return store.upsert_documents(
        collection=collection,
        ids=ids,
        texts=texts,
        metadatas=metadatas,
        embedder=embedder,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest promoted shared knowledge")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystem", required=True, help="Any ecosystem in the family for base path resolution")
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--vectordb-dir", type=Path, default=None)
    parser.add_argument("--collection", default="shared_knowledge")
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    ecosystem_id = validate_ecosystem_id(args.ecosystem)
    base_dir = args.base_dir.resolve()
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    promoted_path = storage.shared_knowledge_promoted(family_id)
    vectordb_dir = args.vectordb_dir or (base_dir / ".vectordb")

    count = ingest_promotions(
        promoted_path=promoted_path,
        vectordb_dir=vectordb_dir,
        collection=args.collection,
    )
    print(f"[ingest_shared_knowledge] upserted {count} records from {promoted_path}")


if __name__ == "__main__":
    main()
