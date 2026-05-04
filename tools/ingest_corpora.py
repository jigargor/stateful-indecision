"""Ingest corpora markdown files into the vector store for RAG retrieval.

Chunks markdown by heading sections and embeds each chunk.

Usage:
    python -m tools.ingest_corpora --ecosystem alpha --base-dir .
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from infra.storage import EcosystemStorage


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(text: str, source_path: str) -> list[dict]:
    """Split markdown into chunks by top-level and second-level headings."""
    chunks: list[dict] = []
    current_heading = "preamble"
    current_lines: list[str] = []

    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,2})\s+(.+)$", line)
        if heading_match:
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chunks.append({
                        "heading": current_heading,
                        "text": body,
                        "source_path": source_path,
                    })
            current_heading = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append({
                "heading": current_heading,
                "text": body,
                "source_path": source_path,
            })

    return chunks


def ingest_corpora(
    storage: EcosystemStorage,
    *,
    vectordb_dir: Path,
    collection: str = "corpora",
) -> int:
    """Read all markdown files in the corpus dir and embed them."""
    from infra.embeddings import get_embedder
    from infra.vector_store import VectorStore

    corpus_dir = storage.corpus_dir()
    md_files = sorted(corpus_dir.glob("*.md"))
    if not md_files:
        print(f"[ingest_corpora] no .md files found in {corpus_dir}")
        return 0

    all_chunks: list[dict] = []
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        rel_path = md_file.relative_to(storage.base_dir).as_posix()
        chunks = chunk_markdown(text, rel_path)
        all_chunks.extend(chunks)

    if not all_chunks:
        return 0

    ids = [_content_hash(c["text"]) for c in all_chunks]
    texts = [c["text"] for c in all_chunks]
    metadatas = [
        {
            "heading": c["heading"],
            "source_path": c["source_path"],
            "source_type": "corpus",
            "ecosystem_id": storage.ecosystem_id,
        }
        for c in all_chunks
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
        description="Ingest corpora markdown into the vector store"
    )
    parser.add_argument("--ecosystem", required=True, choices=["alpha", "beta"])
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--vectordb-dir", type=Path, default=None)
    parser.add_argument("--collection", default="corpora")
    args = parser.parse_args()

    from infra.env import load_env
    base_dir = args.base_dir.resolve()
    load_env(base_dir)

    storage = EcosystemStorage(args.ecosystem, base_dir)
    vectordb_dir = args.vectordb_dir or (base_dir / ".vectordb")

    count = ingest_corpora(
        storage,
        vectordb_dir=vectordb_dir,
        collection=args.collection,
    )
    print(f"[ingest_corpora] upserted {count} chunks into '{args.collection}'")


if __name__ == "__main__":
    main()
