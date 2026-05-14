from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from infra.shared_knowledge import validate_family_id


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def shared_family_prefix(family_id: str) -> str:
    safe = validate_family_id(family_id)
    return f"shared_knowledge/{safe}"


def shared_snapshot_prefix(family_id: str, snapshot_id: str) -> str:
    return f"{shared_family_prefix(family_id)}/snapshots/{snapshot_id}"


def shared_head_key(family_id: str) -> str:
    return f"{shared_family_prefix(family_id)}/HEAD.json"


def shared_snapshot_key(family_id: str, snapshot_id: str, filename: str) -> str:
    return f"{shared_snapshot_prefix(family_id, snapshot_id)}/{filename}"


class SharedKnowledgeHeadPointer(BaseModel):
    family_id: str
    snapshot_id: str
    updated_at: str
    promoted_key: str
    grant_state_key: str
    candidates_key: str | None = None
    grant_ledger_key: str | None = None
    promoted_sha256: str
    grant_state_sha256: str
    candidates_sha256: str | None = None
    grant_ledger_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("family_id")
    @classmethod
    def validate_family(cls, value: str) -> str:
        return validate_family_id(value)

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.model_dump(), indent=2, sort_keys=True).encode("utf-8")
