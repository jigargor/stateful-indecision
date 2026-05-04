# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
#     "huggingface_hub",
# ]
# ///
"""Quick analysis of a stateful-indecision ecosystem run.

Usage:
    uv run tools/analyze_run.py ecosystems/alpha/public.jsonl
    uv run tools/analyze_run.py ecosystems/alpha/public.jsonl --push gorji/si-alpha-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


def flatten_payload(df: pd.DataFrame) -> pd.DataFrame:
    payload_df = pd.json_normalize(df["payload"])
    payload_df.columns = [f"p_{c}" for c in payload_df.columns]
    return pd.concat([df.drop(columns=["payload"]), payload_df], axis=1)


def summarize(df: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"  Total events: {len(df)}")
    print(f"  Agents:       {df['agent_id'].nunique()} ({', '.join(sorted(df['agent_id'].unique()))})")
    print(f"  Event types:  {df['event_type'].nunique()}")
    print(f"{'='*60}\n")

    print("--- Events per agent ---")
    agent_counts = df["agent_id"].value_counts()
    for agent, count in agent_counts.items():
        pct = count / len(df) * 100
        print(f"  {agent:<25} {count:>5}  ({pct:.1f}%)")

    print("\n--- Event type distribution ---")
    type_counts = df["event_type"].value_counts().head(15)
    for etype, count in type_counts.items():
        print(f"  {etype:<40} {count:>5}")

    decisions = df[df["event_type"] == "agent.decision.taken"]
    if not decisions.empty:
        flat = flatten_payload(decisions.copy())
        print("\n--- Top-level action distribution ---")
        if "p_top_action" in flat.columns:
            top_counts = flat["p_top_action"].value_counts()
            for action, count in top_counts.items():
                print(f"  {action:<20} {count:>5}")

        print("\n--- Sub-action distribution (top 15) ---")
        if "p_sub_action" in flat.columns:
            sub_counts = flat["p_sub_action"].value_counts().head(15)
            for action, count in sub_counts.items():
                print(f"  {action:<30} {count:>5}")

        if "p_top_action" in flat.columns:
            print("\n--- Action dist per agent ---")
            for agent in sorted(flat["agent_id"].unique()):
                agent_df = flat[flat["agent_id"] == agent]
                top = agent_df["p_top_action"].value_counts()
                summary = ", ".join(f"{a}={c}" for a, c in top.head(6).items())
                print(f"  {agent:<25} {summary}")

    notebooks = df[df["event_type"] == "agent.notebook.appended"]
    if not notebooks.empty:
        print(f"\n--- Notebook entries: {len(notebooks)} ---")
        for agent in sorted(notebooks["agent_id"].unique()):
            agent_nb = notebooks[notebooks["agent_id"] == agent]
            texts = [e.get("text", "") for e in agent_nb["payload"]]
            unique = len(set(t.strip() for t in texts))
            dupes = len(texts) - unique
            print(f"  {agent:<25} {len(texts):>3} entries, {dupes:>3} duplicates")

    skills = df[df["event_type"] == "agent.skill.authored"]
    if not skills.empty:
        print(f"\n--- Skills authored: {len(skills)} ---")
        for _, row in skills.iterrows():
            print(f"  {row['agent_id']}: {row.get('payload', {}).get('artifact_path', '?')}")


def push_to_hub(df: pd.DataFrame, repo_id: str) -> None:
    from huggingface_hub import HfApi
    import tempfile

    api = HfApi()
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for _, row in df.iterrows():
            f.write(json.dumps(row.to_dict(), default=str) + "\n")
        tmp = f.name

    api.upload_file(path_or_fileobj=tmp, path_in_repo="data/events.jsonl", repo_id=repo_id, repo_type="dataset")
    Path(tmp).unlink()
    print(f"\nPushed to https://huggingface.co/datasets/{repo_id}")


def main():
    parser = argparse.ArgumentParser(description="Analyze a stateful-indecision run")
    parser.add_argument("jsonl", type=Path, help="Path to public.jsonl")
    parser.add_argument("--push", type=str, default=None, help="HF repo id to push dataset to")
    args = parser.parse_args()

    if not args.jsonl.exists():
        print(f"File not found: {args.jsonl}", file=sys.stderr)
        sys.exit(1)

    df = load_jsonl(args.jsonl)
    summarize(df)

    if args.push:
        push_to_hub(df, args.push)


if __name__ == "__main__":
    main()
