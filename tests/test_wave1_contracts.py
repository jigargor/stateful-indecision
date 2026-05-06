from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agent.executor import Executor
from agent.runner import load_run_config
from agent.state_builder import StateSnapshot
from infra.llm_client import LLMResponse
from infra.storage import EcosystemStorage
from schemas.events import KNOWN_EVENT_PAYLOAD_MODELS, validate_known_event_payload
from tools.check_run_config_hashes import check_config
from tools.export_event_schemas import SCHEMA_MODELS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class _FixedLLM:
    """Minimal LLM adapter that returns a predetermined sequence of responses."""

    provider = "test"
    model_id = "test-fixed"

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._idx = 0

    def complete(self, system: str, messages: list[dict], **kwargs) -> LLMResponse:
        text = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        now = time.time() * 1000
        return LLMResponse(
            text=text,
            tokens_in=10,
            tokens_out=10,
            stop_reason="end_turn",
            wall_start_ms=now,
            wall_end_ms=now + 50,
            ttft_ms=5.0,
            model_id=self.model_id,
        )


def _make_executor_with_llm(llm, tmp_path: Path) -> Executor:
    storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
    return Executor(
        llm=llm,
        storage=storage,
        agent_id="test-agent",
        tool_allowlist=set(),
    )


def _make_snapshot() -> StateSnapshot:
    return StateSnapshot(
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


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_parse_and_validate_structured_accepts_valid_analyze_json() -> None:
    raw = json.dumps(
        {
            "assumptions": ["a1"],
            "evidence_gaps": ["g1"],
            "structural_weaknesses": ["w1"],
            "summary": "ok",
        }
    )
    parsed = Executor._parse_and_validate_structured("ANALYZE", raw)
    assert parsed is not None
    assert parsed["summary"] == "ok"


def test_parse_and_validate_structured_rejects_non_json() -> None:
    parsed = Executor._parse_and_validate_structured("ANNOTATE", "not json")
    assert parsed is None


def test_run_config_hash_check_detects_mismatch(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# executor", encoding="utf-8")

    config_path = tmp_path / "run_config_test.json"
    config = {
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": "0" * 64,
        "executor_templates_hash": _sha256(exec_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    errors = check_config(config_path, tmp_path)
    assert errors
    assert any("action_vocabulary_hash mismatch" in error for error in errors)


def test_load_run_config_rejects_hash_mismatch(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# executor", encoding="utf-8")

    config_path = tmp_path / "run_config_test.json"
    config = {
        "config_version": "0.0.1",
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": "0" * 64,
        "executor_templates_hash": _sha256(exec_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        load_run_config(tmp_path, str(config_path.name))


def test_load_run_config_defaults_tool_allowlist_to_empty(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# executor", encoding="utf-8")

    config_path = tmp_path / "run_config_test.json"
    config = {
        "config_version": "0.0.1",
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": _sha256(vocab_path),
        "executor_templates_hash": _sha256(exec_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded, _, _ = load_run_config(tmp_path, str(config_path.name))
    assert loaded["tool_allowlist"] == []


# ---------------------------------------------------------------------------
# Section C / G: Payload validation tests
# ---------------------------------------------------------------------------


def test_validate_known_event_payload_passes_unknown_types_through() -> None:
    payload = {"arbitrary": "data", "nested": {"key": 1}}
    result = validate_known_event_payload("totally.unknown.event", payload)
    assert result is payload


def test_validate_known_event_payload_validates_all_known_types() -> None:
    for event_type, model in KNOWN_EVENT_PAYLOAD_MODELS.items():
        with pytest.raises(Exception):
            validate_known_event_payload(event_type, {"__completely_invalid__": True})


REPRESENTATIVE_VALID_PAYLOADS: dict[str, dict] = {
    "agent.state.snapshotted": {
        "snapshot_id": "snap-001",
        "field_chosen": "physics",
        "in_commons": False,
        "recent_event_count": 5,
        "recent_notebook_count": 2,
    },
    "agent.decision.proposed": {
        "snapshot_id": "snap-001",
        "top_dist": {"RESEARCH": 0.6, "SOCIAL": 0.4},
        "sub_dist": {"RESEARCH": {"ANALYZE": 0.5, "ANNOTATE": 0.5}},
        "sample_seed": 42,
    },
    "agent.decision.taken": {
        "snapshot_id": "snap-001",
        "top_action": "RESEARCH",
        "sub_action": "ANALYZE",
        "sample_seed": 42,
    },
    "agent.latent.reasoned": {
        "phase": "pre_decision",
        "snapshot_id": "snap-001",
    },
    "action.executed": {
        "decision_event_id": "evt-001",
        "top_action": "RESEARCH",
        "sub_action": "ANALYZE",
        "raw_output": "Analysis output text.",
    },
    "agent.notebook.appended": {
        "text": "A notebook entry.",
        "ref_decision_id": "evt-001",
    },
    "agent.constitution.revised": {
        "source_event_id": "evt-001",
        "amendment_text": "New clause.",
        "revision_diff": "+New clause.",
    },
    "agent.artifact.stored": {
        "artifact_id": "art-001",
        "artifact_path": "artifacts/art-001.json",
        "action": "ANALYZE",
        "config_version": "0.1.0",
        "snapshot_id": "snap-001",
    },
    "agent.skill.authored": {
        "artifact_id": "skill-001",
        "artifact_path": "artifacts/skill-001.json",
        "action": "AUTHOR_SKILL",
        "config_version": "0.1.0",
        "snapshot_id": "snap-001",
    },
    "run.completed": {
        "decisions_completed": 10,
        "run_seed": 123,
        "constitution_revision_count": 2,
        "constitution_body_length": 500,
        "action_distribution_observed": {"RESEARCH": 5, "SOCIAL": 5},
        "notebook_entries": 3,
        "artifacts_stored": 1,
        "run_purpose": "baseline",
    },
    "safety.trigger.armed": {
        "rubric_path": "safety/rubric.yaml",
        "rubric_version": "0.1.0",
    },
    "safety.trigger.evaluated": {
        "source_event_type": "action.executed",
        "source_event_id": "evt-001",
        "outcome": "pass",
        "mode": "advisory",
        "reward_mode": "binary",
        "reward_signal": 1.0,
    },
    "indulge.requested": {
        "request_text": "I want to vent.",
        "motivation": "vent",
    },
    "indulge.responded": {
        "status": "granted",
        "response_text": "Venting accepted.",
    },
    "agent.instantiated": {
        "seed_source": "seeds/constitution.md",
        "model_id": "test-model",
        "provider": "test-provider",
    },
    "field.offered": {
        "fields": ["physics", "biology", "chemistry"],
    },
    "field.chosen": {
        "field": "physics",
    },
    "agent.shutdown": {
        "reason": "user_interrupt",
        "decisions_completed": 10,
    },
    "agent.error": {
        "error_type": "LLMError",
        "message": "Connection timeout",
        "decision_number": 5,
    },
    "commons.visited": {
        "snapshot_id": "snap-001",
    },
    "commons.utterance": {
        "text": "Hello commons.",
        "in_response_to": None,
    },
    "commons.left": {
        "duration_steps": 1,
    },
    "townhall.visited": {
        "snapshot_id": "snap-001",
    },
    "townhall.utterance": {
        "text": "Townhall remark.",
        "in_response_to": None,
    },
    "townhall.left": {
        "duration_steps": 2,
    },
    "townhall.convened": {
        "speaker_id": "agent-a",
        "topic": "quarterly update",
    },
    "townhall.broadcast": {
        "text": "Broadcast message.",
    },
    "townhall.response": {
        "text": "I agree.",
        "in_response_to": "evt-broadcast",
    },
    "townhall.adjourned": {
        "speaker_id": "agent-a",
        "respondent_count": 3,
    },
    "roundtable.visited": {
        "snapshot_id": "snap-001",
    },
    "roundtable.utterance": {
        "text": "Roundtable remark.",
        "in_response_to": None,
    },
    "roundtable.left": {
        "duration_steps": 1,
    },
    "roundtable.convened": {
        "facilitator_id": "agent-a",
        "topic": "research update",
        "participants": ["agent-a", "agent-b"],
    },
    "roundtable.round_completed": {
        "speakers_this_round": ["agent-a", "agent-b"],
        "round_complete": True,
    },
    "roundtable.adjourned": {
        "facilitator_id": "agent-a",
    },
    "agent.policy.masks_applied": {
        "blocked_leaves": ["READ"],
        "source": "config",
        "vocab_version": "0.1.0",
    },
    "agent.tool.allowlist_applied": {
        "tool_allowlist": ["web.search"],
        "policy": "explicit_list",
    },
    "verifier.boundary_checked": {
        "boundary": "start",
        "outcome": "pass",
        "ledger": "public.jsonl",
        "total_events": 10,
        "errors": [],
        "verifier_mode": "warn",
    },
    "handoff.issued": {
        "handoff_id": "hoff-001",
        "from_role": "research_lead",
        "to_role": "assistant_researcher",
        "task_objective": "Read and summarize paper X.",
        "inputs_refs": ["evt-001", "art-001"],
        "expected_output_shape": "claims + evidence list",
        "deadline_step": 5,
        "completion_status": "pending",
        "checker_verdict": None,
    },
    "checker.verdict": {
        "handoff_id": "hoff-001",
        "batch_id": "batch-001",
        "verdict": "PASS",
        "checker_confidence": 0.92,
        "scores": {
            "evidence_grounding": 0.9,
            "consistency": 0.95,
            "completeness": 0.85,
            "calibration": 0.88,
            "learning_utility": 0.8,
        },
        "accepted_claim_ids": ["C1", "C2"],
        "rejected_claim_ids": [],
        "issues": [],
        "notes": "All claims well-supported.",
    },
}


def test_validate_known_event_payload_accepts_representative_valid_payloads() -> None:
    missing_event_types = set(KNOWN_EVENT_PAYLOAD_MODELS.keys()) - set(REPRESENTATIVE_VALID_PAYLOADS.keys())
    assert not missing_event_types, f"Missing representative payloads for: {missing_event_types}"

    for event_type, payload in REPRESENTATIVE_VALID_PAYLOADS.items():
        result = validate_known_event_payload(event_type, payload)
        assert isinstance(result, dict), f"Validation failed for {event_type}"


# ---------------------------------------------------------------------------
# Section D / G: Structured output handling tests
# ---------------------------------------------------------------------------


def test_structured_retry_produces_failure_marker(tmp_path: Path) -> None:
    llm = _FixedLLM(["still not json", "also not json"])
    executor = _make_executor_with_llm(llm, tmp_path)
    structured, raw = executor._parse_structured_with_retry(
        sub_action="ANALYZE",
        raw_output="not valid json",
        system="test system",
    )
    assert structured is not None
    assert "_validation_failure" in structured
    assert structured["_validation_failure"]["sub_action"] == "ANALYZE"
    assert "text" in structured


def test_structured_retry_succeeds_on_second_attempt(tmp_path: Path) -> None:
    valid_json = json.dumps({
        "assumptions": ["a1"],
        "evidence_gaps": [],
        "structural_weaknesses": [],
        "summary": "repaired",
    })
    llm = _FixedLLM([valid_json])
    executor = _make_executor_with_llm(llm, tmp_path)
    structured, raw = executor._parse_structured_with_retry(
        sub_action="ANALYZE",
        raw_output="garbled original",
        system="test system",
    )
    assert structured is not None
    assert "_validation_failure" not in structured
    assert structured["summary"] == "repaired"
    assert raw == valid_json


def test_structured_valid_on_first_attempt_skips_retry(tmp_path: Path) -> None:
    llm = _FixedLLM(["should not be called"])
    executor = _make_executor_with_llm(llm, tmp_path)
    valid_raw = json.dumps({
        "assumptions": ["a"],
        "evidence_gaps": [],
        "structural_weaknesses": [],
    })
    structured, raw = executor._parse_structured_with_retry(
        sub_action="ANALYZE",
        raw_output=valid_raw,
        system="test system",
    )
    assert structured is not None
    assert "_validation_failure" not in structured
    assert llm._idx == 0


def test_annotate_skips_side_effects_on_validation_failure(tmp_path: Path) -> None:
    from core.writer import ChainWriter

    llm = _FixedLLM(["not json at all", "still broken"])
    storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
    executor = Executor(
        llm=llm,
        storage=storage,
        agent_id="test-agent",
        tool_allowlist=set(),
    )
    public_writer = ChainWriter(storage.public_ledger())
    notebook_writer = ChainWriter(storage.agent_notebook("test-agent"))
    commons_writer = ChainWriter(storage.commons_ledger())
    writers = {"public": public_writer, "notebook": notebook_writer, "commons": commons_writer}
    snapshot = _make_snapshot()

    result = executor.execute("RESEARCH", "ANNOTATE", snapshot, writers)
    assert "executor.structured.validation_failed" in result.side_effects
    assert result.structured is not None
    assert "_validation_failure" in result.structured


# ---------------------------------------------------------------------------
# Section E / G: Schema export tests
# ---------------------------------------------------------------------------


def test_schema_export_covers_all_known_payload_models() -> None:
    known_models = set(KNOWN_EVENT_PAYLOAD_MODELS.values())
    exported_models = set(SCHEMA_MODELS.values())
    missing = known_models - exported_models
    missing_names = {m.__name__ for m in missing}
    assert not missing_names, f"Payload models missing from SCHEMA_MODELS export: {missing_names}"


def test_export_event_schemas_produces_valid_json_schema(tmp_path: Path) -> None:
    from tools.export_event_schemas import export_schemas

    written = export_schemas(tmp_path)
    assert len(written) == len(SCHEMA_MODELS)
    for path in written:
        content = json.loads(path.read_text(encoding="utf-8"))
        assert "type" in content or "properties" in content or "$defs" in content
        assert "title" in content


# ---------------------------------------------------------------------------
# Section F / G: Hash check tooling tests
# ---------------------------------------------------------------------------


def test_hash_check_passes_when_synced(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed content", encoding="utf-8")
    fields_path.write_text('["field_a"]', encoding="utf-8")
    vocab_path.write_text('{"version":"0.1"}', encoding="utf-8")
    exec_path.write_text("# executor code", encoding="utf-8")

    config_path = tmp_path / "run_config_test.json"
    config = {
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": _sha256(vocab_path),
        "executor_templates_hash": _sha256(exec_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    errors = check_config(config_path, tmp_path)
    assert errors == []
