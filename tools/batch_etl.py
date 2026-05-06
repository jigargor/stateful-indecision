"""Periodic batch ETL: merge ledger JSONL into columnar tabular files; route research separately.

Designed for cron / scheduled jobs after ``aws s3 sync`` (or on local ``ecosystems/``).

Tabular outputs (Apache Parquet, hive-partitioned by ``ecosystem_id``):

- ``tabular/events/`` — one row per JSONL event (payload as JSON string).
- ``tabular/runs/`` — rows extracted from ``run.completed`` events.

Research outputs (separate from hot ledger tables):

- ``research/artifact_metadata/`` — hive-partitioned Parquet (narrow columns + ``source_file``, no full body).
- ``research/artifact_bodies.jsonl`` — one JSON object per line: ``artifact_id``, ``content``, ``structured``.

Requires the ``etl`` optional extra: ``uv sync --extra etl``

Usage:
    uv run python -m tools.batch_etl --base-dir . --out-dir ./etl_warehouse
    uv run python -m tools.batch_etl --base-dir . --out-dir ./etl_warehouse --batch-label nightly
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class ETLStats:
    event_rows: int = 0
    run_rows: int = 0
    artifact_meta_rows: int = 0
    artifact_bodies_lines: int = 0
    jsonl_files_scanned: int = 0
    json_files_scanned: int = 0


def _utc_batch_id(label: str | None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{label}_{ts}" if label else ts


def _iter_ecosystem_jsonl(base_dir: Path) -> Iterator[Path]:
    root = base_dir / "ecosystems"
    if not root.is_dir():
        return
    yield from sorted(root.rglob("*.jsonl"))


def _iter_research_json(base_dir: Path) -> Iterator[Path]:
    root = base_dir / "ecosystems"
    if not root.is_dir():
        return
    for p in sorted(root.rglob("research/*.json")):
        if p.is_file():
            yield p


def _event_row(event: dict[str, Any], source_file: str) -> dict[str, Any]:
    payload = event.get("payload")
    return {
        "event_id": event.get("event_id"),
        "schema_version": event.get("schema_version"),
        "event_type": event.get("event_type"),
        "ecosystem_id": event.get("ecosystem_id") or "unknown",
        "agent_id": event.get("agent_id"),
        "wall_time": event.get("wall_time"),
        "monotonic_ns": event.get("monotonic_ns"),
        "prev_hash": event.get("prev_hash"),
        "record_hash": event.get("record_hash"),
        "payload_json": json.dumps(payload if payload is not None else {}),
        "source_ledger": source_file,
    }


def _run_row(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    return {
        "event_id": event.get("event_id"),
        "ecosystem_id": event.get("ecosystem_id") or "unknown",
        "agent_id": event.get("agent_id"),
        "decisions_completed": payload.get("decisions_completed"),
        "run_seed": payload.get("run_seed"),
        "field_chosen": payload.get("field_chosen"),
        "constitution_revision_count": payload.get("constitution_revision_count"),
        "artifacts_stored": payload.get("artifacts_stored"),
        "notebook_entries": payload.get("notebook_entries"),
        "run_config_version": payload.get("run_config_version"),
        "wall_time": event.get("wall_time"),
        "run_purpose": payload.get("run_purpose"),
    }


def _artifact_meta_row(data: dict[str, Any], source_file: str) -> dict[str, Any]:
    content = data.get("content")
    text = content if isinstance(content, str) else ""
    structured = data.get("structured")
    return {
        "artifact_id": data.get("artifact_id"),
        "agent_id": data.get("agent_id"),
        "ecosystem_id": data.get("ecosystem_id") or "unknown",
        "snapshot_id": data.get("snapshot_id"),
        "action": data.get("action"),
        "config_version": data.get("config_version"),
        "created_at": data.get("created_at"),
        "content_length": len(text),
        "content_preview": text[:500],
        "structured_json": json.dumps(structured) if structured is not None else None,
        "source_file": str(Path(source_file).as_posix()),
    }


def _flush_event_batch(
    batch: list[dict[str, Any]],
    *,
    root: Path,
    pa: Any,
    pq: Any,
) -> None:
    if not batch:
        return
    table = pa.Table.from_pylist(batch)
    pq.write_to_dataset(
        table,
        root_path=root,
        partition_cols=["ecosystem_id"],
        basename_template="part-{i}.parquet",
        existing_data_behavior="overwrite_or_ignore",
    )


def _flush_run_batch(batch: list[dict[str, Any]], *, root: Path, pa: Any, pq: Any) -> None:
    if not batch:
        return
    table = pa.Table.from_pylist(batch)
    pq.write_to_dataset(
        table,
        root_path=root,
        partition_cols=["ecosystem_id"],
        basename_template="part-{i}.parquet",
        existing_data_behavior="overwrite_or_ignore",
    )


def _flush_artifact_meta_batch(batch: list[dict[str, Any]], *, root: Path, pa: Any, pq: Any) -> None:
    if not batch:
        return
    table = pa.Table.from_pylist(batch)
    pq.write_to_dataset(
        table,
        root_path=root,
        partition_cols=["ecosystem_id"],
        basename_template="part-{i}.parquet",
        existing_data_behavior="overwrite_or_ignore",
    )


def run_batch_etl(
    *,
    base_dir: Path,
    out_root: Path,
    batch_label: str | None,
    chunk_size: int,
    write_research_bodies: bool,
) -> tuple[Path, ETLStats]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit(
            "batch_etl requires pyarrow. Install with: uv sync --extra etl"
        ) from exc

    batch_id = _utc_batch_id(batch_label)
    batch_dir = out_root / batch_id
    events_root = batch_dir / "tabular" / "events"
    runs_root = batch_dir / "tabular" / "runs"
    research_dir = batch_dir / "research"
    artifact_meta_root = research_dir / "artifact_metadata"
    research_dir.mkdir(parents=True, exist_ok=True)

    stats = ETLStats()
    event_batch: list[dict[str, Any]] = []
    run_batch: list[dict[str, Any]] = []
    artifact_batch: list[dict[str, Any]] = []

    bodies_path = research_dir / "artifact_bodies.jsonl"
    bodies_fp = bodies_path.open("w", encoding="utf-8") if write_research_bodies else None

    try:
        for jsonl_path in _iter_ecosystem_jsonl(base_dir):
            stats.jsonl_files_scanned += 1
            rel = jsonl_path.relative_to(base_dir).as_posix()
            with jsonl_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event_batch.append(_event_row(event, rel))
                    stats.event_rows += 1
                    if event.get("event_type") == "run.completed":
                        run_batch.append(_run_row(event))
                        stats.run_rows += 1
                    if len(event_batch) >= chunk_size:
                        _flush_event_batch(event_batch, root=events_root, pa=pa, pq=pq)
                        event_batch.clear()
                    if len(run_batch) >= chunk_size:
                        _flush_run_batch(run_batch, root=runs_root, pa=pa, pq=pq)
                        run_batch.clear()

        _flush_event_batch(event_batch, root=events_root, pa=pa, pq=pq)
        _flush_run_batch(run_batch, root=runs_root, pa=pa, pq=pq)

        for art_path in _iter_research_json(base_dir):
            stats.json_files_scanned += 1
            rel = art_path.relative_to(base_dir).as_posix()
            try:
                data = json.loads(art_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            artifact_batch.append(_artifact_meta_row(data, rel))
            stats.artifact_meta_rows += 1
            if bodies_fp is not None:
                aid = data.get("artifact_id") or art_path.stem
                bodies_fp.write(
                    json.dumps(
                        {
                            "artifact_id": aid,
                            "agent_id": data.get("agent_id"),
                            "ecosystem_id": data.get("ecosystem_id") or "unknown",
                            "content": data.get("content", ""),
                            "structured": data.get("structured"),
                            "source_file": rel,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stats.artifact_bodies_lines += 1
            if len(artifact_batch) >= chunk_size:
                _flush_artifact_meta_batch(
                    artifact_batch, root=artifact_meta_root, pa=pa, pq=pq
                )
                artifact_batch.clear()

        _flush_artifact_meta_batch(artifact_batch, root=artifact_meta_root, pa=pa, pq=pq)

    finally:
        if bodies_fp is not None:
            bodies_fp.close()

    manifest = {
        "batch_id": batch_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "base_dir": str(base_dir.resolve()),
        "event_rows": stats.event_rows,
        "run_rows": stats.run_rows,
        "artifact_meta_rows": stats.artifact_meta_rows,
        "artifact_bodies_lines": stats.artifact_bodies_lines,
        "jsonl_files_scanned": stats.jsonl_files_scanned,
        "json_files_scanned": stats.json_files_scanned,
        "outputs": {
            "events_parquet": str(events_root),
            "runs_parquet": str(runs_root),
            "research_metadata_parquet": str(artifact_meta_root),
            "research_bodies_jsonl": str(bodies_path) if write_research_bodies else None,
        },
    }
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    latest = out_root / "latest"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(batch_dir.resolve(), target_is_directory=True)
    except OSError:
        # Windows may require admin for symlinks; ignore.
        pass

    return batch_dir, stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch ETL: Parquet tabular merges + separate research extract"
    )
    parser.add_argument("--base-dir", default=".", help="Project root (contains ecosystems/)")
    parser.add_argument(
        "--out-dir",
        default="./etl_warehouse",
        help="Warehouse root; each run writes etl_warehouse/<batch_id>/",
    )
    parser.add_argument(
        "--batch-label",
        default=None,
        help="Optional label prefix for batch id (e.g. nightly)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50_000,
        help="Rows per Parquet flush for events/runs",
    )
    parser.add_argument(
        "--no-research-bodies",
        action="store_true",
        help="Skip research/artifact_bodies.jsonl (metadata Parquet only)",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    out_root = Path(args.out_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    batch_dir, stats = run_batch_etl(
        base_dir=base_dir,
        out_root=out_root,
        batch_label=args.batch_label,
        chunk_size=max(1000, args.chunk_size),
        write_research_bodies=not args.no_research_bodies,
    )

    print(f"Batch ETL complete: {batch_dir}")
    print(f"  events written:    {stats.event_rows}")
    print(f"  runs written:      {stats.run_rows}")
    print(f"  artifact metadata: {stats.artifact_meta_rows}")
    print(f"  artifact bodies:   {stats.artifact_bodies_lines} lines")
    print(f"  jsonl files:       {stats.jsonl_files_scanned}")
    print(f"  research json:     {stats.json_files_scanned}")


if __name__ == "__main__":
    main()
