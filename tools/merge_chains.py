"""
Merge multiple same-type ledger chains from different ecosystem runs into one
unified hash chain. Events are sorted by ts_wall_utc. Hashes are recomputed
so the output chain is valid. Original event_ids are preserved.

Usage:
    python tools/merge_chains.py --ledger public
    python tools/merge_chains.py --ledger commons
    python tools/merge_chains.py --ledger evaluation

Source files are read from ecosystems/alpha/ across all specified worktrees.
Output is written to ecosystems/alpha/<ledger>.jsonl (in-place).
"""

import argparse
import json
import sys
from pathlib import Path

# Project root = parent of this file's directory
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.canonical_json import canonical_hash


GENESIS_HASH = "0" * 64

WORKTREE_SOURCES = [
    Path("C:/Users/gorji/Documents/2026/si-biochemistry"),
    Path("C:/Users/gorji/Documents/2026/si-psychiatry"),
    Path("C:/Users/gorji/Documents/2026/si-software-eng"),
]


def read_chain(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def rechain(events: list[dict]) -> list[dict]:
    """Re-link events into a valid hash chain, preserving all other fields."""
    rechained = []
    prev_hash = GENESIS_HASH
    for event in events:
        new_event = dict(event)
        new_event["prev_hash"] = prev_hash
        new_event.pop("record_hash", None)
        record_hash = canonical_hash(new_event)
        new_event["record_hash"] = record_hash
        prev_hash = record_hash
        rechained.append(new_event)
    return rechained


def merge_ledger(ledger_name: str, dest_dir: Path) -> None:
    all_events: list[dict] = []

    # Collect from worktrees
    for wt in WORKTREE_SOURCES:
        src = wt / "ecosystems" / "alpha" / f"{ledger_name}.jsonl"
        events = read_chain(src)
        print(f"  {src}: {len(events)} events")
        all_events.extend(events)

    # Also collect from main (may have stub events from test run)
    main_src = dest_dir / f"{ledger_name}.jsonl"
    main_events = read_chain(main_src)
    print(f"  main (existing): {len(main_events)} events")
    all_events.extend(main_events)

    if not all_events:
        print(f"  No events found for {ledger_name}, skipping.")
        return

    # Deduplicate by event_id (keep first occurrence)
    seen: set[str] = set()
    deduped: list[dict] = []
    for ev in all_events:
        eid = ev.get("event_id", "")
        if eid not in seen:
            seen.add(eid)
            deduped.append(ev)

    # Sort by wall timestamp, then monotonic_ns as tiebreaker
    deduped.sort(key=lambda e: (e.get("ts_wall_utc", ""), e.get("ts_monotonic_ns", 0)))

    print(f"  Total after dedup: {len(deduped)} events")

    # Rebuild hash chain
    rechained = rechain(deduped)

    # Write output
    out_path = dest_dir / f"{ledger_name}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for ev in rechained:
            f.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(f"  Written {len(rechained)} events to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge ledger chains from multiple worktrees.")
    parser.add_argument(
        "--ledger",
        choices=["public", "commons", "evaluation", "all"],
        default="all",
    )
    args = parser.parse_args()

    dest_dir = ROOT / "ecosystems" / "alpha"
    dest_dir.mkdir(parents=True, exist_ok=True)

    ledgers = ["public", "commons", "evaluation"] if args.ledger == "all" else [args.ledger]

    for ledger in ledgers:
        print(f"\nMerging {ledger}.jsonl ...")
        merge_ledger(ledger, dest_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
