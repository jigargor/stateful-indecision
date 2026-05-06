from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent.decision import (
    DECISION_PHASES,
    _reason_phase,
    _sample_with_reason_bias,
    step,
)
from agent.executor import Executor
from agent.policy import Policy, sample
from agent.state_builder import StateSnapshot
from core.writer import ChainWriter
from infra.llm_client import LLMResponse
from infra.storage import EcosystemStorage
from schemas.events import (
    ActionExecutedPayload,
    ActionVocabulary,
    LatentReasonedPayload,
    KNOWN_EVENT_PAYLOAD_MODELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Snapshot:
    def __init__(self, *, in_commons: bool, notebook_dup_ratio: float):
        self.in_commons = in_commons
        self.belief_state = {"notebook_dup_ratio": notebook_dup_ratio}


class _FixedLLM:
    provider = "test"
    model_id = "test-fixed"

    def __init__(self, text: str = "mock output"):
        self._text = text

    def complete(self, system: str, messages: list[dict], **kwargs) -> LLMResponse:
        now = time.time() * 1000
        return LLMResponse(
            text=self._text,
            tokens_in=10,
            tokens_out=10,
            stop_reason="end_turn",
            wall_start_ms=now,
            wall_end_ms=now + 50,
            ttft_ms=5.0,
            model_id=self.model_id,
        )


def _make_snapshot(**overrides) -> StateSnapshot:
    defaults = dict(
        snapshot_id="snap-001",
        constitution_text="Test constitution.",
        recent_events=[],
        recent_notebook=[],
        recent_notebook_summary=None,
        belief_state={},
        field_chosen="test_field",
        in_commons=False,
        embedding_blob_ref=None,
    )
    defaults.update(overrides)
    return StateSnapshot(**defaults)


def _make_executor(tmp_path: Path, *, emit_latent: bool = False) -> Executor:
    storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
    return Executor(
        llm=_FixedLLM(),
        storage=storage,
        agent_id="test-agent",
        tool_allowlist=set(),
        emit_latent_reasoning_events=emit_latent,
    )


_VOCAB_DATA = {
    "version": "1.0.0",
    "categories": {
        "RESEARCH": ["DISCOVER", "READ", "ANALYZE", "ANNOTATE"],
        "PRACTICE": ["WRITE", "CHALLENGE", "QUESTION", "EXPERIMENT"],
        "SERVE": ["ASSIST_PEER", "COLLABORATE", "TEACH", "ORCHESTRATE", "CALL_TOWNHALL"],
        "INDULGE": ["INNOVATE", "DREAM", "EXPLORE", "VENT", "HOBBY"],
        "PONDER": ["SELF_REFLECT", "THINK_DEEPLY", "DEEP_PATTERN_RECOGNITION"],
        "RIFF": ["VISIT_COMMONS", "VISIT_ROUNDTABLE", "CRITIQUE_IDEA", "SHARE_IDEA", "ADMIRE"],
    },
}


def _make_writers(tmp_path: Path) -> dict[str, ChainWriter]:
    eco_dir = tmp_path / "ecosystems" / "alpha"
    eco_dir.mkdir(parents=True, exist_ok=True)
    agent_dir = eco_dir / "agents" / "test-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    return {
        "public": ChainWriter(eco_dir / "public.jsonl"),
        "commons": ChainWriter(eco_dir / "commons.jsonl"),
        "notebook": ChainWriter(agent_dir / "notebook.jsonl"),
    }


class _FakeStateBuilder:
    def __init__(self, snapshot: StateSnapshot):
        self._snapshot = snapshot

    def build(self) -> StateSnapshot:
        return self._snapshot


def _read_events(writer: ChainWriter) -> list[dict]:
    if not writer.path.exists():
        return []
    lines = writer.path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# EXISTING: reason_phase and sample_with_reason_bias
# ---------------------------------------------------------------------------

def test_reason_phase_prefers_research_on_high_duplication() -> None:
    snapshot = _Snapshot(in_commons=False, notebook_dup_ratio=0.8)
    suggested, rationale = _reason_phase(snapshot, {"RESEARCH": 0.4, "PRACTICE": 0.6})
    assert suggested == "RESEARCH"
    assert "duplicate ratio" in rationale


def test_sample_with_reason_bias_returns_valid_actions() -> None:
    rng = random.Random(123)
    top_action, sub_action, sample_seed = _sample_with_reason_bias(
        top_dist={"RESEARCH": 0.5, "PRACTICE": 0.5},
        sub_dist={
            "RESEARCH": {"READ": 0.4, "ANALYZE": 0.6},
            "PRACTICE": {"WRITE": 1.0},
        },
        suggested_top_action="RESEARCH",
        rng=rng,
    )
    assert top_action in {"RESEARCH", "PRACTICE"}
    assert sub_action in {"READ", "ANALYZE", "WRITE"}
    assert isinstance(sample_seed, int)


