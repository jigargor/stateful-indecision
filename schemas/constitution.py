from __future__ import annotations

from pydantic import BaseModel


class ConstitutionFrontmatter(BaseModel):
    agent_id: str
    ecosystem_id: str
    created_at: str
    revision_count: int
    last_revised_event_id: str | None = None
    field_chosen: str | None = None
