"""Export ecosystem ledgers and research artifacts to SQLite for Grafana dashboards.

Usage:
    python -m tools.export_to_sqlite [--db dashboard.db] [--base-dir .]

Tables created:
    events     — flattened JSONL events from all ledgers
    artifacts  — research JSON artifact files
    runs       — extracted from run.completed events
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            schema_version TEXT,
            event_type TEXT NOT NULL,
            ecosystem_id TEXT NOT NULL,
            agent_id TEXT,
            wall_time TEXT,
            monotonic_ns INTEGER,
            prev_hash TEXT,
            record_hash TEXT,
            payload_json TEXT,
            source_file TEXT
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            ecosystem_id TEXT NOT NULL,
            snapshot_id TEXT,
            action TEXT,
            config_version TEXT,
            content TEXT,
            structured_json TEXT,
            created_at TEXT,
            source_file TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
            event_id TEXT PRIMARY KEY,
            ecosystem_id TEXT NOT NULL,
            agent_id TEXT,
            decisions_completed INTEGER,
            run_seed INTEGER,
            field_chosen TEXT,
            constitution_revision_count INTEGER,
            artifacts_stored INTEGER,
            notebook_entries INTEGER,
            run_config_version TEXT,
            wall_time TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_ecosystem ON events(ecosystem_id);
        CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id);
        CREATE INDEX IF NOT EXISTS idx_artifacts_agent ON artifacts(agent_id);
        CREATE INDEX IF NOT EXISTS idx_runs_ecosystem ON runs(ecosystem_id);

        CREATE TABLE IF NOT EXISTS research_manifest (
            content_hash TEXT PRIMARY KEY,
            artifact_id TEXT,
            agent_id TEXT NOT NULL,
            ecosystem_id TEXT NOT NULL,
            action TEXT,
            config_version TEXT,
            created_at TEXT,
            snapshot_id TEXT,
            content TEXT,
            summary TEXT,
            source_path TEXT,
            source_type TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_manifest_agent ON research_manifest(agent_id);
        CREATE INDEX IF NOT EXISTS idx_manifest_action ON research_manifest(action);
    """)


def _ingest_jsonl(conn: sqlite3.Connection, jsonl_path: Path) -> int:
    count = 0
    relative = str(jsonl_path)
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO events
               (event_id, schema_version, event_type, ecosystem_id, agent_id,
                wall_time, monotonic_ns, prev_hash, record_hash, payload_json, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.get("event_id"),
                event.get("schema_version"),
                event.get("event_type"),
                event.get("ecosystem_id"),
                event.get("agent_id"),
                event.get("wall_time"),
                event.get("monotonic_ns"),
                event.get("prev_hash"),
                event.get("record_hash"),
                json.dumps(event.get("payload", {})),
                relative,
            ),
        )
        count += 1

        if event.get("event_type") == "run.completed":
            payload = event.get("payload", {})
            conn.execute(
                """INSERT OR IGNORE INTO runs
                   (event_id, ecosystem_id, agent_id, decisions_completed, run_seed,
                    field_chosen, constitution_revision_count, artifacts_stored,
                    notebook_entries, run_config_version, wall_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.get("event_id"),
                    event.get("ecosystem_id"),
                    event.get("agent_id"),
                    payload.get("decisions_completed"),
                    payload.get("run_seed"),
                    payload.get("field_chosen"),
                    payload.get("constitution_revision_count"),
                    payload.get("artifacts_stored"),
                    payload.get("notebook_entries"),
                    payload.get("run_config_version"),
                    event.get("wall_time"),
                ),
            )
    return count


def _ingest_artifact(conn: sqlite3.Connection, artifact_path: Path) -> bool:
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False

    conn.execute(
        """INSERT OR IGNORE INTO artifacts
           (artifact_id, agent_id, ecosystem_id, snapshot_id, action,
            config_version, content, structured_json, created_at, source_file)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("artifact_id"),
            data.get("agent_id"),
            data.get("ecosystem_id"),
            data.get("snapshot_id"),
            data.get("action"),
            data.get("config_version"),
            data.get("content"),
            json.dumps(data.get("structured")) if data.get("structured") else None,
            data.get("created_at"),
            str(artifact_path),
        ),
    )
    return True


def _ingest_manifest(conn: sqlite3.Connection, manifest_path: Path) -> int:
    if not manifest_path.exists():
        return 0
    count = 0
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO research_manifest
               (content_hash, artifact_id, agent_id, ecosystem_id, action,
                config_version, created_at, snapshot_id, content, summary,
                source_path, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("content_hash"),
                entry.get("artifact_id"),
                entry.get("agent_id"),
                entry.get("ecosystem_id"),
                entry.get("action"),
                entry.get("config_version"),
                entry.get("created_at"),
                entry.get("snapshot_id"),
                entry.get("content"),
                entry.get("summary"),
                entry.get("source_path"),
                entry.get("source_type"),
            ),
        )
        count += 1
    return count


def export(base_dir: Path, db_path: Path) -> dict[str, int]:
    ecosystems_dir = base_dir / "ecosystems"
    conn = sqlite3.connect(str(db_path))
    _create_tables(conn)

    stats = {"events": 0, "artifacts": 0, "runs": 0, "manifest_entries": 0}

    if ecosystems_dir.exists():
        for jsonl_file in ecosystems_dir.rglob("*.jsonl"):
            count = _ingest_jsonl(conn, jsonl_file)
            stats["events"] += count

        for research_json in ecosystems_dir.rglob("research/*.json"):
            if _ingest_artifact(conn, research_json):
                stats["artifacts"] += 1

    sync_state_dir = base_dir / ".sync_state"
    if sync_state_dir.exists():
        for manifest in sync_state_dir.glob("*_research_manifest.jsonl"):
            count = _ingest_manifest(conn, manifest)
            stats["manifest_entries"] += count

    conn.commit()

    cursor = conn.execute("SELECT COUNT(*) FROM runs")
    stats["runs"] = cursor.fetchone()[0]

    conn.close()
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export ledgers to SQLite for Grafana")
    parser.add_argument("--db", default="dashboard.db", help="Output SQLite database path")
    parser.add_argument("--base-dir", default=".", help="Project base directory")
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    db_path = Path(args.db).resolve()

    stats = export(base_dir, db_path)
    print(f"Exported to {db_path}:")
    print(f"  events:           {stats['events']}")
    print(f"  artifacts:        {stats['artifacts']}")
    print(f"  runs:             {stats['runs']}")
    print(f"  manifest_entries: {stats['manifest_entries']}")


if __name__ == "__main__":
    main()
