"""Human-readable trace renderer. No hashes, no UUIDs, no envelope noise."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def render_trace(ecosystem: str, agent_id: str | None, base_dir: str = ".") -> int:
    base = Path(base_dir).resolve()
    public = base / "ecosystems" / ecosystem / "public.jsonl"
    if not public.exists():
        print(f"No public ledger at {public}")
        return 1

    events = [json.loads(l) for l in public.read_text("utf-8").splitlines() if l.strip()]
    if agent_id:
        events = [e for e in events if e.get("agent_id") == agent_id or e.get("agent_id") is None]

    step_num = 0
    for event in events:
        et = event.get("event_type", "")
        payload = event.get("payload", {})
        agent = event.get("agent_id", "")

        if et == "agent.instantiated":
            provider = payload.get("provider", "?")
            model = payload.get("model_id", "?")
            print(f"[start] Agent {agent} instantiated ({provider}:{model})")

        elif et == "field.chosen":
            print(f"[start] Field chosen: {payload.get('field', '?')}")
            print()

        elif et == "agent.decision.taken":
            step_num += 1
            top = payload.get("top_action", "?")
            sub = payload.get("sub_action", "?")
            print(f"[{step_num}] {top}/{sub}")

        elif et == "action.executed":
            output = str(payload.get("raw_output", ""))
            metrics = payload.get("metrics", {})
            tok_in = metrics.get("tokens_in", "?")
            tok_out = metrics.get("tokens_out", "?")
            latency = ""
            try:
                ms = metrics["wall_end_ms"] - metrics["wall_start_ms"]
                latency = f"  {ms:.0f}ms"
            except (KeyError, TypeError):
                pass

            effects = payload.get("side_effects", [])
            lines = output.strip().split("\n")
            preview = lines[0][:200] if lines else ""
            if len(lines) > 1:
                preview += f" (+{len(lines)-1} lines)"

            print(f"    tok={tok_in}+{tok_out}{latency}")
            if effects:
                print(f"    side: {', '.join(effects)}")
            print(f"    >>> {preview}")
            print()

        elif et == "agent.constitution.revised":
            amendment = str(payload.get("amendment_text", ""))[:300].replace("\n", " | ")
            print(f"    *** CONSTITUTION AMENDED: {amendment}")
            print()

        elif et == "run.completed":
            print(f"[done] {payload.get('decisions_completed', '?')} decisions completed")
            dist = payload.get("action_distribution_observed", {})
            if dist:
                print("  action distribution:")
                for act, count in sorted(dist.items(), key=lambda x: -x[1]):
                    print(f"    {act:<40} {count}")
            rev = payload.get("constitution_revision_count", 0)
            nb = payload.get("notebook_entries", 0)
            print(f"  constitution revisions: {rev}  notebook entries: {nb}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Human-readable trace of an agent run")
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()
    return render_trace(args.ecosystem, args.agent, args.base_dir)


if __name__ == "__main__":
    raise SystemExit(main())
