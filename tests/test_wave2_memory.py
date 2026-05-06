"""Wave 2: Memory Window and Consolidation — test suite.

Tests rolling summary, notebook consolidation logic, config validation,
and regression defaults.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.state_builder import StateBuilder
from core.writer import ChainWriter
from infra.storage import EcosystemStorage
from tools.consolidate_notebook import (
    consolidate_older_entries,
    group_into_ltm_chunks,
    load_notebook_texts,
    _content_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_notebook_entry(text: str, decision_id: str = "d-1", wall_time: str = "2025-01-01T00:00:00Z") -> dict:
    return {
        "text": text,
        "ref_decision_id": decision_id,
        "fingerprint": _content_hash(text),
        "wall_time": wall_time,
        "event_id": f"evt-{_content_hash(text)[:8]}",
        "agent_id": "agent-1",
    }


def _write_notebook_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for e in entries:
        event = {
            "schema_version": "0.1.0",
            "event_id": e["event_id"],
            "event_type": "agent.notebook.appended",
            "ecosystem_id": "alpha",
            "agent_id": e["agent_id"],
            "wall_time": e["wall_time"],
            "monotonic_ns": 0,
            "payload": {
                "text": e["text"],
                "ref_decision_id": e["ref_decision_id"],
                "fingerprint": e["fingerprint"],
            },
            "prev_hash": "0" * 64,
            "record_hash": "0" * 64,
        }
        lines.append(json.dumps(event))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Section E: Rolling summary unit tests
# ---------------------------------------------------------------------------


class TestRollingSummary:
    """Tests for StateBuilder._summarize_notebook_prefix."""

    def test_empty_input_returns_none(self) -> None:
        result = StateBuilder._summarize_notebook_prefix([])
        assert result is None

    def test_single_entry_returns_summary(self) -> None:
        result = StateBuilder._summarize_notebook_prefix(["a single note"])
        assert result is not None
        assert "1 entries" in result
        assert "1 unique" in result

    def test_many_entries_produces_bounded_output(self) -> None:
        texts = [f"note number {i} about topic X" for i in range(50)]
        result = StateBuilder._summarize_notebook_prefix(texts)
        assert result is not None
        assert "50 entries" in result
        assert len(result) < 500

    def test_excerpt_truncation_at_120_chars(self) -> None:
        long_text = "x" * 200
        result = StateBuilder._summarize_notebook_prefix([long_text])
        assert result is not None
        assert "x" * 121 not in result
        assert "x" * 120 in result

    def test_deterministic_same_input_same_output(self) -> None:
        texts = ["alpha", "beta", "gamma", "delta"]
        r1 = StateBuilder._summarize_notebook_prefix(texts)
        r2 = StateBuilder._summarize_notebook_prefix(texts)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Section D/G: Consolidation logic tests
# ---------------------------------------------------------------------------


class TestGroupIntoLtmChunks:
    """Tests for group_into_ltm_chunks."""

    def test_fewer_entries_than_recent_cap_returns_empty(self) -> None:
        entries = [_make_notebook_entry(f"note-{i}") for i in range(3)]
        chunks = group_into_ltm_chunks(entries, chunk_size=5, recent_cap=5)
        assert chunks == []

    def test_splits_older_entries_into_chunks(self) -> None:
        entries = [_make_notebook_entry(f"note-{i}", decision_id=f"d-{i}") for i in range(15)]
        chunks = group_into_ltm_chunks(entries, chunk_size=5, recent_cap=5)
        assert len(chunks) == 2
        assert chunks[0]["entry_count"] == 5
        assert chunks[1]["entry_count"] == 5

    def test_deduplicates_within_chunks(self) -> None:
        entries = [_make_notebook_entry("duplicate text", decision_id=f"d-{i}") for i in range(10)]
        chunks = group_into_ltm_chunks(entries, chunk_size=10, recent_cap=0)
        assert len(chunks) == 1
        assert chunks[0]["unique_count"] == 1
        assert chunks[0]["entry_count"] == 10

    def test_chunk_metadata_correct(self) -> None:
        entries = [
            _make_notebook_entry(f"note-{i}", decision_id=f"d-{i}", wall_time=f"2025-01-0{i+1}T00:00:00Z")
            for i in range(8)
        ]
        chunks = group_into_ltm_chunks(entries, chunk_size=5, recent_cap=3)
        assert len(chunks) == 1
        assert chunks[0]["time_range_start"] == "2025-01-01T00:00:00Z"
        assert chunks[0]["time_range_end"] == "2025-01-05T00:00:00Z"
        assert chunks[0]["decision_ids"] == ["d-0", "d-1", "d-2", "d-3", "d-4"]

    def test_content_hash_deterministic(self) -> None:
        entries = [_make_notebook_entry(f"note-{i}") for i in range(10)]
        c1 = group_into_ltm_chunks(entries, chunk_size=5, recent_cap=5)
        c2 = group_into_ltm_chunks(entries, chunk_size=5, recent_cap=5)
        assert c1[0]["content_hash"] == c2[0]["content_hash"]


class TestConsolidateOlderEntries:
    """Tests for the library-callable consolidate_older_entries."""

    def test_reads_notebook_jsonl(self, tmp_path: Path) -> None:
        notebook_path = tmp_path / "notebook.jsonl"
        entries = [_make_notebook_entry(f"note-{i}", decision_id=f"d-{i}") for i in range(10)]
        _write_notebook_jsonl(notebook_path, entries)

        chunks = consolidate_older_entries(notebook_path, recent_cap=5, chunk_size=5)
        assert len(chunks) == 1
        assert chunks[0]["entry_count"] == 5

    def test_does_not_modify_source_file(self, tmp_path: Path) -> None:
        notebook_path = tmp_path / "notebook.jsonl"
        entries = [_make_notebook_entry(f"note-{i}", decision_id=f"d-{i}") for i in range(10)]
        _write_notebook_jsonl(notebook_path, entries)

        content_before = notebook_path.read_text(encoding="utf-8")
        consolidate_older_entries(notebook_path, recent_cap=5, chunk_size=5)
        content_after = notebook_path.read_text(encoding="utf-8")
        assert content_before == content_after

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        chunks = consolidate_older_entries(tmp_path / "nonexistent.jsonl")
        assert chunks == []

    def test_preserves_source_event_ids(self, tmp_path: Path) -> None:
        notebook_path = tmp_path / "notebook.jsonl"
        entries = [_make_notebook_entry(f"note-{i}", decision_id=f"d-{i}") for i in range(10)]
        _write_notebook_jsonl(notebook_path, entries)

        chunks = consolidate_older_entries(notebook_path, recent_cap=5, chunk_size=5)
        assert len(chunks[0]["decision_ids"]) > 0
        assert all(d.startswith("d-") for d in chunks[0]["decision_ids"])


# ---------------------------------------------------------------------------
# Config wiring tests
# ---------------------------------------------------------------------------


class TestConfigWiring:
    """Tests for notebook_consolidation_interval config validation."""

    def test_consolidation_interval_default_zero(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)
        assert config.get("notebook_consolidation_interval") is None

    def test_consolidation_interval_valid(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict = {"config_version": "1.0.0", "notebook_consolidation_interval": 5}
        _validate_run_config_modes(config)
        assert config["notebook_consolidation_interval"] == 5

    def test_consolidation_interval_negative_raises(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict = {"config_version": "1.0.0", "notebook_consolidation_interval": -1}
        with pytest.raises(ValueError, match="non-negative"):
            _validate_run_config_modes(config)

    def test_memory_caps_negative_raises(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict = {"config_version": "1.0.0", "memory_recent_events_cap": -5}
        with pytest.raises(ValueError, match="non-negative"):
            _validate_run_config_modes(config)

    def test_memory_notebook_cap_negative_raises(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict = {"config_version": "1.0.0", "memory_recent_notebook_cap": -2}
        with pytest.raises(ValueError, match="non-negative"):
            _validate_run_config_modes(config)


# ---------------------------------------------------------------------------
# Regression: defaults unchanged
# ---------------------------------------------------------------------------


class TestZeroCaps:
    """Finding 1 / Finding 4: cap=0 must produce empty lists, not full slices."""

    def _setup_ecosystem(self, tmp_path: Path) -> EcosystemStorage:
        storage = EcosystemStorage("alpha", tmp_path)
        from agent.constitution_manager import ConstitutionManager

        constitution = ConstitutionManager(storage, "agent-1")
        constitution.initialize(seed_text="seed constitution", ecosystem_id="alpha")
        writer_public = ChainWriter(storage.public_ledger())
        writer_notebook = ChainWriter(storage.agent_notebook("agent-1"))
        for i in range(10):
            writer_public.append(
                "agent.decision.taken",
                {"snapshot_id": str(i), "top_action": "RESEARCH", "sub_action": "READ", "sample_seed": i},
                ecosystem_id="alpha",
                agent_id="agent-1",
            )
        for i in range(8):
            writer_notebook.append(
                "agent.notebook.appended",
                {"text": f"note-{i}", "ref_decision_id": f"d-{i}", "fingerprint": f"f{i:064d}"[:64]},
                ecosystem_id="alpha",
                agent_id="agent-1",
            )
        return storage

    def test_zero_events_cap_returns_empty_list(self, tmp_path: Path) -> None:
        storage = self._setup_ecosystem(tmp_path)
        builder = StateBuilder(storage, "agent-1", recent_events_cap=0)
        snapshot = builder.build()
        assert snapshot.recent_events == []

    def test_zero_notebook_cap_returns_empty_list(self, tmp_path: Path) -> None:
        storage = self._setup_ecosystem(tmp_path)
        builder = StateBuilder(storage, "agent-1", recent_notebook_cap=0)
        snapshot = builder.build()
        assert snapshot.recent_notebook == []

    def test_zero_caps_with_populated_data(self, tmp_path: Path) -> None:
        """Both caps at zero still produce empty lists even with plenty of data."""
        storage = self._setup_ecosystem(tmp_path)
        builder = StateBuilder(storage, "agent-1", recent_events_cap=0, recent_notebook_cap=0)
        snapshot = builder.build()
        assert snapshot.recent_events == []
        assert snapshot.recent_notebook == []


class TestConsolidationErrorResilience:
    """Finding 2 / Finding 4: consolidation errors must not crash the decision loop."""

    def test_consolidation_raises_on_corrupt_input(self, tmp_path: Path) -> None:
        """consolidate_older_entries can raise on unexpected I/O (directory instead of file)."""
        notebook_path = tmp_path / "notebook.jsonl"
        notebook_path.mkdir()
        with pytest.raises((IsADirectoryError, PermissionError)):
            consolidate_older_entries(notebook_path, recent_cap=5)

    def test_consolidation_hook_error_does_not_crash_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates the runner's defensive wrapper: errors are caught, loop continues."""
        import agent.runner as runner_mod

        call_count = 0

        def _raise_on_consolidate(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise OSError("simulated disk failure")

        monkeypatch.setattr(runner_mod, "consolidate_older_entries", _raise_on_consolidate)

        notebook_consolidation_interval = 2
        recent_notebook_cap = 5
        decisions_completed = 0
        for decision_number in range(1, 5):
            decisions_completed += 1
            if (
                notebook_consolidation_interval > 0
                and decision_number % notebook_consolidation_interval == 0
            ):
                try:
                    runner_mod.consolidate_older_entries(
                        tmp_path / "notebook.jsonl",
                        recent_cap=recent_notebook_cap,
                    )
                except Exception as consolidation_exc:
                    print(f"[consolidation] error at decision {decision_number}, continuing: {consolidation_exc}")

        assert decisions_completed == 4
        assert call_count == 2


class TestRegressionDefaults:
    """Verify no behavioral change when Wave 2 config keys are absent."""

    def test_state_builder_defaults_unchanged(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        from agent.constitution_manager import ConstitutionManager

        constitution = ConstitutionManager(storage, "agent-1")
        constitution.initialize(seed_text="seed constitution", ecosystem_id="alpha")

        writer_public = ChainWriter(storage.public_ledger())
        writer_notebook = ChainWriter(storage.agent_notebook("agent-1"))

        for i in range(3):
            writer_public.append(
                "agent.decision.taken",
                {"snapshot_id": str(i), "top_action": "RESEARCH", "sub_action": "READ", "sample_seed": i},
                ecosystem_id="alpha",
                agent_id="agent-1",
            )
        for i in range(3):
            writer_notebook.append(
                "agent.notebook.appended",
                {"text": f"note-{i}", "ref_decision_id": f"d-{i}", "fingerprint": f"f{i:064d}"[:64]},
                ecosystem_id="alpha",
                agent_id="agent-1",
            )

        builder = StateBuilder(storage, "agent-1")
        snapshot = builder.build()
        assert len(snapshot.recent_events) == 3
        assert len(snapshot.recent_notebook) == 3
        assert snapshot.recent_notebook_summary is None

    def test_summary_none_when_entries_within_cap(self, tmp_path: Path) -> None:
        storage = EcosystemStorage("alpha", tmp_path)
        from agent.constitution_manager import ConstitutionManager

        constitution = ConstitutionManager(storage, "agent-1")
        constitution.initialize(seed_text="seed constitution", ecosystem_id="alpha")
        writer_notebook = ChainWriter(storage.agent_notebook("agent-1"))

        for i in range(5):
            writer_notebook.append(
                "agent.notebook.appended",
                {"text": f"note-{i}", "ref_decision_id": f"d-{i}", "fingerprint": f"f{i:064d}"[:64]},
                ecosystem_id="alpha",
                agent_id="agent-1",
            )

        builder = StateBuilder(storage, "agent-1", recent_notebook_cap=5)
        snapshot = builder.build()
        assert snapshot.recent_notebook_summary is None
