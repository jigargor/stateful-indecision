"""Tests for S3 sync cursor logic, newline boundary safety, and EcosystemStorage extensions.

These tests do NOT require boto3 or AWS credentials -- they test the local
data-preparation logic that feeds into the upload path.
"""
from __future__ import annotations

import json
from pathlib import Path

from infra.s3_sync import (
    LedgerCursor,
    S3SyncConfig,
    SyncState,
    _parse_last_record_meta,
    load_state,
    read_newline_bounded_slice,
    save_state,
)
from infra.storage import EcosystemStorage


def _make_jsonl_line(event_id: str, record_hash: str) -> str:
    return json.dumps({
        "event_id": event_id,
        "event_type": "test",
        "record_hash": record_hash,
        "prev_hash": "0" * 64,
    })


class TestReadNewlineBoundedSlice:
    """Validates the checker requirement: never upload partial lines."""

    def test_returns_empty_when_start_at_end(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"line1\nline2\n")
        result = read_newline_bounded_slice(f, f.stat().st_size)
        assert result == b""

    def test_returns_empty_when_start_past_end(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"line1\n")
        result = read_newline_bounded_slice(f, 9999)
        assert result == b""

    def test_returns_complete_lines_only(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"line1\nline2\npartial")
        result = read_newline_bounded_slice(f, 0)
        assert result == b"line1\nline2\n"

    def test_returns_empty_when_no_newline(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"no-newline-here")
        result = read_newline_bounded_slice(f, 0)
        assert result == b""

    def test_incremental_from_offset(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"line1\nline2\nline3\n")
        offset = len(b"line1\n")
        result = read_newline_bounded_slice(f, offset)
        assert result == b"line2\nline3\n"

    def test_partial_last_line_excluded_from_offset(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"line1\nline2\nincomplete")
        offset = len(b"line1\n")
        result = read_newline_bounded_slice(f, offset)
        assert result == b"line2\n"

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "ledger.jsonl"
        f.write_bytes(b"")
        result = read_newline_bounded_slice(f, 0)
        assert result == b""


class TestParseLastRecordMeta:
    def test_extracts_event_id_and_hash(self) -> None:
        h = "a" * 64
        line = _make_jsonl_line("evt-1", h)
        result = _parse_last_record_meta(line.encode() + b"\n")
        assert result == ("evt-1", h)

    def test_returns_last_line_when_multiple(self) -> None:
        h1 = "a" * 64
        h2 = "b" * 64
        chunk = (_make_jsonl_line("evt-1", h1) + "\n" + _make_jsonl_line("evt-2", h2) + "\n").encode()
        result = _parse_last_record_meta(chunk)
        assert result is not None
        assert result[0] == "evt-2"
        assert result[1] == h2

    def test_returns_none_for_invalid_json(self) -> None:
        result = _parse_last_record_meta(b"not json\n")
        assert result is None

    def test_returns_none_for_short_hash(self) -> None:
        line = json.dumps({"event_id": "x", "record_hash": "short"})
        result = _parse_last_record_meta(line.encode() + b"\n")
        assert result is None

    def test_returns_none_for_empty(self) -> None:
        result = _parse_last_record_meta(b"")
        assert result is None


class TestSyncStatePersistence:
    def test_round_trip(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        state = SyncState(
            ecosystem_id="alpha",
            cursors={
                "public.jsonl": LedgerCursor(
                    rel_path="public.jsonl",
                    uploaded_through_byte_offset=1024,
                    uploaded_through_record_hash="c" * 64,
                    last_event_id="evt-99",
                    s3_key="ecosystems/alpha/public.jsonl",
                ),
            },
            research_bundles={"agent-001": ["001_write.json"]},
        )
        save_state(state_path, state)
        loaded = load_state(state_path)
        assert loaded.ecosystem_id == "alpha"
        assert "public.jsonl" in loaded.cursors
        assert loaded.cursors["public.jsonl"].uploaded_through_byte_offset == 1024
        assert loaded.research_bundles["agent-001"] == ["001_write.json"]

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        state = load_state(tmp_path / "nonexistent.json")
        assert state.ecosystem_id == ""
        assert state.cursors == {}

    def test_state_path_created(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "state.json"
        save_state(nested, SyncState(ecosystem_id="beta"))
        assert nested.exists()


class TestS3SyncConfig:
    def test_defaults(self) -> None:
        cfg = S3SyncConfig(bucket="test-bucket")
        assert cfg.prefix == ""
        assert cfg.sse_mode == "sse-s3"
        assert cfg.research_mode == "bundle"
        assert cfg.shutdown_max_sec == 90
        assert cfg.sync_interval_sec == 300


class TestEcosystemStorageExtensions:
    def test_syncable_ledger_paths_returns_five(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        paths = storage.syncable_ledger_paths()
        assert len(paths) == 5
        names = {p.name for p in paths}
        assert names == {
            "public.jsonl",
            "evaluation.jsonl",
            "commons.jsonl",
            "roundtable.jsonl",
            "townhall.jsonl",
        }

    def test_syncable_paths_stay_within_firewall(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        eco_dir = str(storage.ecosystem_dir)
        for p in storage.syncable_ledger_paths():
            assert str(p).startswith(eco_dir)

    def test_iter_agent_ids_empty(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("beta", tmp_path)
        assert storage.iter_agent_ids() == []

    def test_iter_agent_ids_finds_agents(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        (storage.ecosystem_dir / "agents" / "agent-a").mkdir(parents=True)
        (storage.ecosystem_dir / "agents" / "agent-b").mkdir(parents=True)
        ids = storage.iter_agent_ids()
        assert ids == ["agent-a", "agent-b"]

    def test_agent_sync_paths_returns_expected_keys(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        paths = storage.agent_sync_paths("test-agent")
        assert set(paths.keys()) == {"notebook", "constitution", "research_dir"}
        assert paths["notebook"].name == "notebook.jsonl"
        assert paths["constitution"].name == "constitution.md"
        assert paths["research_dir"].name == "research"
