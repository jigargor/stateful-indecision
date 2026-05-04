from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.canonical_json import canonical_hash


NULL_HASH = "0" * 64


@dataclass
class ChainError:
    line_number: int
    event_id: str
    error: str


@dataclass
class VerificationResult:
    path: Path
    valid: bool
    total_events: int
    errors: list[ChainError]


def verify_chain(path: Path) -> VerificationResult:
    if not path.exists():
        return VerificationResult(path=path, valid=True, total_events=0, errors=[])

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return VerificationResult(path=path, valid=True, total_events=0, errors=[])

    errors: list[ChainError] = []
    previous_hash = NULL_HASH
    for index, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(ChainError(index, "unknown", "invalid json"))
            continue

        event_id = str(event.get("event_id", "unknown"))
        prev_hash = event.get("prev_hash")
        if prev_hash != previous_hash:
            errors.append(
                ChainError(
                    index,
                    event_id,
                    f"prev_hash mismatch: expected {previous_hash}, got {prev_hash}",
                )
            )

        claimed_hash = event.get("record_hash")
        hash_source = dict(event)
        hash_source.pop("record_hash", None)
        recomputed = canonical_hash(hash_source)
        if claimed_hash != recomputed:
            errors.append(
                ChainError(
                    index,
                    event_id,
                    f"record_hash mismatch: expected {recomputed}, got {claimed_hash}",
                )
            )
        previous_hash = claimed_hash if isinstance(claimed_hash, str) else previous_hash

    return VerificationResult(
        path=path,
        valid=len(errors) == 0,
        total_events=len(lines),
        errors=errors,
    )
