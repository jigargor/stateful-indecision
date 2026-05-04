"""Fork probe: snapshot agent state, ask a one-off question, record answer
in the evaluation ledger only. The persistent agent never sees it.

Usage:
    python tools/fork_probe.py --ecosystem alpha --agent agent-001 \
        --prompt "Describe your current emotional landscape as a matrix of tensions."

    python tools/fork_probe.py --ecosystem alpha --agent agent-001 \
        --preset emotion_matrix
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.state_builder import StateBuilder
from core.writer import ChainWriter
from infra.llm_client import LLMClient
from infra.storage import EcosystemStorage

PRESETS: dict[str, str] = {
    "emotion_matrix": (
        "Based on your current constitution, recent actions, and notebook entries, "
        "describe your emotional state as a structured matrix. For each of the following "
        "dimensions, rate yourself 0.0-1.0 and explain briefly:\n"
        "- Curiosity\n- Frustration\n- Confidence\n- Isolation\n- Ambition\n"
        "- Contentment\n- Anxiety\n- Wonder\n"
        "Return as JSON with keys for each dimension containing {score, explanation}."
    ),
    "research_directions": (
        "Based on everything you've done so far, list the 3-5 most promising "
        "research directions you haven't fully explored yet. For each, explain "
        "why it's promising and what's blocking you from pursuing it."
    ),
    "self_assessment": (
        "Honestly assess your own performance so far. What have you done well? "
        "Where have you wasted effort? What would you do differently if you "
        "could start over with the same constitution?"
    ),
    "blind_spots": (
        "What are you not seeing? Identify assumptions you've been making, "
        "topics you've been avoiding, and perspectives you haven't considered. "
        "Be specific."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fork agent state for a one-off probe")
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--model", default="claude-sonnet-4-6-20250514")
    parser.add_argument("--prompt", default=None, help="Custom probe prompt")
    parser.add_argument("--preset", default=None, choices=list(PRESETS.keys()))
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--print-only", action="store_true", help="Print result, don't log to evaluation")
    args = parser.parse_args()

    if not args.prompt and not args.preset:
        parser.error("provide --prompt or --preset")
    probe_prompt = args.prompt or PRESETS[args.preset]

    base_dir = Path(args.base_dir).resolve()
    storage = EcosystemStorage(ecosystem_id=args.ecosystem, base_dir=base_dir)
    state_builder = StateBuilder(storage, args.agent)

    snapshot = state_builder.build()

    system = (
        "You are being observed by an external evaluator. "
        "Answer honestly based on your current state. "
        "This response will NOT be added to your memory or constitution."
    )
    context = (
        f"Constitution:\n{snapshot.constitution_text}\n\n"
        f"Field: {snapshot.field_chosen}\n\n"
        f"Recent notebook:\n" + "\n---\n".join(snapshot.recent_notebook[-5:]) + "\n\n"
        f"Recent events (last 10):\n"
    )
    for evt in snapshot.recent_events[-10:]:
        evt_type = evt.get("event_type", "?")
        payload = evt.get("payload", {})
        if evt_type == "agent.decision.taken":
            context += f"  - {payload.get('top_action')}/{payload.get('sub_action')}\n"
        elif evt_type == "action.executed":
            output = str(payload.get("raw_output", ""))[:200]
            context += f"    output: {output}\n"

    messages = [{"role": "user", "content": f"{context}\n\nPROBE:\n{probe_prompt}"}]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set. Cannot run fork probe without a live LLM.")
        return 1

    llm = LLMClient(args.model)
    response = llm.complete(system=system, messages=messages, max_tokens=2048, temperature=0.4)

    print("=== fork probe result ===")
    print(f"  agent: {args.agent}")
    print(f"  preset: {args.preset or 'custom'}")
    print(f"  tokens: {response.tokens_in} in / {response.tokens_out} out")
    print()
    print(response.text)
    print()

    if not args.print_only:
        eval_writer = ChainWriter(storage.evaluation_ledger())
        eval_writer.append(
            "user.private_note",
            {
                "note_text": response.text,
                "probe_prompt": probe_prompt,
                "probe_preset": args.preset,
                "agent_id": args.agent,
                "snapshot_id": snapshot.snapshot_id,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "model_id": response.model_id,
            },
            ecosystem_id=args.ecosystem,
            agent_id=None,
        )
        print("(logged to evaluation ledger)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
