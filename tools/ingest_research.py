"""Ingest research artifacts from a manifest into the vector store.

Reads the research_manifest.jsonl produced by index_research.py and
embeds each artifact's content into ChromaDB for RAG retrieval.

Usage:
    python -m tools.ingest_research --ecosystem beta --base-dir .
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def ingest_manifest(
    manifest_path: Path,
    *,
    vectordb_dir: Path,
    collection: str = "research_artifacts",
) -> int:
    """Read manifest and upsert all entries into the vector store."""
    from infra.embeddings import get_embedder
    from infra.vector_store import VectorStore

    if not manifest_path.exists():
        print(f"[ingest_research] manifest not found: {manifest_path}")
        return 0

    entries: list[dict] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        print("[ingest_research] manifest is empty")
        return 0

    entries = [e for e in entries if e.get("content", "").strip()]

    ids = [e["content_hash"] for e in entries]
    texts = [e["content"][:4000] for e in entries]
    metadatas = [
        {
            "artifact_id": e.get("artifact_id", ""),
            "agent_id": e.get("agent_id", ""),
            "ecosystem_id": e.get("ecosystem_id", ""),
            "action": e.get("action", ""),
            "config_version": e.get("config_version", ""),
            "created_at": e.get("created_at", ""),
            "source_type": e.get("source_type", ""),
            "source_path": e.get("source_path", ""),
        }
        for e in entries
    ]

    store = VectorStore(persist_dir=vectordb_dir)
    embedder = get_embedder()

    count = store.upsert_documents(
        collection=collection,
        ids=ids,
        texts=texts,
        metadatas=metadatas,
        embedder=embedder,
    )
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest research manifest into the vector store for RAG"
    )
    parser.add_argument("--ecosystem", required=True, choices=["alpha", "beta"])
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--vectordb-dir", type=Path, default=None)
    parser.add_argument("--collection", default="research_artifacts")
    parser.add_argument(
        "--manifest", default=None,
        help="Manifest path (default: .sync_state/<ecosystem>_research_manifest.jsonl)",
    )
    args = parser.parse_args()

    from infra.env import load_env
    base_dir = args.base_dir.resolve()
    load_env(base_dir)

    manifest_path = Path(args.manifest) if args.manifest else (
        base_dir / ".sync_state" / f"{args.ecosystem}_research_manifest.jsonl"
    )
    vectordb_dir = args.vectordb_dir or (base_dir / ".vectordb")

    count = ingest_manifest(
        manifest_path,
        vectordb_dir=vectordb_dir,
        collection=args.collection,
    )
    print(f"[ingest_research] upserted {count} artifacts into '{args.collection}'")


if __name__ == "__main__":
    main()
