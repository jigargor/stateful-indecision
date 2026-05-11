from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SharedKnowledgeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    candidate_id: str
    artifact_id: str
    content_hash: str
    content: str
    summary: str = ""
    action: str = ""
    source_ecosystem_id: str
    source_agent_id: str
    source_path: str
    created_at: str = ""


class SharedKnowledgePromoted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    promotion_id: str
    content_hash: str
    content: str
    summary: str = ""
    action: str = ""
    quality_score: float
    filter_reasons: list[str] = Field(default_factory=list)
    promotion_timestamp: str
    source_ecosystems: list[str] = Field(default_factory=list)
    source_agents: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    source_candidate_ids: list[str] = Field(default_factory=list)


class GrantLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    grant_id: str
    access_profile: str
    allow_ecosystems: list[str] = Field(default_factory=list)
    allow_agents: list[str] = Field(default_factory=list)
    enabled: bool = True
    updated_at: str


class GrantState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    grant_version: int
    grants_hash: str
    updated_at: str
    grants: list[dict[str, Any]] = Field(default_factory=list)
