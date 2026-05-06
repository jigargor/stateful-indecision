"""Wave E2 — Offline multi-run map-reduce protocol surfaces.

Tests cover:
  - HandoffPayload and CheckerVerdictPayload schema validation
  - KNOWN_EVENT_PAYLOAD_MODELS registration for new event types
  - Forum/public dual-write consistency (same event_id in both ledgers)
  - Checker verdict convention documentation guards
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.writer import ChainWriter
from forums.base import ForumBase, ForumView
from infra.storage import EcosystemStorage
from schemas.events import (
    CHECKER_VERDICTS,
    COMPLETION_STATUSES,
    CheckerVerdictPayload,
    HANDOFF_ROLES,
    HandoffPayload,
    KNOWN_EVENT_PAYLOAD_MODELS,
    validate_known_event_payload,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _valid_handoff(**overrides) -> dict:
    base = {
        "handoff_id": str(uuid4()),
        "from_role": "research_lead",
        "to_role": "assistant_researcher",
        "task_objective": "Read and extract claims from paper X.",
        "inputs_refs": ["evt-001", "art-002"],
        "expected_output_shape": "claims + evidence list",
        "deadline_step": 5,
        "completion_status": "pending",
        "checker_verdict": None,
    }
    base.update(overrides)
    return base


def _valid_verdict(**overrides) -> dict:
    base = {
        "handoff_id": str(uuid4()),
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
        "notes": "Solid evidence base.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# A) HandoffPayload schema validation
# ---------------------------------------------------------------------------


class TestHandoffPayloadValid:
    def test_round_trip(self) -> None:
        data = _valid_handoff()
        model = HandoffPayload.model_validate(data)
        dumped = model.model_dump()
        assert dumped["handoff_id"] == data["handoff_id"]
        assert dumped["from_role"] == "research_lead"
        assert dumped["to_role"] == "assistant_researcher"

    def test_minimal_required_fields(self) -> None:
        data = {
            "handoff_id": "h1",
            "from_role": "checker",
            "to_role": "research_lead",
            "task_objective": "Verify claims.",
            "inputs_refs": ["ref-1"],
            "expected_output_shape": "verdict",
            "deadline_step": 3,
        }
        model = HandoffPayload.model_validate(data)
        assert model.deadline_step == 3
        assert model.completion_status == "pending"
        assert model.checker_verdict is None
        assert model.inputs_refs == ["ref-1"]

    def test_all_roles_accepted(self) -> None:
        for role in sorted(HANDOFF_ROLES):
            HandoffPayload.model_validate(
                _valid_handoff(from_role=role, to_role=role)
            )

    def test_all_completion_statuses_accepted(self) -> None:
        status_verdict_pairs = {
            "pending": None,
            "in_progress": None,
            "completed": "PASS",
            "blocked": "BLOCK",
        }
        for status, verdict in status_verdict_pairs.items():
            HandoffPayload.model_validate(
                _valid_handoff(completion_status=status, checker_verdict=verdict)
            )

    def test_completion_status_defaults_to_pending(self) -> None:
        data = _valid_handoff()
        del data["completion_status"]
        model = HandoffPayload.model_validate(data)
        assert model.completion_status == "pending"

    def test_all_checker_verdicts_accepted(self) -> None:
        verdict_status_pairs = {
            "PASS": "completed",
            "REVISE": "pending",
            "BLOCK": "blocked",
        }
        for verdict, status in verdict_status_pairs.items():
            HandoffPayload.model_validate(
                _valid_handoff(checker_verdict=verdict, completion_status=status)
            )

    def test_none_checker_verdict_accepted(self) -> None:
        HandoffPayload.model_validate(_valid_handoff(checker_verdict=None))


class TestHandoffPayloadInvalid:
    def test_invalid_from_role(self) -> None:
        with pytest.raises(ValidationError, match="Input should be"):
            HandoffPayload.model_validate(_valid_handoff(from_role="manager"))

    def test_invalid_to_role(self) -> None:
        with pytest.raises(ValidationError, match="Input should be"):
            HandoffPayload.model_validate(_valid_handoff(to_role="intern"))

    def test_empty_task_objective(self) -> None:
        with pytest.raises(ValidationError, match="task_objective must be non-empty"):
            HandoffPayload.model_validate(_valid_handoff(task_objective="  "))

    def test_invalid_completion_status(self) -> None:
        with pytest.raises(ValidationError, match="Input should be"):
            HandoffPayload.model_validate(_valid_handoff(completion_status="done"))

    def test_invalid_checker_verdict(self) -> None:
        with pytest.raises(ValidationError, match="Input should be"):
            HandoffPayload.model_validate(_valid_handoff(checker_verdict="APPROVE"))

    def test_missing_required_field(self) -> None:
        data = _valid_handoff()
        del data["task_objective"]
        with pytest.raises(ValidationError):
            HandoffPayload.model_validate(data)

    def test_missing_inputs_refs(self) -> None:
        data = _valid_handoff()
        del data["inputs_refs"]
        with pytest.raises(ValidationError):
            HandoffPayload.model_validate(data)

    def test_missing_deadline_step(self) -> None:
        data = _valid_handoff()
        del data["deadline_step"]
        with pytest.raises(ValidationError):
            HandoffPayload.model_validate(data)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HandoffPayload.model_validate(_valid_handoff(surprise_field="nope"))


# ---------------------------------------------------------------------------
# B) CheckerVerdictPayload schema validation
# ---------------------------------------------------------------------------


class TestCheckerVerdictValid:
    def test_round_trip(self) -> None:
        data = _valid_verdict()
        model = CheckerVerdictPayload.model_validate(data)
        dumped = model.model_dump()
        assert dumped["verdict"] == "PASS"
        assert dumped["checker_confidence"] == pytest.approx(0.92)

    def test_all_verdicts_accepted(self) -> None:
        for v in sorted(CHECKER_VERDICTS):
            CheckerVerdictPayload.model_validate(_valid_verdict(verdict=v))

    def test_boundary_confidence_values(self) -> None:
        CheckerVerdictPayload.model_validate(_valid_verdict(checker_confidence=0.0))
        CheckerVerdictPayload.model_validate(_valid_verdict(checker_confidence=1.0))

    def test_optional_batch_id_none(self) -> None:
        model = CheckerVerdictPayload.model_validate(_valid_verdict(batch_id=None))
        assert model.batch_id is None

    def test_optional_notes_none(self) -> None:
        model = CheckerVerdictPayload.model_validate(_valid_verdict(notes=None))
        assert model.notes is None


class TestCheckerVerdictInvalid:
    def test_invalid_verdict(self) -> None:
        with pytest.raises(ValidationError, match="Input should be"):
            CheckerVerdictPayload.model_validate(_valid_verdict(verdict="APPROVE"))

    def test_confidence_below_zero(self) -> None:
        with pytest.raises(ValidationError, match="checker_confidence must be between"):
            CheckerVerdictPayload.model_validate(_valid_verdict(checker_confidence=-0.1))

    def test_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError, match="checker_confidence must be between"):
            CheckerVerdictPayload.model_validate(_valid_verdict(checker_confidence=1.01))

    def test_missing_required_field(self) -> None:
        data = _valid_verdict()
        del data["scores"]
        with pytest.raises(ValidationError):
            CheckerVerdictPayload.model_validate(data)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckerVerdictPayload.model_validate(_valid_verdict(bonus="nope"))

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            CheckerVerdictPayload.model_validate(
                _valid_verdict(scores={"evidence_grounding": -0.1})
            )

    def test_score_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be between 0.0 and 1.0"):
            CheckerVerdictPayload.model_validate(
                _valid_verdict(scores={"calibration": 1.5})
            )

    def test_score_boundary_values_accepted(self) -> None:
        model = CheckerVerdictPayload.model_validate(
            _valid_verdict(scores={"low": 0.0, "high": 1.0, "mid": 0.5})
        )
        assert model.scores == {"low": 0.0, "high": 1.0, "mid": 0.5}


# ---------------------------------------------------------------------------
# C) KNOWN_EVENT_PAYLOAD_MODELS registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_handoff_issued_registered(self) -> None:
        assert "handoff.issued" in KNOWN_EVENT_PAYLOAD_MODELS
        assert KNOWN_EVENT_PAYLOAD_MODELS["handoff.issued"] is HandoffPayload

    def test_checker_verdict_registered(self) -> None:
        assert "checker.verdict" in KNOWN_EVENT_PAYLOAD_MODELS
        assert KNOWN_EVENT_PAYLOAD_MODELS["checker.verdict"] is CheckerVerdictPayload

    def test_validate_known_event_payload_handoff(self) -> None:
        result = validate_known_event_payload("handoff.issued", _valid_handoff())
        assert isinstance(result, dict)
        assert result["from_role"] == "research_lead"

    def test_validate_known_event_payload_verdict(self) -> None:
        result = validate_known_event_payload("checker.verdict", _valid_verdict())
        assert isinstance(result, dict)
        assert result["verdict"] == "PASS"

    def test_validate_known_event_payload_rejects_invalid_handoff(self) -> None:
        with pytest.raises(Exception):
            validate_known_event_payload("handoff.issued", {"bad": True})

    def test_validate_known_event_payload_rejects_invalid_verdict(self) -> None:
        with pytest.raises(Exception):
            validate_known_event_payload("checker.verdict", {"bad": True})


# ---------------------------------------------------------------------------
# D) Forum/public dual-write consistency
# ---------------------------------------------------------------------------


class _TestForum(ForumBase):
    """Minimal concrete forum for testing dual-write."""

    @property
    def event_prefix(self) -> str:
        return "test_forum"

    def _build_view(self, current_agent: str) -> ForumView:
        return ForumView()


def _read_ledger_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


class TestDualWriteConsistency:
    def test_same_event_id_in_both_ledgers(self, tmp_path: Path) -> None:
        storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
        forum_path = storage.resolve("test_forum.jsonl")
        public_path = storage.public_ledger()
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        forum = _TestForum(forum_writer, public_writer, "alpha")
        forum.join("agent-a", "snap-001")

        forum_events = _read_ledger_events(forum_path)
        public_events = _read_ledger_events(public_path)

        assert len(forum_events) == 1
        assert len(public_events) == 1
        assert forum_events[0]["event_id"] == public_events[0]["event_id"]

    def test_payload_identical_across_ledgers(self, tmp_path: Path) -> None:
        storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
        forum_path = storage.resolve("test_forum.jsonl")
        public_path = storage.public_ledger()
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        forum = _TestForum(forum_writer, public_writer, "alpha")
        event_id = forum.speak("agent-a", "hello dual write")

        forum_events = _read_ledger_events(forum_path)
        public_events = _read_ledger_events(public_path)

        assert len(forum_events) == 1
        assert len(public_events) == 1
        assert forum_events[0]["payload"] == public_events[0]["payload"]
        assert forum_events[0]["event_type"] == public_events[0]["event_type"]

    def test_handoff_issued_dual_write(self, tmp_path: Path) -> None:
        """Dual-write a handoff.issued event and verify both ledgers validate the payload."""
        storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
        forum_path = storage.resolve("handoff_forum.jsonl")
        public_path = storage.public_ledger()
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        handoff = _valid_handoff()
        event_id = str(uuid4())

        forum_writer.append(
            "handoff.issued",
            handoff,
            ecosystem_id="alpha",
            agent_id="agent-a",
            event_id_override=event_id,
        )
        public_writer.append(
            "handoff.issued",
            handoff,
            ecosystem_id="alpha",
            agent_id="agent-a",
            event_id_override=event_id,
        )

        forum_events = _read_ledger_events(forum_path)
        public_events = _read_ledger_events(public_path)

        assert len(forum_events) == 1
        assert len(public_events) == 1
        assert forum_events[0]["event_id"] == public_events[0]["event_id"] == event_id
        assert forum_events[0]["event_type"] == "handoff.issued"
        assert forum_events[0]["payload"]["handoff_id"] == handoff["handoff_id"]

    def test_multiple_dual_writes_preserve_ids(self, tmp_path: Path) -> None:
        storage = EcosystemStorage(ecosystem_id="alpha", base_dir=tmp_path)
        forum_path = storage.resolve("test_forum.jsonl")
        public_path = storage.public_ledger()
        forum_writer = ChainWriter(forum_path)
        public_writer = ChainWriter(public_path)

        forum = _TestForum(forum_writer, public_writer, "alpha")
        forum.join("agent-a", "snap-001")
        forum.speak("agent-a", "message one")
        forum.speak("agent-a", "message two")
        forum.leave("agent-a", 1)

        forum_events = _read_ledger_events(forum_path)
        public_events = _read_ledger_events(public_path)

        assert len(forum_events) == 4
        assert len(public_events) == 4
        for fe, pe in zip(forum_events, public_events):
            assert fe["event_id"] == pe["event_id"]
            assert fe["payload"] == pe["payload"]


# ---------------------------------------------------------------------------
# E) Checker verdict convention guards
# ---------------------------------------------------------------------------


class TestStatusVerdictCrossValidation:
    """Model-level enforcement: status/verdict pairs are always consistent."""

    def test_pending_none_accepted(self) -> None:
        h = HandoffPayload.model_validate(
            _valid_handoff(completion_status="pending", checker_verdict=None)
        )
        assert h.completion_status == "pending"
        assert h.checker_verdict is None

    def test_pending_revise_accepted(self) -> None:
        h = HandoffPayload.model_validate(
            _valid_handoff(completion_status="pending", checker_verdict="REVISE")
        )
        assert h.completion_status == "pending"
        assert h.checker_verdict == "REVISE"

    def test_in_progress_none_accepted(self) -> None:
        h = HandoffPayload.model_validate(
            _valid_handoff(completion_status="in_progress", checker_verdict=None)
        )
        assert h.completion_status == "in_progress"

    def test_completed_pass_accepted(self) -> None:
        h = HandoffPayload.model_validate(
            _valid_handoff(completion_status="completed", checker_verdict="PASS")
        )
        assert h.completion_status == "completed"
        assert h.checker_verdict == "PASS"

    def test_blocked_block_accepted(self) -> None:
        h = HandoffPayload.model_validate(
            _valid_handoff(completion_status="blocked", checker_verdict="BLOCK")
        )
        assert h.completion_status == "blocked"
        assert h.checker_verdict == "BLOCK"

    def test_completed_without_pass_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires checker_verdict='PASS'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="completed", checker_verdict=None)
            )

    def test_completed_with_block_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires checker_verdict='PASS'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="completed", checker_verdict="BLOCK")
            )

    def test_blocked_without_block_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires checker_verdict='BLOCK'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="blocked", checker_verdict=None)
            )

    def test_blocked_with_pass_rejected(self) -> None:
        with pytest.raises(ValidationError, match="requires checker_verdict='BLOCK'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="blocked", checker_verdict="PASS")
            )

    def test_pending_with_pass_rejected(self) -> None:
        with pytest.raises(ValidationError, match="allows checker_verdict to be None or 'REVISE'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="pending", checker_verdict="PASS")
            )

    def test_pending_with_block_rejected(self) -> None:
        with pytest.raises(ValidationError, match="allows checker_verdict to be None or 'REVISE'"):
            HandoffPayload.model_validate(
                _valid_handoff(completion_status="pending", checker_verdict="BLOCK")
            )


# ---------------------------------------------------------------------------
# F) Handoff field completeness
# ---------------------------------------------------------------------------


class TestFieldCompleteness:
    """All required handoff fields from the autogen-iteration-protocol are present."""

    REQUIRED_HANDOFF_FIELDS = {
        "handoff_id",
        "from_role",
        "to_role",
        "task_objective",
        "inputs_refs",
        "expected_output_shape",
        "deadline_step",
        "completion_status",
        "checker_verdict",
    }

    REQUIRED_VERDICT_FIELDS = {
        "handoff_id",
        "batch_id",
        "verdict",
        "checker_confidence",
        "scores",
        "accepted_claim_ids",
        "rejected_claim_ids",
        "issues",
        "notes",
    }

    def test_handoff_model_fields(self) -> None:
        actual = set(HandoffPayload.model_fields.keys())
        assert self.REQUIRED_HANDOFF_FIELDS == actual

    def test_verdict_model_fields(self) -> None:
        actual = set(CheckerVerdictPayload.model_fields.keys())
        assert self.REQUIRED_VERDICT_FIELDS == actual


# ---------------------------------------------------------------------------
# G) Regression: existing payload models unaffected
# ---------------------------------------------------------------------------


class TestRegressionExistingPayloads:
    def test_existing_models_still_registered(self) -> None:
        pre_e2_types = {
            "agent.state.snapshotted",
            "agent.decision.proposed",
            "agent.decision.taken",
            "agent.latent.reasoned",
            "action.executed",
            "agent.notebook.appended",
            "agent.constitution.revised",
            "agent.artifact.stored",
            "agent.skill.authored",
            "run.completed",
            "safety.trigger.armed",
            "safety.trigger.evaluated",
            "agent.policy.masks_applied",
            "agent.tool.allowlist_applied",
            "verifier.boundary_checked",
            "indulge.requested",
            "indulge.responded",
            "agent.instantiated",
            "field.offered",
            "field.chosen",
            "agent.shutdown",
            "agent.error",
            "commons.visited",
            "commons.utterance",
            "commons.left",
            "townhall.visited",
            "townhall.utterance",
            "townhall.left",
            "townhall.convened",
            "townhall.broadcast",
            "townhall.response",
            "townhall.adjourned",
            "roundtable.visited",
            "roundtable.utterance",
            "roundtable.left",
            "roundtable.convened",
            "roundtable.round_completed",
            "roundtable.adjourned",
        }
        for et in pre_e2_types:
            assert et in KNOWN_EVENT_PAYLOAD_MODELS, f"Pre-E2 event type missing: {et}"

    def test_unknown_event_still_passes_through(self) -> None:
        payload = {"anything": "goes"}
        result = validate_known_event_payload("future.unknown.event", payload)
        assert result is payload
