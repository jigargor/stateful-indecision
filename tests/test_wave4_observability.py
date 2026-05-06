"""Wave 4 — Observability and Evolution.

Tests for:
- SQL export produces expected tables/columns
- Grafana starter queries are syntactically valid SQL against a real schema
- Trajectory export produces valid JSONL with expected fields (18 fields)
- Dashboard template is valid JSON with expected structure
- New Wave 4 queries (10-13) return expected columns
- Trajectory export handles empty ecosystems and missing executions gracefully
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from tools.export_to_sqlite import _create_tables, export
from tools.export_trajectories import build_trajectories, load_jsonl

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GRAFANA_QUERIES_PATH = PROJECT_ROOT / "tools" / "grafana_starter_queries.sql"
DASHBOARD_TEMPLATE_PATH = PROJECT_ROOT / "tools" / "grafana_dashboard_template.json"

EXPECTED_TRAJECTORY_FIELDS = {
    "ecosystem_id",
    "agent_id",
    "decision_event_id",
    "decision_number",
    "snapshot_id",
    "top_action",
    "sub_action",
    "sample_seed",
    "raw_output",
    "structured_output",
    "side_effects",
    "tokens_in",
    "tokens_out",
    "stop_reason",
    "latency_ms",
    "evaluation_outcome",
    "run_config_version",
    "wall_time",
}


def _make_decision_event(
    ecosystem_id: str,
    agent_id: str,
    event_id: str,
    top_action: str = "research",
    wall_time: str = "2026-01-01T00:00:00Z",
    decision_number: int = 0,
) -> dict:
    return {
        "event_id": event_id,
        "schema_version": "0.1.0",
        "event_type": "agent.decision.taken",
        "ecosystem_id": ecosystem_id,
        "agent_id": agent_id,
        "wall_time": wall_time,
        "monotonic_ns": int(time.time() * 1e9),
        "prev_hash": "0" * 64,
        "record_hash": "a" * 64,
        "payload": {
            "snapshot_id": f"snap-{event_id}",
            "top_action": top_action,
            "sub_action": None,
            "sample_seed": 42,
        },
    }


def _make_execution_event(
    ecosystem_id: str,
    agent_id: str,
    event_id: str,
    decision_event_id: str,
    wall_time: str = "2026-01-01T00:00:01Z",
    tokens_in: int = 500,
    tokens_out: int = 200,
    stop_reason: str = "end_turn",
    wall_start_ms: float = 1000.0,
    wall_end_ms: float = 3500.0,
) -> dict:
    return {
        "event_id": event_id,
        "schema_version": "0.1.0",
        "event_type": "action.executed",
        "ecosystem_id": ecosystem_id,
        "agent_id": agent_id,
        "wall_time": wall_time,
        "monotonic_ns": int(time.time() * 1e9),
        "prev_hash": "a" * 64,
        "record_hash": "b" * 64,
        "payload": {
            "decision_event_id": decision_event_id,
            "raw_output": "test output",
            "structured": {"key": "value"},
            "side_effects": [],
            "metrics": {
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "stop_reason": stop_reason,
                "wall_start_ms": wall_start_ms,
                "wall_end_ms": wall_end_ms,
            },
        },
    }


def _make_run_completed_event(
    ecosystem_id: str,
    agent_id: str,
    event_id: str,
    run_config_version: str = "v1.0",
    wall_time: str = "2026-01-01T01:00:00Z",
) -> dict:
    return {
        "event_id": event_id,
        "schema_version": "0.1.0",
        "event_type": "run.completed",
        "ecosystem_id": ecosystem_id,
        "agent_id": agent_id,
        "wall_time": wall_time,
        "monotonic_ns": int(time.time() * 1e9),
        "prev_hash": "b" * 64,
        "record_hash": "c" * 64,
        "payload": {
            "decisions_completed": 3,
            "run_seed": 123,
            "field_chosen": "research",
            "constitution_revision_count": 1,
            "artifacts_stored": 2,
            "notebook_entries": 5,
            "run_config_version": run_config_version,
        },
    }


def _make_evaluation_event(
    ecosystem_id: str,
    decision_event_id: str,
    outcome: str = "pass",
) -> dict:
    return {
        "event_id": f"eval-{decision_event_id}",
        "schema_version": "0.1.0",
        "event_type": "safety.trigger.evaluated",
        "ecosystem_id": ecosystem_id,
        "agent_id": None,
        "wall_time": "2026-01-01T00:00:02Z",
        "monotonic_ns": int(time.time() * 1e9),
        "prev_hash": "c" * 64,
        "record_hash": "d" * 64,
        "payload": {
            "source_event_type": "agent.decision.taken",
            "source_event_id": decision_event_id,
            "outcome": outcome,
            "mode": "evaluate",
            "reward_mode": "default",
            "reward_signal": 1.0,
        },
    }


def _write_events_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def _build_test_db(events: list[dict]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    _create_tables(conn)
    for event in events:
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
                "test",
            ),
        )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# SQL export: tables and columns
# ---------------------------------------------------------------------------

class TestSQLExportSchema:
    def test_create_tables_produces_expected_tables(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"events", "artifacts", "runs", "research_manifest"}.issubset(tables)

    def test_events_table_has_expected_columns(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }
        expected = {
            "event_id", "schema_version", "event_type", "ecosystem_id",
            "agent_id", "wall_time", "monotonic_ns", "prev_hash",
            "record_hash", "payload_json", "source_file",
        }
        assert expected.issubset(columns)

    def test_runs_table_has_expected_columns(self):
        conn = sqlite3.connect(":memory:")
        _create_tables(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(runs)").fetchall()
        }
        expected = {
            "event_id", "ecosystem_id", "agent_id", "decisions_completed",
            "run_seed", "field_chosen", "run_config_version", "wall_time",
        }
        assert expected.issubset(columns)

    def test_export_function_with_synthetic_data(self, tmp_path):
        eco_dir = tmp_path / "ecosystems" / "test"
        eco_dir.mkdir(parents=True)
        events = [
            _make_decision_event("test", "agent-1", "d1"),
            _make_execution_event("test", "agent-1", "e1", "d1"),
            _make_run_completed_event("test", "agent-1", "r1"),
        ]
        _write_events_jsonl(eco_dir / "public.jsonl", events)

        db_path = tmp_path / "test.db"
        stats = export(tmp_path, db_path)
        assert stats["events"] >= 3
        assert stats["runs"] >= 1

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        assert rows[0] >= 3
        conn.close()


# ---------------------------------------------------------------------------
# Grafana queries: syntactic validity
# ---------------------------------------------------------------------------

def _parse_sql_queries(sql_text: str) -> list[str]:
    """Split the starter queries file into individual SQL statements."""
    queries = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            if current and any(l.strip() for l in current):
                queries.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current and any(l.strip() for l in current):
        queries.append("\n".join(current))
    return [q.strip().rstrip(";") for q in queries if q.strip()]


class TestGrafanaQueries:
    @pytest.fixture()
    def test_db(self):
        events = [
            _make_decision_event("alpha", "agent-1", f"d{i}", wall_time=f"2026-01-01T{i:02d}:00:00Z")
            for i in range(5)
        ] + [
            _make_execution_event(
                "alpha", "agent-1", f"e{i}", f"d{i}",
                wall_time=f"2026-01-01T{i:02d}:00:01Z",
                wall_start_ms=1000.0 + i * 100,
                wall_end_ms=3000.0 + i * 200,
            )
            for i in range(5)
        ] + [
            _make_run_completed_event("alpha", "agent-1", "r1"),
        ]
        return _build_test_db(events)

    def test_all_queries_are_syntactically_valid(self, test_db):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        assert len(queries) >= 13, f"Expected at least 13 queries, found {len(queries)}"
        for i, query in enumerate(queries, 1):
            try:
                test_db.execute(query)
            except sqlite3.OperationalError as exc:
                pytest.fail(f"Query {i} failed: {exc}\nSQL:\n{query[:200]}")

    def test_all_queries_are_select_only(self):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"}
        for i, query in enumerate(queries, 1):
            upper = query.upper().strip()
            for kw in forbidden:
                if upper.startswith(kw):
                    pytest.fail(f"Query {i} starts with forbidden keyword {kw}")

    def test_latency_query_returns_expected_columns(self, test_db):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        query_10 = queries[9]
        cursor = test_db.execute(query_10)
        col_names = {desc[0] for desc in cursor.description}
        expected = {"ecosystem_id", "agent_id", "sample_count", "p50_latency_ms", "p95_latency_ms"}
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_token_aggregation_query(self, test_db):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        query_11 = queries[10]
        cursor = test_db.execute(query_11)
        col_names = {desc[0] for desc in cursor.description}
        expected = {"ecosystem_id", "agent_id", "executions", "total_tokens_in", "total_tokens_out", "avg_tokens_per_decision"}
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"
        rows = cursor.fetchall()
        assert len(rows) >= 1

    def test_stop_reason_time_bucket_query(self, test_db):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        query_12 = queries[11]
        cursor = test_db.execute(query_12)
        col_names = {desc[0] for desc in cursor.description}
        expected = {"hour_bucket", "ecosystem_id", "stop_reason", "event_count"}
        assert expected.issubset(col_names)

    def test_action_mix_time_bucket_query(self, test_db):
        sql_text = GRAFANA_QUERIES_PATH.read_text(encoding="utf-8")
        queries = _parse_sql_queries(sql_text)
        query_13 = queries[12]
        cursor = test_db.execute(query_13)
        col_names = {desc[0] for desc in cursor.description}
        expected = {"hour_bucket", "ecosystem_id", "top_action", "decisions"}
        assert expected.issubset(col_names)


# ---------------------------------------------------------------------------
# Dashboard template: JSON validity and structure
# ---------------------------------------------------------------------------

class TestDashboardTemplate:
    @pytest.fixture()
    def dashboard(self):
        return json.loads(DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8"))

    def test_valid_json(self):
        data = json.loads(DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_has_expected_top_level_keys(self, dashboard):
        for key in ("panels", "title", "schemaVersion", "tags"):
            assert key in dashboard, f"Missing top-level key: {key}"

    def test_has_expected_panel_count(self, dashboard):
        assert len(dashboard["panels"]) == 9

    def test_no_duplicate_panel_ids(self, dashboard):
        ids = [p["id"] for p in dashboard["panels"]]
        assert len(ids) == len(set(ids)), f"Duplicate panel IDs: {ids}"

    def test_panel_ids_are_1_through_9(self, dashboard):
        ids = sorted(p["id"] for p in dashboard["panels"])
        assert ids == list(range(1, 10))

    def test_no_overlapping_grid_positions(self, dashboard):
        occupied = set()
        for panel in dashboard["panels"]:
            gp = panel["gridPos"]
            for dx in range(gp["w"]):
                for dy in range(gp["h"]):
                    cell = (gp["x"] + dx, gp["y"] + dy)
                    assert cell not in occupied, (
                        f"Panel {panel['id']} overlaps at cell {cell}"
                    )
                    occupied.add(cell)

    def test_all_panel_sql_is_select_only(self, dashboard):
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                raw_sql = target.get("rawSql", "")
                upper = raw_sql.strip().upper()
                assert not any(
                    upper.startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP")
                ), f"Panel {panel['id']} contains non-SELECT SQL"

    def test_wave4_panels_present(self, dashboard):
        titles = {p["title"] for p in dashboard["panels"]}
        expected = {
            "Decision Latency Distribution (p50/p95)",
            "Tokens per Decision by Agent",
            "Stop Reason Mix Over Time",
            "Action Mix Over Time",
        }
        assert expected.issubset(titles), f"Missing panels: {expected - titles}"


# ---------------------------------------------------------------------------
# Trajectory export: field presence and correctness
# ---------------------------------------------------------------------------

class TestTrajectoryExport:
    def _make_events(self) -> list[dict]:
        return [
            _make_decision_event("beta", "agent-1", "d1", wall_time="2026-01-01T00:00:00Z"),
            _make_execution_event("beta", "agent-1", "e1", "d1"),
            _make_decision_event("beta", "agent-1", "d2", top_action="commons", wall_time="2026-01-01T01:00:00Z"),
            _make_execution_event("beta", "agent-1", "e2", "d2", tokens_in=800, tokens_out=300, stop_reason="max_tokens"),
            _make_run_completed_event("beta", "agent-1", "r1", run_config_version="v2.1"),
        ]

    def test_trajectory_has_all_expected_fields(self):
        events = self._make_events()
        trajectories = build_trajectories(events, "beta")
        assert len(trajectories) == 2
        for row in trajectories:
            assert set(row.keys()) == EXPECTED_TRAJECTORY_FIELDS

    def test_decision_number_is_sequential(self):
        events = self._make_events()
        trajectories = build_trajectories(events, "beta")
        numbers = [t["decision_number"] for t in trajectories]
        assert numbers == [0, 1]

    def test_latency_ms_computed(self):
        events = self._make_events()
        trajectories = build_trajectories(events, "beta")
        for row in trajectories:
            assert row["latency_ms"] is not None
            assert row["latency_ms"] > 0

    def test_run_config_version_propagated(self):
        events = self._make_events()
        trajectories = build_trajectories(events, "beta")
        for row in trajectories:
            assert row["run_config_version"] == "v2.1"

    def test_evaluation_outcome_joined(self):
        events = self._make_events()
        eval_events = [_make_evaluation_event("beta", "d1", "pass")]
        trajectories = build_trajectories(events, "beta", eval_events)
        d1_row = next(t for t in trajectories if t["decision_event_id"] == "d1")
        d2_row = next(t for t in trajectories if t["decision_event_id"] == "d2")
        assert d1_row["evaluation_outcome"] == "pass"
        assert d2_row["evaluation_outcome"] is None

    def test_empty_ecosystem_produces_empty_output(self):
        events = self._make_events()
        trajectories = build_trajectories(events, "nonexistent")
        assert trajectories == []

    def test_decision_without_execution_degrades_gracefully(self):
        events = [
            _make_decision_event("beta", "agent-1", "d-orphan"),
        ]
        trajectories = build_trajectories(events, "beta")
        assert len(trajectories) == 1
        row = trajectories[0]
        assert row["raw_output"] is None
        assert row["tokens_in"] is None
        assert row["latency_ms"] is None
        assert row["stop_reason"] is None
        assert row["side_effects"] == []

    def test_ecosystem_filtering(self):
        events = [
            _make_decision_event("alpha", "agent-1", "d-alpha"),
            _make_decision_event("beta", "agent-1", "d-beta"),
        ]
        alpha_traj = build_trajectories(events, "alpha")
        beta_traj = build_trajectories(events, "beta")
        assert len(alpha_traj) == 1
        assert alpha_traj[0]["ecosystem_id"] == "alpha"
        assert len(beta_traj) == 1
        assert beta_traj[0]["ecosystem_id"] == "beta"

    def test_load_jsonl_missing_file(self, tmp_path):
        result = load_jsonl(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_jsonl_round_trip(self, tmp_path):
        events = self._make_events()
        trajectories = build_trajectories(events, "beta")
        out_path = tmp_path / "out.jsonl"
        with out_path.open("w") as f:
            for row in trajectories:
                f.write(json.dumps(row) + "\n")
        loaded = load_jsonl(out_path)
        assert len(loaded) == len(trajectories)
        for row in loaded:
            assert set(row.keys()) == EXPECTED_TRAJECTORY_FIELDS