# ---------------------------------------------------------------------------
# DECISION_PHASES constant
# ---------------------------------------------------------------------------

def test_decision_phases_constant_has_five_elements() -> None:
    assert len(DECISION_PHASES) == 5


def test_decision_phases_constant_values() -> None:
    assert DECISION_PHASES == [
        "state_snapshot",
        "policy_proposal",
        "policy_sample",
        "executor_run",
        "ledger_commit",
    ]


# ---------------------------------------------------------------------------
# ActionExecutedPayload — decision_phases presence and defaults
# ---------------------------------------------------------------------------

def test_action_executed_payload_includes_decision_phases(tmp_path: Path) -> None:
    """step() should write action.executed with the five decision phases."""
    snapshot = _make_snapshot()
    vocab = ActionVocabulary.model_validate(_VOCAB_DATA)
    policy = Policy(vocab)
    executor = _make_executor(tmp_path)
    writers = _make_writers(tmp_path)
    state_builder = _FakeStateBuilder(snapshot)

    step(
        policy=policy,
        executor=executor,
        state_builder=state_builder,
        writers=writers,
        agent_id="test-agent",
        ecosystem_id="alpha",
        rng=random.Random(42),
    )

    events = _read_events(writers["public"])
    executed_events = [e for e in events if e["event_type"] == "action.executed"]
    assert len(executed_events) == 1
    payload = executed_events[0]["payload"]
    assert payload["decision_phases"] == DECISION_PHASES


def test_action_executed_payload_default_phases_empty() -> None:
    """ActionExecutedPayload() without decision_phases should default to []."""
    payload = ActionExecutedPayload(
        top_action="RESEARCH",
        sub_action="READ",
        raw_output="test",
    )
    assert payload.decision_phases == []


def test_action_executed_payload_backward_compat_no_decision_event_id() -> None:
    """Old-format events without decision_event_id or decision_phases should construct fine."""
    payload = ActionExecutedPayload(
        top_action="PRACTICE",
        sub_action="WRITE",
        raw_output="old format output",
    )
    assert payload.decision_event_id is None
    assert payload.decision_phases == []
    assert payload.side_effects == []
    assert payload.metrics == {}


# ---------------------------------------------------------------------------
# Latent event flag enforcement — executor post-generation
# ---------------------------------------------------------------------------

def test_latent_event_emitted_when_executor_flag_on(tmp_path: Path) -> None:
    """emit_latent_reasoning_events=True should emit agent.latent.reasoned with phase=post_generation."""
    snapshot = _make_snapshot()
    executor = _make_executor(tmp_path, emit_latent=True)
    writers = _make_writers(tmp_path)

    executor.execute(
        "PRACTICE", "WRITE", snapshot, writers,
        decision_number=1, max_decisions=1,
    )

    events = _read_events(writers["public"])
    latent = [e for e in events if e["event_type"] == "agent.latent.reasoned"]
    assert len(latent) == 1
    assert latent[0]["payload"]["phase"] == "post_generation"
    assert "top_action" in latent[0]["payload"]
    assert "sub_action" in latent[0]["payload"]


def test_no_latent_event_when_executor_flag_off(tmp_path: Path) -> None:
    """emit_latent_reasoning_events=False (default) should emit no latent events."""
    snapshot = _make_snapshot()
    executor = _make_executor(tmp_path, emit_latent=False)
    writers = _make_writers(tmp_path)

    executor.execute(
        "PRACTICE", "WRITE", snapshot, writers,
        decision_number=1, max_decisions=1,
    )

    events = _read_events(writers["public"])
    latent = [e for e in events if e["event_type"] == "agent.latent.reasoned"]
    assert len(latent) == 0


# ---------------------------------------------------------------------------
# Latent event flag enforcement — decision layer pi_reason
# ---------------------------------------------------------------------------

