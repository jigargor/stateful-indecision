from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FAMILY_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_RESERVED_FAMILY_IDS: frozenset[str] = frozenset({
    "agents", "corpora", "ecosystems", "evaluation",
    "public", "commons", "roundtable", "townhall",
    "tmp", "test", "none", "null", "default", "shared", "shared-knowledge",
})


def validate_family_id(raw: str) -> str:
    cleaned = raw.strip()
    if not _FAMILY_ID_RE.match(cleaned):
        raise ValueError(
            f"Invalid family_id {cleaned!r}: must match {_FAMILY_ID_RE.pattern} "
            "(lowercase, starts with letter, hyphen-separated, max 63 chars)"
        )
    if cleaned in _RESERVED_FAMILY_IDS:
        raise ValueError(
            f"Invalid family_id {cleaned!r}: reserved word "
            f"(reserved: {', '.join(sorted(_RESERVED_FAMILY_IDS))})"
        )
    return cleaned


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_grants_hash(payload: dict[str, Any]) -> str:
    normalized = dict(payload)
    normalized.pop("grants_hash", None)
    encoded = _canonical_json(normalized).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class GrantDecision:
    allowed: bool
    reason: str
    grant_version: int
    grants_hash: str


def load_grant_state(path: Path, *, family_id: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"grant state not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("grant state must be a JSON object")

    fam = validate_family_id(str(data.get("family_id", "")))
    if fam != family_id:
        raise ValueError(f"grant family mismatch: expected {family_id}, got {fam}")

    version = data.get("grant_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("grant_version must be a positive integer")

    updated_at = data.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise ValueError("updated_at must be a non-empty string")

    grants = data.get("grants")
    if not isinstance(grants, list):
        raise ValueError("grants must be a list")

    got_hash = str(data.get("grants_hash", ""))
    expected_hash = compute_grants_hash(data)
    if got_hash != expected_hash:
        raise ValueError("grants_hash mismatch")
    return data


def _parse_ts(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def evaluate_access(
    grant_state: dict[str, Any],
    *,
    ecosystem_id: str,
    agent_id: str,
    access_profile: str,
    max_age_sec: int,
) -> GrantDecision:
    version = int(grant_state["grant_version"])
    grants_hash = str(grant_state["grants_hash"])

    if max_age_sec > 0:
        updated_at = _parse_ts(str(grant_state["updated_at"]))
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age > max_age_sec:
            return GrantDecision(False, "stale_grant_state", version, grants_hash)

    grants = grant_state.get("grants", [])
    for entry in grants:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue
        if str(entry.get("access_profile", "")) != access_profile:
            continue

        allowed_ecosystems = entry.get("allow_ecosystems", [])
        if not isinstance(allowed_ecosystems, list):
            continue
        eco_ok = "*" in allowed_ecosystems or ecosystem_id in allowed_ecosystems
        if not eco_ok:
            continue

        allowed_agents = entry.get("allow_agents", [])
        if not isinstance(allowed_agents, list):
            continue
        agent_ok = not allowed_agents or "*" in allowed_agents or agent_id in allowed_agents
        if not agent_ok:
            continue

        return GrantDecision(True, "grant_match", version, grants_hash)

    return GrantDecision(False, "no_matching_grant", version, grants_hash)
