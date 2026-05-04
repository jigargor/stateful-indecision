from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _render_trace(events: list[dict]) -> None:
    for event in events:
        et = event.get("event_type", "?")
        agent = event.get("agent_id", "")
        payload = event.get("payload", {})

        if et == "agent.decision.taken":
            top = payload.get("top_action", "?")
            sub = payload.get("sub_action", "?")
            print(f"  [{agent}] {top}/{sub}")
        elif et == "action.executed":
            output = str(payload.get("raw_output", ""))[:200].replace("\n", " ")
            metrics = payload.get("metrics", {})
            tok = f"tok={metrics.get('tokens_in', '?')}+{metrics.get('tokens_out', '?')}"
            effects = payload.get("side_effects", [])
            print(f"    {tok}  >>> {output}")
            if effects:
                print(f"    side: {', '.join(effects)}")
        elif et == "agent.constitution.revised":
            amendment = str(payload.get("amendment_text", ""))[:150].replace("\n", " ")
            print(f"  [{agent}] CONSTITUTION REVISED: {amendment}")
        elif et == "agent.notebook.appended":
            text = str(payload.get("text", ""))[:150].replace("\n", " ")
            print(f"    notebook: {text}")
        elif et == "agent.instantiated":
            print(f"  [{agent}] INSTANTIATED (provider: {payload.get('provider', '?')}, model: {payload.get('model_id', '?')})")
        elif et == "field.chosen":
            print(f"  [{agent}] FIELD CHOSEN: {payload.get('field', '?')}")
        elif et == "run.completed":
            print(f"  [{agent}] RUN COMPLETE: {payload.get('decisions_completed', '?')} decisions")
            dist = payload.get("action_distribution_observed", {})
            for act, count in sorted(dist.items(), key=lambda x: -x[1]):
                print(f"    {act:<40} {count}")
        elif et in {"web.search.requested", "web.search.results.received", "web.fetch.requested", "web.fetch.received"}:
            pass
        else:
            print(f"  [{agent}] {et}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a ledger file")
    parser.add_argument("ledger", nargs="?", help="path to .jsonl file")
    parser.add_argument("--ecosystem", default=None)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--format", choices=["json", "trace"], default="json")
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    if args.ledger:
        path = Path(args.ledger)
    elif args.ecosystem:
        base = Path(args.base_dir).resolve()
        path = base / "ecosystems" / args.ecosystem / "public.jsonl"
    else:
        parser.error("provide a ledger path or --ecosystem")
        return 1

    if not path.exists():
        print(f"{path} does not exist")
        return 1

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.event_type:
        events = [e for e in events if e.get("event_type") == args.event_type]
    if args.agent:
        events = [e for e in events if e.get("agent_id") == args.agent]
    events = events[-args.limit:]

    if args.format == "trace":
        _render_trace(events)
    else:
        for event in events:
            print(json.dumps(event, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
