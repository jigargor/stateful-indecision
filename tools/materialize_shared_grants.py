"""Materialize family grant_state.json from append-only grant_ledger.jsonl."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from infra.shared_knowledge import compute_grants_hash, validate_family_id
from infra.storage import EcosystemStorage, validate_ecosystem_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def materialize_grant_state(*, ledger_path: Path, state_path: Path, family_id: str) -> dict:
    grants_by_id: dict[str, dict] = {}
    for row in _read_jsonl(ledger_path):
        if str(row.get("family_id", "")) != family_id:
            continue
        grant_id = str(row.get("grant_id", "")).strip()
        if not grant_id:
            continue
        revoked = bool(row.get("revoked", False))
        if revoked:
            grants_by_id.pop(grant_id, None)
            continue
        grants_by_id[grant_id] = {
            "grant_id": grant_id,
            "access_profile": str(row.get("access_profile", "")),
            "allow_ecosystems": list(row.get("allow_ecosystems", [])),
            "allow_agents": list(row.get("allow_agents", [])),
            "enabled": bool(row.get("enabled", True)),
            "updated_at": str(row.get("updated_at", "")),
        }

    grants = [grants_by_id[key] for key in sorted(grants_by_id.keys())]
    previous_version = 0
    if state_path.exists():
        try:
            previous_version = int(json.loads(state_path.read_text(encoding="utf-8")).get("grant_version", 0))
        except Exception:
            previous_version = 0

    state = {
        "family_id": family_id,
        "grant_version": previous_version + 1,
        "updated_at": _utc_now(),
        "grants": grants,
    }
    state["grants_hash"] = compute_grants_hash(state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize shared grant state")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystem", required=True, help="Any ecosystem in the family for base path resolution")
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    ecosystem_id = validate_ecosystem_id(args.ecosystem)
    base_dir = args.base_dir.resolve()
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    state = materialize_grant_state(
        ledger_path=storage.shared_knowledge_grant_ledger(family_id),
        state_path=storage.shared_knowledge_grant_state(family_id),
        family_id=family_id,
    )
    print(
        "[materialize_shared_grants] "
        f"grant_version={state['grant_version']} grants={len(state['grants'])}"
    )


if __name__ == "__main__":
    main()