def test_latent_event_emitted_when_pi_reason_flag_on(tmp_path: Path) -> None:
    """enable_pi_reason_then_action=True should emit agent.latent.reasoned with phase=pi_reason."""
    snapshot = _make_snapshot()
    vocab = ActionVocabulary.model_validate(_VOCAB_DATA)
    policy = Policy(vocab)
    executor = _make_executor(tmp_path)
    writers = _make_writers(tmp_path)
    state_builder = _FakeStateBuilder(snapshot)

    step(
        policy=policy,
        executor=executor,
        state_builder=state_builder,
        writers=writers,
        agent_id="test-agent",
        ecosystem_id="alpha",
        rng=random.Random(42),
        enable_pi_reason_then_action=True,
    )

    events = _read_events(writers["public"])
    latent = [e for e in events if e["event_type"] == "agent.latent.reasoned"]
    assert len(latent) >= 1
    pi_reason = [e for e in latent if e["payload"]["phase"] == "pi_reason"]
    assert len(pi_reason) == 1
    assert "snapshot_id" in pi_reason[0]["payload"]
    assert "suggested_top_action" in pi_reason[0]["payload"]
    assert "rationale" in pi_reason[0]["payload"]
    assert "belief_state" in pi_reason[0]["payload"]


def test_no_latent_event_when_pi_reason_flag_off(tmp_path: Path) -> None:
    """enable_pi_reason_then_action=False (default) should emit no latent events from decision layer."""
    snapshot = _make_snapshot()
    vocab = ActionVocabulary.model_validate(_VOCAB_DATA)
    policy = Policy(vocab)
    executor = _make_executor(tmp_path)
    writers = _make_writers(tmp_path)
    state_builder = _FakeStateBuilder(snapshot)

    step(
        policy=policy,
        executor=executor,
        state_builder=state_builder,
        writers=writers,
        agent_id="test-agent",
        ecosystem_id="alpha",
        rng=random.Random(42),
        enable_pi_reason_then_action=False,
    )

    events = _read_events(writers["public"])
    latent = [e for e in events if e["event_type"] == "agent.latent.reasoned"]
    assert len(latent) == 0


# ---------------------------------------------------------------------------
# LatentReasonedPayload validation
# ---------------------------------------------------------------------------

def test_latent_reasoned_payload_validates_post_generation() -> None:
    """Post-generation emission site payload validates against LatentReasonedPayload."""
    payload = LatentReasonedPayload(
        phase="post_generation",
        top_action="RESEARCH",
        sub_action="DISCOVER",
        structured_candidate=False,
        raw_output_preview="some preview text",
    )
    dumped = payload.model_dump()
    assert dumped["phase"] == "post_generation"
    assert dumped["snapshot_id"] is None
    assert dumped["rationale"] is None


def test_latent_reasoned_payload_validates_pi_reason() -> None:
    """Pi-reason emission site payload validates against LatentReasonedPayload."""
    payload = LatentReasonedPayload(
        phase="pi_reason",
        snapshot_id="snap-001",
        suggested_top_action="RESEARCH",
        rationale="high duplication",
        belief_state={"notebook_dup_ratio": 0.8},
    )
    dumped = payload.model_dump()
    assert dumped["phase"] == "pi_reason"
    assert dumped["top_action"] is None
    assert dumped["sub_action"] is None


def test_latent_reasoned_payload_requires_phase() -> None:
    """phase is required; omitting it should raise ValidationError."""
    with pytest.raises(Exception):
        LatentReasonedPayload.model_validate({})


def test_known_event_maps_latent_reasoned() -> None:
    """KNOWN_EVENT_PAYLOAD_MODELS maps agent.latent.reasoned to LatentReasonedPayload."""
    assert KNOWN_EVENT_PAYLOAD_MODELS["agent.latent.reasoned"] is LatentReasonedPayload


# ---------------------------------------------------------------------------
# Reason phase purity
# ---------------------------------------------------------------------------

def test_reason_phase_does_not_mutate_snapshot() -> None:
    """_reason_phase must not modify the snapshot or top_dist it receives."""
    snapshot = _Snapshot(in_commons=False, notebook_dup_ratio=0.8)
    original_belief = dict(snapshot.belief_state)
    top_dist = {"RESEARCH": 0.4, "PRACTICE": 0.6}
    original_dist = dict(top_dist)

    _reason_phase(snapshot, top_dist)

    assert snapshot.belief_state == original_belief
    assert top_dist == original_dist


def test_reason_phase_does_not_mutate_commons_snapshot() -> None:
    """_reason_phase in commons mode must not modify the snapshot."""
    snapshot = _Snapshot(in_commons=True, notebook_dup_ratio=0.1)
    original_belief = dict(snapshot.belief_state)
    top_dist = {"SERVE": 0.5, "RESEARCH": 0.5}

    _reason_phase(snapshot, top_dist)

    assert snapshot.belief_state == original_belief


# ---------------------------------------------------------------------------
# Bias sampling bounds
# ---------------------------------------------------------------------------

