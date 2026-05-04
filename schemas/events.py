from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class DecisionTakenPayload(BaseModel):
    snapshot_id: str
    top_action: str
    sub_action: str
    sample_seed: int


class ActionExecutedPayload(BaseModel):
    top_action: str
    sub_action: str
    raw_output: str
    structured: dict[str, Any] | None = None
    side_effects: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


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
