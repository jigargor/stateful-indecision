from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from datasets import load_dataset


def read_jsonl_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def top_action_entropy(rows: list[dict]) -> float:
    top_counts: dict[str, int] = {}
    total = 0
    for row in rows:
        if row.get("event_type") != "agent.decision.taken":
            continue
        payload = row.get("payload", {})
        action = payload.get("top_action")
        if not action:
            continue
        total += 1
        top_counts[action] = top_counts.get(action, 0) + 1
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in top_counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def notebook_dup_stats(ecosystem_dir: Path) -> tuple[int, int, float]:
    total_entries = 0
    total_unique = 0
    notebooks = list((ecosystem_dir / "agents").glob("*/notebook.jsonl"))
    for notebook_path in notebooks:
        if not notebook_path.exists():
            continue
        rows = read_jsonl_rows(notebook_path)
        texts = [row.get("payload", {}).get("text", "").strip() for row in rows if row.get("event_type") == "agent.notebook.appended"]
        total_entries += len(texts)
        total_unique += len(set(texts))
    dupes = total_entries - total_unique
    ratio = (dupes / total_entries) if total_entries else 0.0
    return total_entries, dupes, ratio


def summarize_dataset(path: Path) -> dict[str, float | int]:
    ds = load_dataset("json", data_files=str(path), split="train")
    rows = [dict(item) for item in ds]
    event_type_counts: dict[str, int] = {}
    for row in rows:
        et = row.get("event_type", "")
        event_type_counts[et] = event_type_counts.get(et, 0) + 1
    decisions = event_type_counts.get("agent.decision.taken", 0)
    return {
        "events": len(rows),
        "decisions": decisions,
        "commons_utterance": event_type_counts.get("commons.utterance", 0),
        "roundtable_utterance": event_type_counts.get("roundtable.utterance", 0),
        "skill_authored": event_type_counts.get("agent.skill.authored", 0),
        "entropy_top_action": top_action_entropy(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare alpha and beta runs with Hugging Face datasets")
    parser.add_argument("--alpha", default="ecosystems/alpha/public.jsonl")
    parser.add_argument("--beta", default="ecosystems/beta/public.jsonl")
    args = parser.parse_args()

    alpha_path = Path(args.alpha)
    beta_path = Path(args.beta)
    alpha_summary = summarize_dataset(alpha_path)
    beta_summary = summarize_dataset(beta_path)

    alpha_nb = notebook_dup_stats(alpha_path.parent)
    beta_nb = notebook_dup_stats(beta_path.parent)

    print("=== HF DATASETS COMPARISON ===")
    print(f"alpha events: {alpha_summary['events']}")
    print(f"beta events:  {beta_summary['events']}")
    print(f"alpha decisions: {alpha_summary['decisions']}")
    print(f"beta decisions:  {beta_summary['decisions']}")
    print()
    print(f"alpha commons utterances: {alpha_summary['commons_utterance']}")
    print(f"beta commons utterances:  {beta_summary['commons_utterance']}")
    print(f"alpha roundtable utterances: {alpha_summary['roundtable_utterance']}")
    print(f"beta roundtable utterances:  {beta_summary['roundtable_utterance']}")
    print()
    print(f"alpha top-action entropy: {alpha_summary['entropy_top_action']:.3f}")
    print(f"beta top-action entropy:  {beta_summary['entropy_top_action']:.3f}")
    print("(lower entropy = more differentiated / less uniform)")
    print()
    print(f"alpha notebook entries: {alpha_nb[0]}, duplicates: {alpha_nb[1]} ({alpha_nb[2]*100:.1f}%)")
    print(f"beta notebook entries:  {beta_nb[0]}, duplicates: {beta_nb[1]} ({beta_nb[2]*100:.1f}%)")
    print()
    print(f"alpha skill-authored events: {alpha_summary['skill_authored']}")
    print(f"beta skill-authored events:  {beta_summary['skill_authored']}")


if __name__ == "__main__":
    main()