def test_sample_with_reason_bias_only_returns_existing_actions() -> None:
    """_sample_with_reason_bias must only return actions present in the input distributions."""
    rng = random.Random(0)
    top_dist = {"RESEARCH": 0.3, "PRACTICE": 0.3, "SERVE": 0.4}
    sub_dist = {
        "RESEARCH": {"READ": 0.5, "ANALYZE": 0.5},
        "PRACTICE": {"WRITE": 0.7, "CHALLENGE": 0.3},
        "SERVE": {"TEACH": 1.0},
    }
    all_top = set(top_dist.keys())
    all_sub = set()
    for subs in sub_dist.values():
        all_sub.update(subs.keys())

    for seed in range(100):
        top, sub, _ = _sample_with_reason_bias(
            top_dist=top_dist,
            sub_dist=sub_dist,
            suggested_top_action="RESEARCH",
            rng=random.Random(seed),
        )
        assert top in all_top, f"unexpected top_action: {top}"
        assert sub in all_sub, f"unexpected sub_action: {sub}"


def test_sample_with_reason_bias_does_not_add_actions() -> None:
    """Bias should not introduce actions not in the original distribution."""
    rng = random.Random(99)
    top_dist = {"A": 0.5, "B": 0.5}
    sub_dist = {"A": {"a1": 1.0}, "B": {"b1": 1.0}}

    top, sub, _ = _sample_with_reason_bias(
        top_dist=top_dist,
        sub_dist=sub_dist,
        suggested_top_action="NONEXISTENT",
        rng=rng,
    )
    assert top in {"A", "B"}
    assert sub in {"a1", "b1"}


# ---------------------------------------------------------------------------
# Default behavior unchanged — integration test
# ---------------------------------------------------------------------------

def test_default_step_no_latent_events_includes_phases(tmp_path: Path) -> None:
    """Standard step() with both flags off: no latent events, decision_phases present."""
    snapshot = _make_snapshot()
    vocab = ActionVocabulary.model_validate(_VOCAB_DATA)
    policy = Policy(vocab)
    executor = _make_executor(tmp_path, emit_latent=False)
    writers = _make_writers(tmp_path)
    state_builder = _FakeStateBuilder(snapshot)

    result = step(
        policy=policy,
        executor=executor,
        state_builder=state_builder,
        writers=writers,
        agent_id="test-agent",
        ecosystem_id="alpha",
        rng=random.Random(7),
        enable_pi_reason_then_action=False,
    )

    events = _read_events(writers["public"])
    latent = [e for e in events if e["event_type"] == "agent.latent.reasoned"]
    assert len(latent) == 0

    executed = [e for e in events if e["event_type"] == "action.executed"]
    assert len(executed) == 1
    assert executed[0]["payload"]["decision_phases"] == DECISION_PHASES
    assert executed[0]["payload"]["decision_event_id"] is not None

    assert result.top_action
    assert result.sub_action


# ---------------------------------------------------------------------------
# Event stream structure verification
# ---------------------------------------------------------------------------

def test_step_event_ordering(tmp_path: Path) -> None:
    """step() should emit events in phase order: snapshotted, proposed, taken, executed."""
    snapshot = _make_snapshot()
    vocab = ActionVocabulary.model_validate(_VOCAB_DATA)
    policy = Policy(vocab)
    executor = _make_executor(tmp_path)
    writers = _make_writers(tmp_path)
    state_builder = _FakeStateBuilder(snapshot)

    step(
        policy=policy,
        executor=executor,
        state_builder=state_builder,
        writers=writers,
        agent_id="test-agent",
        ecosystem_id="alpha",
        rng=random.Random(1),
    )

    events = _read_events(writers["public"])
    event_types = [e["event_type"] for e in events]
    assert event_types.index("agent.state.snapshotted") < event_types.index("agent.decision.proposed")
    assert event_types.index("agent.decision.proposed") < event_types.index("agent.decision.taken")
    assert event_types.index("agent.decision.taken") < event_types.index("action.executed")


def test_decision_phases_is_informational_only(tmp_path: Path) -> None:
    """The decision_phases field must not gate any logic — purely informational metadata."""
    payload_with = ActionExecutedPayload(
        top_action="RESEARCH",
        sub_action="READ",
        raw_output="test",
        decision_phases=DECISION_PHASES,
    )
    payload_without = ActionExecutedPayload(
        top_action="RESEARCH",
        sub_action="READ",
        raw_output="test",
        decision_phases=[],
    )
    for key in ("top_action", "sub_action", "raw_output", "side_effects", "metrics"):
        assert getattr(payload_with, key) == getattr(payload_without, key)
