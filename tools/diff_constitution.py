from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="Show constitution revision history")
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    base = Path(args.base_dir).resolve()
    constitution_path = base / "ecosystems" / args.ecosystem / "agents" / args.agent / "constitution.md"
    public_path = base / "ecosystems" / args.ecosystem / "public.jsonl"

    if not constitution_path.exists():
        print(f"Constitution not found: {constitution_path}")
        return 1

    print(f"=== Constitution: {args.agent} ===")
    print(constitution_path.read_text(encoding="utf-8"))

    if public_path.exists():
        revisions = []
        for line in public_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event_type") == "agent.constitution.revised" and event.get("agent_id") == args.agent:
                revisions.append(event)

        if revisions:
            print(f"\n=== {len(revisions)} revision(s) found ===\n")
            for i, rev in enumerate(revisions, 1):
                payload = rev.get("payload", {})
                print(f"--- Revision {i} (event: {rev.get('event_id', '?')[:12]}...) ---")
                print(f"  amendment: {payload.get('amendment_text', '(none)')}")
                if payload.get("revision_diff"):
                    print(f"  diff:\n{payload['revision_diff']}")
                print()
        else:
            print("\nNo revisions recorded in public ledger.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
