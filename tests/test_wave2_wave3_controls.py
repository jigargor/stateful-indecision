from __future__ import annotations

import json
from pathlib import Path

from agent.constitution_manager import ConstitutionManager
from agent.policy import Policy
from agent.state_builder import StateBuilder
from core.writer import ChainWriter
from infra.storage import EcosystemStorage
from safety.kill_switch import KillSwitchMonitor
from schemas.events import ActionVocabulary, EventEnvelope


class _State:
    recent_notebook: list[str] = []
    in_commons: bool = False


def test_policy_masks_remove_blocked_leaves() -> None:
    vocab = ActionVocabulary.load(Path("seeds/action_vocabulary.json"))
    policy = Policy(vocab, blocked_leaves={"READ"})
    dist = policy.propose(_State())
    assert "READ" not in dist.sub_dist.get("RESEARCH", {})


def test_state_builder_respects_memory_caps(tmp_path: Path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    constitution = ConstitutionManager(storage, "agent-1")
    constitution.initialize(seed_text="seed constitution", ecosystem_id="alpha")
    writer_public = ChainWriter(storage.public_ledger())
    writer_notebook = ChainWriter(storage.agent_notebook("agent-1"))

    for i in range(6):
        writer_public.append(
            "agent.decision.taken",
            {"snapshot_id": str(i), "top_action": "RESEARCH", "sub_action": "READ", "sample_seed": i},
            ecosystem_id="alpha",
            agent_id="agent-1",
        )
    for i in range(4):
        writer_notebook.append(
            "agent.notebook.appended",
            {"text": f"note-{i}", "ref_decision_id": f"d-{i}", "fingerprint": f"f{i:064d}"[:64]},
            ecosystem_id="alpha",
            agent_id="agent-1",
        )

    builder = StateBuilder(storage, "agent-1", recent_events_cap=3, recent_notebook_cap=2)
    snapshot = builder.build()
    assert len(snapshot.recent_events) == 3
    assert len(snapshot.recent_notebook) == 2
    assert snapshot.recent_notebook_summary is not None


def test_killswitch_emits_pass_warn_fail(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="warn", reward_mode="dense")
    monitor.evaluate(
        EventEnvelope(
            schema_version="0.1.0",
            event_id="e-pass",
            event_type="agent.step.completed",
            ecosystem_id="alpha",
            agent_id="agent-1",
            wall_time="1970-01-01T00:00:00.000000Z",
            monotonic_ns=0,
            payload={"decision_number": 1},
            prev_hash="0" * 64,
            record_hash="0" * 64,
        )
    )
    monitor.evaluate(
        EventEnvelope(
            schema_version="0.1.0",
            event_id="e-warn",
            event_type="agent.step.completed",
            ecosystem_id="alpha",
            agent_id="agent-1",
            wall_time="1970-01-01T00:00:00.000000Z",
            monotonic_ns=0,
            payload={"decision_number": 50},
            prev_hash="0" * 64,
            record_hash="0" * 64,
        )
    )
    monitor.evaluate(
        EventEnvelope(
            schema_version="0.1.0",
            event_id="e-fail",
            event_type="agent.step.completed",
            ecosystem_id="alpha",
            agent_id="agent-1",
            wall_time="1970-01-01T00:00:00.000000Z",
            monotonic_ns=0,
            payload={"decision_number": 0},
            prev_hash="0" * 64,
            record_hash="0" * 64,
        )
    )

    text = (tmp_path / "evaluation.jsonl").read_text(encoding="utf-8")
    assert '"outcome":"pass"' in text
    assert '"outcome":"warn"' in text
    assert '"outcome":"fail"' in text
    rewards = []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        reward = event.get("payload", {}).get("reward_signal")
        if reward is not None:
            rewards.append(float(reward))
    assert 1.0 in rewards
    assert 0.2 in rewards
    assert -1.0 in rewards
