from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load_notebook_texts(path: Path) -> list[str]:
    if not path.exists():
        return []
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_type") != "agent.notebook.appended":
            continue
        texts.append(str(event.get("payload", {}).get("text", "")))
    return texts


def summarize_texts(texts: list[str], top_k: int = 5) -> dict[str, object]:
    counts = Counter(t.strip() for t in texts if t.strip())
    total = len(texts)
    unique = len(counts)
    duplicates = total - unique
    most_common = [{"count": count, "text": text[:200]} for text, count in counts.most_common(top_k)]
    return {
        "total_entries": total,
        "unique_entries": unique,
        "duplicate_entries": duplicates,
        "duplicate_pct": round((duplicates / total) * 100.0, 2) if total else 0.0,
        "most_common_entries": most_common,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize notebook duplication and common patterns.")
    parser.add_argument("--ecosystem", required=True, help="Ecosystem id, e.g. alpha or beta")
    parser.add_argument("--agent-id", required=True, help="Agent id, e.g. psych-lead")
    parser.add_argument("--base-dir", default=".", help="Repository base directory")
    parser.add_argument("--output", default="", help="Optional output path for summary JSON")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    notebook_path = base_dir / "ecosystems" / args.ecosystem / "agents" / args.agent_id / "notebook.jsonl"
    texts = load_notebook_texts(notebook_path)
    summary = summarize_texts(texts)

    print(json.dumps(summary, indent=2))
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (base_dir / output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote summary to {output_path}")


if __name__ == "__main__":
    main()
