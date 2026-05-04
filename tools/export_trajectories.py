from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_trajectories(events: list[dict], ecosystem_id: str) -> list[dict]:
    by_agent: dict[str, list[dict]] = {}
    for event in events:
        if event.get("ecosystem_id") != ecosystem_id:
            continue
        agent_id = event.get("agent_id")
        if not agent_id:
            continue
        by_agent.setdefault(agent_id, []).append(event)

    trajectories: list[dict] = []
    for agent_id, agent_events in by_agent.items():
        decision_events = [e for e in agent_events if e.get("event_type") == "agent.decision.taken"]
        execution_by_decision = {
            e.get("payload", {}).get("decision_event_id"): e
            for e in agent_events
            if e.get("event_type") == "action.executed"
        }
        for decision in decision_events:
            decision_event_id = decision.get("event_id")
            payload = decision.get("payload", {})
            execution = execution_by_decision.get(decision_event_id)
            exec_payload = execution.get("payload", {}) if execution else {}
            metrics = exec_payload.get("metrics", {}) if isinstance(exec_payload, dict) else {}
            trajectories.append(
                {
                    "ecosystem_id": ecosystem_id,
                    "agent_id": agent_id,
                    "decision_event_id": decision_event_id,
                    "snapshot_id": payload.get("snapshot_id"),
                    "top_action": payload.get("top_action"),
                    "sub_action": payload.get("sub_action"),
                    "sample_seed": payload.get("sample_seed"),
                    "raw_output": exec_payload.get("raw_output"),
                    "structured_output": exec_payload.get("structured"),
                    "side_effects": exec_payload.get("side_effects", []),
                    "tokens_in": metrics.get("tokens_in"),
                    "tokens_out": metrics.get("tokens_out"),
                    "stop_reason": metrics.get("stop_reason"),
                    "wall_time": decision.get("wall_time"),
                }
            )
    return trajectories


def main() -> None:
    parser = argparse.ArgumentParser(description="Export decision trajectories for offline training.")
    parser.add_argument("--ecosystem", required=True, help="Ecosystem id, e.g. alpha or beta")
    parser.add_argument("--base-dir", default=".", help="Repository base directory")
    parser.add_argument("--output", required=True, help="Output JSONL file path")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    public_path = base_dir / "ecosystems" / args.ecosystem / "public.jsonl"
    events = load_jsonl(public_path)
    trajectories = build_trajectories(events, args.ecosystem)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (base_dir / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        for row in trajectories:
            out.write(json.dumps(row) + "\n")
    print(f"Wrote {len(trajectories)} trajectories to {output_path}")


if __name__ == "__main__":
    main()
