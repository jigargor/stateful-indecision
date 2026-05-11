"""Promote shared-knowledge candidates into curated family-level records."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from infra.shared_knowledge import validate_family_id
from infra.storage import EcosystemStorage, validate_ecosystem_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _quality_score(content: str, summary: str) -> float:
    score = 0.0
    if len(content) >= 240:
        score += 0.5
    if len(summary.strip()) >= 32:
        score += 0.3
    if "\n" in content:
        score += 0.2
    return min(1.0, round(score, 3))


def promote_candidates(*, family_id: str, candidates: list[dict], min_quality: float) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in candidates:
        content_hash = str(row.get("content_hash", "")).strip()
        if content_hash:
            grouped[content_hash].append(row)

    promoted: list[dict] = []
    for content_hash, group in grouped.items():
        exemplar = group[0]
        content = str(exemplar.get("content", "")).strip()
        summary = str(exemplar.get("summary", "")).strip()
        quality = _quality_score(content, summary)
        filter_reasons: list[str] = []
        if not content:
            filter_reasons.append("empty_content")
        if quality < min_quality:
            filter_reasons.append("below_quality_threshold")
        if filter_reasons:
            continue
        promoted.append({
            "family_id": family_id,
            "promotion_id": f"{family_id}:{content_hash}",
            "content_hash": content_hash,
            "content": content,
            "summary": summary,
            "action": str(exemplar.get("action", "")),
            "quality_score": quality,
            "filter_reasons": [],
            "promotion_timestamp": _utc_now(),
            "source_ecosystems": sorted({str(item.get("source_ecosystem_id", "")) for item in group if item.get("source_ecosystem_id")}),
            "source_agents": sorted({str(item.get("source_agent_id", "")) for item in group if item.get("source_agent_id")}),
            "source_artifact_ids": sorted({str(item.get("artifact_id", "")) for item in group if item.get("artifact_id")}),
            "source_paths": sorted({str(item.get("source_path", "")) for item in group if item.get("source_path")}),
            "source_candidate_ids": sorted({str(item.get("candidate_id", "")) for item in group if item.get("candidate_id")}),
        })
    return promoted


def append_promotions(path: Path, rows: list[dict]) -> int:
    seen: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = str(row.get("promotion_id", ""))
            if pid:
                seen.add(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            pid = str(row.get("promotion_id", ""))
            if not pid or pid in seen:
                continue
            seen.add(pid)
            handle.write(json.dumps(row) + "\n")
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote shared-knowledge candidates")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--ecosystem", required=True, help="Any ecosystem in the family for base path resolution")
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument("--min-quality", type=float, default=0.4)
    args = parser.parse_args()

    family_id = validate_family_id(args.family_id)
    ecosystem_id = validate_ecosystem_id(args.ecosystem)
    base_dir = args.base_dir.resolve()
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    candidates_path = storage.shared_knowledge_candidates(family_id)
    promoted_path = storage.shared_knowledge_promoted(family_id)

    candidates = _load_jsonl(candidates_path)
    promoted_rows = promote_candidates(
        family_id=family_id,
        candidates=candidates,
        min_quality=args.min_quality,
    )
    count = append_promotions(promoted_path, promoted_rows)
    print(f"[promote_shared_knowledge] appended {count} promoted records to {promoted_path}")


if __name__ == "__main__":
    main()
