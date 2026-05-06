from __future__ import annotations

import random
from dataclasses import dataclass

from agent.executor import Executor
from agent.policy import Policy, sample
from agent.state_builder import StateBuilder
from core.writer import ChainWriter
from schemas.events import (
    ActionExecutedPayload,
    AgentStateSnapshottedPayload,
    DecisionProposedPayload,
    DecisionTakenPayload,
)

DECISION_PHASES: list[str] = [
    "state_snapshot",
    "policy_proposal",
    "policy_sample",
    "executor_run",
    "ledger_commit",
]


@dataclass
class StepResult:
    top_action: str
    sub_action: str
    raw_output: str
    side_effects: list[str]
    tokens_in: int
    tokens_out: int
    latency_ms: float


def _sample_with_reason_bias(
    *,
    top_dist: dict[str, float],
    sub_dist: dict[str, dict[str, float]],
    suggested_top_action: str,
    rng: random.Random,
) -> tuple[str, str, int]:
    sample_seed = rng.getrandbits(64)
    local_rng = random.Random(sample_seed)
    biased = dict(top_dist)
    if suggested_top_action in biased:
        biased[suggested_top_action] *= 1.5
    total = sum(biased.values()) or 1.0
    normalized = {k: v / total for k, v in biased.items()}
    top_actions = list(normalized.keys())
    top_weights = list(normalized.values())
    top_action = local_rng.choices(top_actions, weights=top_weights, k=1)[0]
    sub_actions = list(sub_dist[top_action].keys())
    sub_weights = list(sub_dist[top_action].values())
    sub_action = local_rng.choices(sub_actions, weights=sub_weights, k=1)[0]
    return top_action, sub_action, sample_seed


def _reason_phase(snapshot, top_dist: dict[str, float]) -> tuple[str, str]:
    suggested_top_action = max(top_dist, key=top_dist.get)
    if snapshot.belief_state.get("notebook_dup_ratio", 0.0) > 0.4:
        suggested_top_action = "RESEARCH" if "RESEARCH" in top_dist else suggested_top_action
        rationale = "high notebook duplicate ratio suggests outward exploration"
    elif snapshot.in_commons:
        suggested_top_action = "SERVE" if "SERVE" in top_dist else suggested_top_action
        rationale = "in-commons context suggests contribution-oriented action"
    else:
        rationale = "distribution-max prior from current belief state"
    return suggested_top_action, rationale


def step(
    *,
    policy: Policy,
    executor: Executor,
    state_builder: StateBuilder,
    writers: dict[str, ChainWriter],
    agent_id: str,
    ecosystem_id: str,
    rng: random.Random,
    enable_pi_reason_then_action: bool = False,
    decision_number: int = 1,
    max_decisions: int = 100,
) -> StepResult:
    """Execute one decision step through five sequential phases (see DECISION_PHASES):

    1. state_snapshot  — StateBuilder.build() → agent.state.snapshotted event.
    2. policy_proposal — Policy.propose(snapshot) → builds action distributions
       (no ledger event emitted in this phase).
    3. policy_sample   — sample(dist, rng) (or biased variant when
       enable_pi_reason_then_action is True) selects top/sub action, then
       BOTH agent.decision.proposed and agent.decision.taken events are
       appended to the ledger.
    4. executor_run    — Executor.execute(...) → side effects + raw output.
    5. ledger_commit   — action.executed event with phase metadata.
    """
    snapshot = state_builder.build()
    snapshot_payload = AgentStateSnapshottedPayload(
        snapshot_id=snapshot.snapshot_id,
        field_chosen=snapshot.field_chosen,
        in_commons=snapshot.in_commons,
        recent_event_count=len(snapshot.recent_events),
        recent_notebook_count=len(snapshot.recent_notebook),
        embedding_blob_ref=snapshot.embedding_blob_ref,
        belief_state=snapshot.belief_state,
    ).model_dump()
    writers["public"].append(
        "agent.state.snapshotted",
        snapshot_payload,
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )

    dist = policy.propose(snapshot)
    if enable_pi_reason_then_action:
        suggested_top_action, rationale = _reason_phase(snapshot, dist.top_dist)
        writers["public"].append(
            "agent.latent.reasoned",
            {
                "phase": "pi_reason",
                "snapshot_id": snapshot.snapshot_id,
                "suggested_top_action": suggested_top_action,
                "rationale": rationale,
                "belief_state": snapshot.belief_state,
            },
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
        )
        top_action, sub_action, sample_seed = _sample_with_reason_bias(
            top_dist=dist.top_dist,
            sub_dist=dist.sub_dist,
            suggested_top_action=suggested_top_action,
            rng=rng,
        )
    else:
        top_action, sub_action, sample_seed = sample(dist, rng)
    decision_proposed_payload = DecisionProposedPayload(
        snapshot_id=snapshot.snapshot_id,
        top_dist=dist.top_dist,
        sub_dist=dist.sub_dist,
        sample_seed=sample_seed,
    ).model_dump()
    writers["public"].append(
        "agent.decision.proposed",
        {**decision_proposed_payload, "leaf_category_weights": dist.leaf_category_weights},
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    decision_taken_payload = DecisionTakenPayload(
        snapshot_id=snapshot.snapshot_id,
        top_action=top_action,
        sub_action=sub_action,
        sample_seed=sample_seed,
    ).model_dump()
    taken_event = writers["public"].append(
        "agent.decision.taken",
        decision_taken_payload,
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    result = executor.execute(
        top_action,
        sub_action,
        snapshot,
        writers,
        decision_number=decision_number,
        max_decisions=max_decisions,
    )
    metrics = result.llm_response
    action_executed_payload = ActionExecutedPayload(
        top_action=top_action,
        sub_action=sub_action,
        raw_output=result.raw_output,
        structured=result.structured,
        side_effects=result.side_effects,
        metrics={
            "tokens_in": metrics.tokens_in,
            "tokens_out": metrics.tokens_out,
            "stop_reason": metrics.stop_reason,
            "wall_start_ms": metrics.wall_start_ms,
            "wall_end_ms": metrics.wall_end_ms,
            "ttft_ms": metrics.ttft_ms,
            "model_id": metrics.model_id,
        },
    ).model_dump()
    writers["public"].append(
        "action.executed",
        {
            **action_executed_payload,
            "decision_event_id": taken_event.event_id,
            "decision_phases": list(DECISION_PHASES),
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
