from __future__ import annotations

import json
from pathlib import Path

import pytest

pyarrow = pytest.importorskip("pyarrow")
pytest.importorskip("pyarrow.parquet")

from tools.batch_etl import run_batch_etl


def test_batch_etl_writes_parquet_and_manifest(tmp_path: Path) -> None:
    base = tmp_path / "proj"
    eco = base / "ecosystems" / "alpha"
    agents = eco / "agents" / "agent-1" / "research"
    agents.mkdir(parents=True)
    pub = eco / "public.jsonl"
    pub.write_text(
        json.dumps(
            {
                "event_id": "e1",
                "schema_version": "0.1.0",
                "event_type": "agent.decision.taken",
                "ecosystem_id": "alpha",
                "agent_id": "agent-1",
                "wall_time": "2026-01-01T00:00:00Z",
                "monotonic_ns": 1,
                "prev_hash": "0" * 64,
                "record_hash": "1" * 64,
                "payload": {"top_action": "RIFF"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "event_id": "e2",
                "schema_version": "0.1.0",
                "event_type": "run.completed",
                "ecosystem_id": "alpha",
                "agent_id": "agent-1",
                "wall_time": "2026-01-01T00:01:00Z",
                "monotonic_ns": 2,
                "prev_hash": "1" * 64,
                "record_hash": "2" * 64,
                "payload": {
                    "decisions_completed": 3,
                    "run_seed": 99,
                    "field_chosen": "test_field",
                    "run_config_version": "0.0.1",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    art = agents / "a1.json"
    art.write_text(
        json.dumps(
            {
                "artifact_id": "art-1",
                "agent_id": "agent-1",
                "ecosystem_id": "alpha",
                "content": "hello world",
                "structured": {"k": 1},
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "warehouse"
    batch_dir, stats = run_batch_etl(
        base_dir=base,
        out_root=out,
        batch_label="test",
        chunk_size=1000,
        write_research_bodies=True,
    )

    assert stats.event_rows == 2
    assert stats.run_rows == 1
    assert stats.artifact_meta_rows == 1
    assert stats.artifact_bodies_lines == 1

    manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["event_rows"] == 2
    assert manifest["run_rows"] == 1

    events_parts = list((batch_dir / "tabular" / "events").rglob("*.parquet"))
    assert events_parts, "expected partitioned events parquet"
    t = pyarrow.parquet.read_table(events_parts[0])
    assert t.num_rows >= 1

    bodies = (batch_dir / "research" / "artifact_bodies.jsonl").read_text(encoding="utf-8").strip()
    row = json.loads(bodies.splitlines()[0])
    assert row["artifact_id"] == "art-1"
    assert row["content"] == "hello world"
