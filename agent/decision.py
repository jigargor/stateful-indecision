from __future__ import annotations

import random
from dataclasses import dataclass

from agent.executor import Executor
from agent.policy import Policy, sample
from agent.state_builder import StateBuilder
from core.writer import ChainWriter


@dataclass
class StepResult:
    top_action: str
    sub_action: str
    raw_output: str
    side_effects: list[str]
    tokens_in: int
    tokens_out: int
    latency_ms: float


def step(
    *,
    policy: Policy,
    executor: Executor,
    state_builder: StateBuilder,
    writers: dict[str, ChainWriter],
    agent_id: str,
    ecosystem_id: str,
    rng: random.Random,
) -> StepResult:
    snapshot = state_builder.build()
    writers["public"].append(
        "agent.state.snapshotted",
        {
            "snapshot_id": snapshot.snapshot_id,
            "field_chosen": snapshot.field_chosen,
            "in_commons": snapshot.in_commons,
            "recent_event_count": len(snapshot.recent_events),
            "recent_notebook_count": len(snapshot.recent_notebook),
            "embedding_blob_ref": snapshot.embedding_blob_ref,
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )

    dist = policy.propose(snapshot)
    top_action, sub_action, sample_seed = sample(dist, rng)
    writers["public"].append(
        "agent.decision.proposed",
        {
            "snapshot_id": snapshot.snapshot_id,
            "top_dist": dist.top_dist,
            "sub_dist": dist.sub_dist,
            "leaf_category_weights": dist.leaf_category_weights,
            "sample_seed": sample_seed,
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    taken_event = writers["public"].append(
        "agent.decision.taken",
        {
            "snapshot_id": snapshot.snapshot_id,
            "top_action": top_action,
            "sub_action": sub_action,
            "sample_seed": sample_seed,
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    result = executor.execute(top_action, sub_action, snapshot, writers)
    metrics = result.llm_response
    writers["public"].append(
        "action.executed",
        {
            "decision_event_id": taken_event.event_id,
            "top_action": top_action,
            "sub_action": sub_action,
            "raw_output": result.raw_output,
            "structured": result.structured,
            "side_effects": result.side_effects,
            "metrics": {
                "tokens_in": metrics.tokens_in,
                "tokens_out": metrics.tokens_out,
                "stop_reason": metrics.stop_reason,
                "wall_start_ms": metrics.wall_start_ms,
                "wall_end_ms": metrics.wall_end_ms,
                "ttft_ms": metrics.ttft_ms,
                "model_id": metrics.model_id,
            },
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    return StepResult(
        top_action=top_action,
        sub_action=sub_action,
        raw_output=result.raw_output,
        side_effects=result.side_effects,
        tokens_in=metrics.tokens_in,
        tokens_out=metrics.tokens_out,
        latency_ms=metrics.wall_end_ms - metrics.wall_start_ms,
    )
