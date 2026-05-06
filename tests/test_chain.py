from __future__ import annotations

import json

import pytest

from core.verifier import verify_chain
from core.writer import ChainWriter


def test_append_and_verify_chain(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    writer = ChainWriter(path)
    for i in range(3):
        writer.append("event.test", {"index": i}, ecosystem_id="alpha", agent_id="agent-001")
    result = verify_chain(path)
    assert result.valid is True
    assert result.total_events == 3


def test_corrupt_middle_event_fails(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    writer = ChainWriter(path)
    for i in range(3):
        writer.append("event.test", {"index": i}, ecosystem_id="alpha", agent_id="agent-001")

    lines = path.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["payload"]["index"] = 42
    lines[1] = json.dumps(middle, separators=(",", ":"), sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_chain(path)
    assert result.valid is False
    assert any(error.line_number == 2 for error in result.errors)


def test_swapped_events_fail_prev_hash(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    writer = ChainWriter(path)
    for i in range(3):
        writer.append("event.test", {"index": i}, ecosystem_id="alpha", agent_id="agent-001")
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_chain(path)
    assert result.valid is False
    assert any("prev_hash mismatch" in error.error for error in result.errors)


def test_empty_chain_is_valid(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    path.touch()
    result = verify_chain(path)
    assert result.valid is True
    assert result.total_events == 0


def test_genesis_prev_hash(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    writer = ChainWriter(path)
    writer.append("event.test", {"index": 0}, ecosystem_id="alpha", agent_id="agent-001")
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["prev_hash"] == "0" * 64


def test_known_payload_validation_rejects_invalid_shape(tmp_path) -> None:
    path = tmp_path / "chain.jsonl"
    writer = ChainWriter(path)
    with pytest.raises(ValueError):
        writer.append(
            "agent.decision.taken",
            {"snapshot_id": "snap-1", "top_action": "RESEARCH"},
            ecosystem_id="alpha",
            agent_id="agent-001",
        )
