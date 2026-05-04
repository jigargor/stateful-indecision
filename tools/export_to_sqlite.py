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


def export(base_dir: Path, db_path: Path) -> dict[str, int]:
    ecosystems_dir = base_dir / "ecosystems"
    conn = sqlite3.connect(str(db_path))
    _create_tables(conn)

    stats = {"events": 0, "artifacts": 0, "runs": 0}

    if ecosystems_dir.exists():
        for jsonl_file in ecosystems_dir.rglob("*.jsonl"):
            count = _ingest_jsonl(conn, jsonl_file)
            stats["events"] += count

        for research_json in ecosystems_dir.rglob("research/*.json"):
            if _ingest_artifact(conn, research_json):
                stats["artifacts"] += 1

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
    print(f"  events:    {stats['events']}")
    print(f"  artifacts: {stats['artifacts']}")
    print(f"  runs:      {stats['runs']}")


if __name__ == "__main__":
    main()
