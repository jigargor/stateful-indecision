"""Build shared-knowledge candidate records from ecosystem research artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from infra.shared_knowledge import validate_family_id
from infra.storage import EcosystemStorage, validate_ecosystem_id


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_candidates(*, base_dir: Path, family_id: str, ecosystems: list[str]) -> list[dict]:
    entries: list[dict] = []
    for ecosystem_id in ecosystems:
        storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
        for agent_id in storage.iter_agent_ids():
            research_dir = storage.agent_research_dir(agent_id)
            for artifact_path in sorted(research_dir.glob("*.json")):
                if not artifact_path.is_file():
                    continue
                try:
                    data = json.loads(artifact_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                content = str(data.get("content", "")).strip()
                if not content:
                    continue
                artifact_id = str(data.get("artifact_id", artifact_path.stem))
                entries.append({
                    "family_id": family_id,
                    "candidate_id": f"{family_id}:{ecosystem_id}:{agent_id}:{artifact_id}",
                    "artifact_id": artifact_id,
                    "content_hash": _content_hash(content),
                    "content": content,
                    "summary": str((data.get("structured") or {}).get("summary", "")) if isinstance(data.get("structured"), dict) else "",
                    "action": str(data.get("action", "")),
                    "source_ecosystem_id": ecosystem_id,
                    "source_agent_id": agent_id,
                    "source_path": str(artifact_path.relative_to(base_dir).as_posix()),
                    "created_at": str(data.get("created_at", "")),
                })
    return entries


def append_candidates(path: Path, entries: list[dict]) -> int:
    seen: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = str(row.get("candidate_id", ""))
            if key:
                seen.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            candidate_id = str(entry.get("candidate_id", ""))
            if not candidate_id or candidate_id in seen:
                continue
            seen.add(candidate_id)
            handle.write(json.dumps(entry) + "\n")
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Index shared-knowledge candidates")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystems", nargs="+", required=True)
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    base_dir = args.base_dir.resolve()
    ecosystem_ids = [validate_ecosystem_id(value) for value in args.ecosystems]
    if not ecosystem_ids:
        raise ValueError("at least one ecosystem id is required")

    storage = EcosystemStorage(ecosystem_id=ecosystem_ids[0], base_dir=base_dir)
    candidates_path = storage.shared_knowledge_candidates(family_id)
    entries = collect_candidates(base_dir=base_dir, family_id=family_id, ecosystems=ecosystem_ids)
    count = append_candidates(candidates_path, entries)
    print(f"[index_shared_knowledge] appended {count} candidates to {candidates_path}")


if __name__ == "__main__":
    main()
