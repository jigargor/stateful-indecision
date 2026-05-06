"""Export decision trajectories as JSONL for offline RL / preference training.

Usage:
    python -m tools.export_trajectories --ecosystem beta --base-dir . --output trajectories.jsonl

Output format: JSONL (one JSON object per line). Each line represents a single
decision-execution pair. HuggingFace ``datasets.load_dataset("json", ...)``
can ingest this directly.

Schema (18 fields):
    ecosystem_id        str       Ecosystem identifier (e.g. "alpha", "beta").
    agent_id            str       Agent that made the decision.
    decision_event_id   str       Event ID of the ``agent.decision.taken`` event.
    decision_number     int       0-based index of this decision within the agent's
                                  trajectory, ordered by wall_time.
    snapshot_id         str|null  State snapshot ID at decision time.
    top_action          str|null  Top-level action chosen.
    sub_action          str|null  Sub-action (if any).
    sample_seed         int|null  Seed used for sampling.
    raw_output          str|null  Raw LLM output text (null if no execution found).
    structured_output   any|null  Parsed structured output (null if unavailable).
    side_effects        list      Side effects produced by execution (empty list default).
    tokens_in           int|null  Input token count (null if no metrics).
    tokens_out          int|null  Output token count (null if no metrics).
    stop_reason         str|null  LLM stop reason (e.g. "end_turn", "max_tokens").
    latency_ms          float|null  Execution wall-clock latency in milliseconds.
    evaluation_outcome  str|null  Outcome from evaluation ledger for this decision
                                  (null if no evaluation event exists).
    run_config_version  str|null  Run config version from the most recent run.completed
                                  event for this agent (provenance tracking).
    wall_time           str       ISO timestamp of the decision event.

Nullable fields: snapshot_id, sub_action, sample_seed, raw_output,
structured_output, tokens_in, tokens_out, stop_reason, latency_ms,
evaluation_outcome, run_config_version. These are null when the corresponding
execution or evaluation event is missing.

Relationship to ledger events:
    - Each row maps to one ``agent.decision.taken`` event in ``public.jsonl``.
    - Execution data comes from the ``action.executed`` event whose
      ``payload.decision_event_id`` matches.
    - Evaluation outcomes come from ``evaluation.jsonl`` events whose
      ``payload.source_event_id`` matches the decision's ``event_id``.
    - ``run_config_version`` is extracted from the latest ``run.completed``
      event for the same agent.
"""
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


def build_trajectories(
    events: list[dict],
    ecosystem_id: str,
    evaluation_events: list[dict] | None = None,
) -> list[dict]:
    by_agent: dict[str, list[dict]] = {}
    for event in events:
        if event.get("ecosystem_id") != ecosystem_id:
            continue
        agent_id = event.get("agent_id")
        if not agent_id:
            continue
        by_agent.setdefault(agent_id, []).append(event)

    eval_by_decision: dict[str, str] = {}
    if evaluation_events:
        for ev in evaluation_events:
            payload = ev.get("payload", {})
            source_id = payload.get("source_event_id")
            outcome = payload.get("outcome")
            if source_id and outcome:
                eval_by_decision[source_id] = outcome

    trajectories: list[dict] = []
    for agent_id, agent_events in by_agent.items():
        decision_events = sorted(
            [e for e in agent_events if e.get("event_type") == "agent.decision.taken"],
            key=lambda e: e.get("wall_time", ""),
        )
        execution_by_decision = {
            e.get("payload", {}).get("decision_event_id"): e
            for e in agent_events
            if e.get("event_type") == "action.executed"
        }

        run_config_version: str | None = None
        for e in agent_events:
            if e.get("event_type") == "run.completed":
                rcv = (e.get("payload") or {}).get("run_config_version")
                if rcv:
                    run_config_version = rcv

        for decision_number, decision in enumerate(decision_events):
            decision_event_id = decision.get("event_id")
            payload = decision.get("payload", {})
            execution = execution_by_decision.get(decision_event_id)
            exec_payload = execution.get("payload", {}) if execution else {}
            metrics = exec_payload.get("metrics", {}) if isinstance(exec_payload, dict) else {}

            latency_ms: float | None = None
            wall_start = metrics.get("wall_start_ms")
            wall_end = metrics.get("wall_end_ms")
            if wall_start is not None and wall_end is not None:
                try:
                    latency_ms = float(wall_end) - float(wall_start)
                except (TypeError, ValueError):
                    pass

            trajectories.append(
                {
                    "ecosystem_id": ecosystem_id,
                    "agent_id": agent_id,
                    "decision_event_id": decision_event_id,
                    "decision_number": decision_number,
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
                    "latency_ms": latency_ms,
                    "evaluation_outcome": eval_by_decision.get(decision_event_id),
                    "run_config_version": run_config_version,
                    "wall_time": decision.get("wall_time"),
                }
            )
    return trajectories


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export decision trajectories for offline training.",
        epilog="Output format: JSONL (one JSON object per line). "
        "Compatible with HuggingFace datasets.load_dataset('json', ...).",
    )
    parser.add_argument("--ecosystem", required=True, help="Ecosystem id, e.g. alpha or beta")
    parser.add_argument("--base-dir", default=".", help="Repository base directory")
    parser.add_argument("--output", required=True, help="Output JSONL file path")
    parser.add_argument(
        "--format",
        default="jsonl",
        choices=["jsonl"],
        help="Output format (default: jsonl). JSONL is the only supported format.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    public_path = base_dir / "ecosystems" / args.ecosystem / "public.jsonl"
    eval_path = base_dir / "ecosystems" / args.ecosystem / "evaluation.jsonl"

    events = load_jsonl(public_path)
    evaluation_events = load_jsonl(eval_path)
    trajectories = build_trajectories(events, args.ecosystem, evaluation_events)

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
