from __future__ import annotations

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    snapshot_id: str
    constitution_text: str
    recent_events: list[dict] = Field(default_factory=list)
    recent_notebook: list[str] = Field(default_factory=list)
    field_chosen: str | None = None
    in_commons: bool = False
    embedding_blob_ref: None = None
