"""Consolidate notebook entries into long-term memory via the vector store.

Reads notebook.jsonl for an agent, groups older entries into summary chunks,
embeds them into the vector store, and reports consolidation stats.

Retains the original analytics output (duplication stats) alongside the
new LTM consolidation pipeline.

Usage:
    python -m tools.consolidate_notebook --ecosystem alpha --agent-id psych-lead
    python -m tools.consolidate_notebook --ecosystem beta --agent-id beta-agent-1 --embed
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_notebook_texts(path: Path) -> list[dict]:
    """Load notebook entries with full metadata."""
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") != "agent.notebook.appended":
            continue
        payload = event.get("payload", {})
        entries.append({
            "text": str(payload.get("text", "")),
            "ref_decision_id": payload.get("ref_decision_id", ""),
            "fingerprint": payload.get("fingerprint", ""),
            "wall_time": event.get("wall_time", ""),
            "event_id": event.get("event_id", ""),
            "agent_id": event.get("agent_id", ""),
        })
    return entries


def summarize_texts(texts: list[str], top_k: int = 5) -> dict[str, object]:
    """Original analytics: duplication stats."""
    counts = Counter(t.strip() for t in texts if t.strip())
    total = len(texts)
    unique = len(counts)
    duplicates = total - unique
    most_common = [
        {"count": count, "text": text[:200]}
        for text, count in counts.most_common(top_k)
    ]
    return {
        "total_entries": total,
        "unique_entries": unique,
        "duplicate_entries": duplicates,
        "duplicate_pct": round((duplicates / total) * 100.0, 2) if total else 0.0,
        "most_common_entries": most_common,
    }


def group_into_ltm_chunks(
    entries: list[dict],
    chunk_size: int = 10,
    recent_cap: int = 5,
) -> list[dict]:
    """Group older notebook entries into summary chunks for LTM embedding.

    The most recent `recent_cap` entries are kept as STM and not consolidated.
    Older entries are grouped into chunks of `chunk_size` for summarization.
    """
    if len(entries) <= recent_cap:
        return []

    older = entries[:-recent_cap] if recent_cap > 0 else entries
    chunks: list[dict] = []

    for start in range(0, len(older), chunk_size):
        batch = older[start : start + chunk_size]
        texts = [e["text"] for e in batch if e["text"].strip()]
        if not texts:
            continue

        unique_texts = list(dict.fromkeys(texts))
        combined = "\n---\n".join(unique_texts)

        time_range_start = batch[0].get("wall_time", "")
        time_range_end = batch[-1].get("wall_time", "")
        decision_ids = [e["ref_decision_id"] for e in batch if e["ref_decision_id"]]

        chunks.append({
            "text": combined,
            "content_hash": _content_hash(combined),
            "entry_count": len(batch),
            "unique_count": len(unique_texts),
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
            "decision_ids": decision_ids,
        })

    return chunks


def embed_ltm_chunks(
    chunks: list[dict],
    *,
    agent_id: str,
    ecosystem_id: str,
    vectordb_dir: Path,
    collection: str = "notebook_ltm",
) -> int:
    """Embed consolidated notebook chunks into the vector store."""
    from infra.embeddings import get_embedder
    from infra.vector_store import VectorStore

    if not chunks:
        return 0

    store = VectorStore(persist_dir=vectordb_dir)
    embedder = get_embedder()

    ids = [c["content_hash"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [
        {
            "agent_id": agent_id,
            "ecosystem_id": ecosystem_id,
            "source_type": "notebook_ltm",
            "entry_count": str(c["entry_count"]),
            "unique_count": str(c["unique_count"]),
            "time_range_start": c["time_range_start"],
            "time_range_end": c["time_range_end"],
        }
        for c in chunks
    ]

    return store.upsert_documents(
        collection=collection,
        ids=ids,
        texts=texts,
        metadatas=metadatas,
        embedder=embedder,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate notebook entries into LTM and report duplication stats."
    )
    parser.add_argument("--ecosystem", required=True, help="Ecosystem id, e.g. alpha or beta")
    parser.add_argument("--agent-id", required=True, help="Agent id, e.g. psych-lead")
    parser.add_argument("--base-dir", default=".", help="Repository base directory")
    parser.add_argument("--output", default="", help="Optional output path for summary JSON")
    parser.add_argument(
        "--embed", action="store_true",
        help="Embed consolidated chunks into the vector store (requires rag deps)",
    )
    parser.add_argument("--vectordb-dir", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--recent-cap", type=int, default=5)
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    notebook_path = (
        base_dir / "ecosystems" / args.ecosystem / "agents" / args.agent_id / "notebook.jsonl"
    )

    entries = load_notebook_texts(notebook_path)
    texts = [e["text"] for e in entries]
    stats = summarize_texts(texts)
    print(json.dumps(stats, indent=2))

    chunks = group_into_ltm_chunks(
        entries,
        chunk_size=args.chunk_size,
        recent_cap=args.recent_cap,
    )
    print(f"\n[consolidate] {len(chunks)} LTM chunks from {len(entries)} notebook entries")

    if args.embed and chunks:
        from infra.env import load_env
        load_env(base_dir)

        vectordb_dir = args.vectordb_dir or (base_dir / ".vectordb")
        count = embed_ltm_chunks(
            chunks,
            agent_id=args.agent_id,
            ecosystem_id=args.ecosystem,
            vectordb_dir=vectordb_dir,
        )
        print(f"[consolidate] embedded {count} chunks into notebook_ltm collection")

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (base_dir / output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = {
            **stats,
            "ltm_chunks": len(chunks),
            "ltm_chunk_details": [
                {k: v for k, v in c.items() if k != "text"}
                for c in chunks
            ],
        }
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote summary to {output_path}")


if __name__ == "__main__":
    main()
