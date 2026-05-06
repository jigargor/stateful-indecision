from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NULL_HASH = "0" * 64


class EventEnvelope(BaseModel):
    schema_version: str = "0.1.0"
    event_id: str
    event_type: str
    ecosystem_id: str
    agent_id: str | None = None
    wall_time: str
    monotonic_ns: int
    payload: dict[str, Any]
    prev_hash: str
    record_hash: str

    @field_validator("prev_hash", "record_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if len(value) != 64:
            raise ValueError("hash must be 64 hex chars")
        int(value, 16)
        return value


class DecisionProposedPayload(BaseModel):
    snapshot_id: str
    top_dist: dict[str, float]
    sub_dist: dict[str, dict[str, float]]
    sample_seed: int
    leaf_category_weights: dict[str, dict[str, float]] = Field(default_factory=dict)


class DecisionTakenPayload(BaseModel):
    snapshot_id: str
    top_action: str
    sub_action: str
    sample_seed: int


class ActionExecutedPayload(BaseModel):
    decision_event_id: str | None = None
    decision_phases: list[str] = Field(default_factory=list)
    top_action: str
    sub_action: str
    raw_output: str
    structured: dict[str, Any] | None = None
    side_effects: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class LatentReasonedPayload(BaseModel):
    phase: str
    snapshot_id: str | None = None
    suggested_top_action: str | None = None
    rationale: str | None = None
    belief_state: dict[str, float] | None = None
    top_action: str | None = None
    sub_action: str | None = None
    structured_candidate: bool | None = None
    raw_output_preview: str | None = None


class NotebookPayload(BaseModel):
    text: str
    ref_decision_id: str
    fingerprint: str | None = None


class ConstitutionRevisedPayload(BaseModel):
    source_event_id: str
    amendment_text: str
    revision_diff: str


class ArtifactStoredPayload(BaseModel):
    artifact_id: str
    artifact_path: str
    action: str
    config_version: str
    snapshot_id: str


class RunCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    decisions_completed: int
    run_seed: int
    field_chosen: str | None = None
    constitution_revision_count: int
    constitution_body_length: int
    action_distribution_observed: dict[str, int]
    notebook_entries: int
    artifacts_stored: int
    run_purpose: str
    run_config_version: str | None = None
    gamma: float | None = None
    horizon_T: int | None = None
    reward_mode: str | None = None
    run_config: dict[str, Any] | None = None


class AgentStateSnapshottedPayload(BaseModel):
    snapshot_id: str
    field_chosen: str | None = None
    in_commons: bool
    recent_event_count: int
    recent_notebook_count: int
    embedding_blob_ref: str | None = None
    belief_state: dict[str, float] = Field(default_factory=dict)


class AnalyzeStructuredOutput(BaseModel):
    assumptions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    structural_weaknesses: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    target_doi: str | None = None
    summary: str | None = None


class AnnotateStructuredOutput(BaseModel):
    title: str | None = None
    doi: str | None = None
    notes: str | None = None
    uncertainties: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    zotero_item_key: str | None = None


class SafetyTriggerArmedPayload(BaseModel):
    rubric_path: str
    rubric_version: str
    rubric_missing: bool = False


class SafetyTriggerEvaluatedPayload(BaseModel):
    source_event_type: str
    source_event_id: str
    outcome: str
    mode: str
    reward_mode: str
    reward_signal: float
    unrecognized_event_type: bool = False


class PolicyMasksAppliedPayload(BaseModel):
    blocked_leaves: list[str]
    source: str
    vocab_version: str


class ToolAllowlistAppliedPayload(BaseModel):
    tool_allowlist: list[str] | None
    policy: str


class VerifierBoundaryCheckedPayload(BaseModel):
    boundary: str
    outcome: str
    ledger: str
    total_events: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    verifier_mode: str


class IndulgeRequestedPayload(BaseModel):
    request_text: str
    motivation: str


class IndulgeRespondedPayload(BaseModel):
    status: str
    response_text: str


class AgentInstantiatedPayload(BaseModel):
    seed_source: str
    model_id: str
    provider: str


class FieldOfferedPayload(BaseModel):
    fields: list[str]


class FieldChosenPayload(BaseModel):
    field: str


class AgentShutdownPayload(BaseModel):
    reason: str
    decisions_completed: int


class AgentErrorPayload(BaseModel):
    error_type: str
    message: str
    decision_number: int


class ForumVisitedPayload(BaseModel):
    snapshot_id: str


class ForumUtterancePayload(BaseModel):
    text: str
    in_response_to: str | None = None


class ForumLeftPayload(BaseModel):
    duration_steps: int


class TownhallConvenedPayload(BaseModel):
    speaker_id: str
    topic: str
    session_kind: str | None = None
    tangential_bridge: str | None = None


class TownhallBroadcastPayload(BaseModel):
    text: str


class TownhallResponsePayload(BaseModel):
    text: str
    in_response_to: str | None = None


class TownhallAdjournedPayload(BaseModel):
    speaker_id: str
    respondent_count: int


class RoundtableConvenedPayload(BaseModel):
    facilitator_id: str
    topic: str
    participants: list[str]


class RoundtableRoundCompletedPayload(BaseModel):
    speakers_this_round: list[str]
    round_complete: bool


class RoundtableAdjournedPayload(BaseModel):
    facilitator_id: str


HANDOFF_ROLES = {"research_lead", "assistant_researcher", "checker"}
COMPLETION_STATUSES = {"pending", "in_progress", "completed", "blocked"}
CHECKER_VERDICTS = {"PASS", "REVISE", "BLOCK"}


class HandoffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    from_role: Literal["research_lead", "assistant_researcher", "checker"]
    to_role: Literal["research_lead", "assistant_researcher", "checker"]
    task_objective: str
    inputs_refs: list[str]
    expected_output_shape: str
    deadline_step: int
    completion_status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    checker_verdict: Literal["PASS", "REVISE", "BLOCK"] | None = None

    @field_validator("task_objective")
    @classmethod
    def validate_task_objective(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_objective must be non-empty")
        return value

    @model_validator(mode="after")
    def validate_status_verdict_consistency(self) -> "HandoffPayload":
        status = self.completion_status
        verdict = self.checker_verdict
        if status == "completed" and verdict != "PASS":
            raise ValueError("completion_status='completed' requires checker_verdict='PASS'")
        if status == "blocked" and verdict != "BLOCK":
            raise ValueError("completion_status='blocked' requires checker_verdict='BLOCK'")
        if status in ("pending", "in_progress") and verdict not in (None, "REVISE"):
            raise ValueError(
                f"completion_status='{status}' allows checker_verdict to be None or 'REVISE'"
            )
        return self


class CheckerVerdictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    batch_id: str | None = None
    verdict: Literal["PASS", "REVISE", "BLOCK"]
    checker_confidence: float
    scores: dict[str, float]
    accepted_claim_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("checker_confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"checker_confidence must be between 0.0 and 1.0, got {value}")
        return value

    @field_validator("scores")
    @classmethod
    def validate_scores(cls, value: dict[str, float]) -> dict[str, float]:
        for key, score in value.items():
            if not (0.0 <= score <= 1.0):
                raise ValueError(f"score '{key}' must be between 0.0 and 1.0, got {score}")
        return value


KNOWN_EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "agent.state.snapshotted": AgentStateSnapshottedPayload,
    "agent.decision.proposed": DecisionProposedPayload,
    "agent.decision.taken": DecisionTakenPayload,
    "agent.latent.reasoned": LatentReasonedPayload,
    "action.executed": ActionExecutedPayload,
    "agent.notebook.appended": NotebookPayload,
    "agent.constitution.revised": ConstitutionRevisedPayload,
    "agent.artifact.stored": ArtifactStoredPayload,
    "agent.skill.authored": ArtifactStoredPayload,
    "run.completed": RunCompletedPayload,
    "safety.trigger.armed": SafetyTriggerArmedPayload,
    "safety.trigger.evaluated": SafetyTriggerEvaluatedPayload,
    "agent.policy.masks_applied": PolicyMasksAppliedPayload,
    "agent.tool.allowlist_applied": ToolAllowlistAppliedPayload,
    "verifier.boundary_checked": VerifierBoundaryCheckedPayload,
    "indulge.requested": IndulgeRequestedPayload,
    "indulge.responded": IndulgeRespondedPayload,
    "agent.instantiated": AgentInstantiatedPayload,
    "field.offered": FieldOfferedPayload,
    "field.chosen": FieldChosenPayload,
    "agent.shutdown": AgentShutdownPayload,
    "agent.error": AgentErrorPayload,
    "commons.visited": ForumVisitedPayload,
    "commons.utterance": ForumUtterancePayload,
    "commons.left": ForumLeftPayload,
    "townhall.visited": ForumVisitedPayload,
    "townhall.utterance": ForumUtterancePayload,
    "townhall.left": ForumLeftPayload,
    "townhall.convened": TownhallConvenedPayload,
    "townhall.broadcast": TownhallBroadcastPayload,
    "townhall.response": TownhallResponsePayload,
    "townhall.adjourned": TownhallAdjournedPayload,
    "roundtable.visited": ForumVisitedPayload,
    "roundtable.utterance": ForumUtterancePayload,
    "roundtable.left": ForumLeftPayload,
    "roundtable.convened": RoundtableConvenedPayload,
    "roundtable.round_completed": RoundtableRoundCompletedPayload,
    "roundtable.adjourned": RoundtableAdjournedPayload,
    "handoff.issued": HandoffPayload,
    "checker.verdict": CheckerVerdictPayload,
}


def validate_known_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = KNOWN_EVENT_PAYLOAD_MODELS.get(event_type)
    if model is None:
        return payload
    return model.model_validate(payload).model_dump()


class ActionVocabulary(BaseModel):
    version: str
    categories: dict[str, list[str]]
    leaf_category_weights: dict[str, dict[str, float]] = Field(default_factory=dict)

    @property
    def all_leaves(self) -> list[str]:
        leaves: list[str] = []
        for leaf_list in self.categories.values():
            leaves.extend(leaf_list)
        return leaves

    @field_validator("leaf_category_weights")
    @classmethod
    def validate_weights(cls, weights: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for leaf, cat_weights in weights.items():
            total = sum(cat_weights.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"weights for {leaf} sum to {total}, expected 1.0")
        return weights

    def primary_category(self, leaf: str) -> str:
        """The category with the highest weight for this leaf."""
        weights = self.leaf_category_weights.get(leaf, {})
        if not weights:
            for cat, leaves in self.categories.items():
                if leaf in leaves:
                    return cat
            raise KeyError(f"unknown leaf: {leaf}")
        return max(weights, key=weights.get)

    def category_affinity(self, leaf: str, category: str) -> float:
        """How strongly a leaf associates with a given category. 0.0 if unset."""
        return self.leaf_category_weights.get(leaf, {}).get(category, 0.0)

    @classmethod
    def load(cls, path: Path) -> "ActionVocabulary":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
