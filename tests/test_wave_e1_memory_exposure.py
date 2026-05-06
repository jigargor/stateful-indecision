"""Wave E1 — Memory exposure controls.

Tests for:
- cap enforcement (including boundary values)
- provenance field presence and structure
- graceful fallback with empty/missing data
- prompt block inclusion/exclusion logic (via real Executor)
- regression: default behavior remains unchanged
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adapters.mock import MockAdapter
from agent.constitution_manager import ConstitutionManager
from agent.executor import Executor
from agent.state_builder import ContextSegment, StateBuilder, StateSnapshot, _truncate_to_cap
from core.writer import ChainWriter
from infra.storage import EcosystemStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_ecosystem(tmp_path: Path, ecosystem_id: str = "alpha") -> EcosystemStorage:
    storage = EcosystemStorage(ecosystem_id, tmp_path)
    return storage


def _init_agent(storage: EcosystemStorage, agent_id: str) -> None:
    cm = ConstitutionManager(storage, agent_id)
    cm.initialize(seed_text="seed constitution", ecosystem_id=storage.ecosystem_id)


def _write_notebook_entries(storage: EcosystemStorage, agent_id: str, texts: list[str]) -> None:
    writer = ChainWriter(storage.agent_notebook(agent_id))
    for i, text in enumerate(texts):
        writer.append(
            "agent.notebook.appended",
            {"text": text, "ref_decision_id": f"d-{i}", "fingerprint": f"f{i:064d}"[:64]},
            ecosystem_id=storage.ecosystem_id,
            agent_id=agent_id,
        )


def _write_roundtable_utterances(storage: EcosystemStorage, agents_and_texts: list[tuple[str, str]]) -> None:
    writer = ChainWriter(storage.roundtable_ledger())
    for agent_id, text in agents_and_texts:
        writer.append(
            "roundtable.utterance",
            {"text": text, "in_response_to": None},
            ecosystem_id=storage.ecosystem_id,
            agent_id=agent_id,
        )


def _write_townhall_broadcast(storage: EcosystemStorage, speaker: str, text: str) -> None:
    writer = ChainWriter(storage.townhall_ledger())
    writer.append(
        "townhall.convened",
        {"speaker_id": speaker, "topic": "test topic"},
        ecosystem_id=storage.ecosystem_id,
        agent_id=speaker,
    )
    writer.append(
        "townhall.broadcast",
        {"text": text},
        ecosystem_id=storage.ecosystem_id,
        agent_id=speaker,
    )
    writer.append(
        "townhall.adjourned",
        {"speaker_id": speaker, "respondent_count": 0},
        ecosystem_id=storage.ecosystem_id,
        agent_id=speaker,
    )


# ---------------------------------------------------------------------------
# A) Default behavior unchanged when E1 toggles are off
# ---------------------------------------------------------------------------

class TestDefaultBehaviorUnchanged:
    def test_defaults_produce_empty_peer_and_forum(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")

        builder = StateBuilder(storage, "agent-1")
        snapshot = builder.build()
        assert snapshot.peer_context == []
        assert snapshot.forum_digest == []

    def test_explicit_off_produces_empty(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "agent-2")
        _write_notebook_entries(storage, "agent-2", ["peer note A"])
        _write_roundtable_utterances(storage, [("agent-2", "roundtable msg")])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=False,
            peer_context_cap=0,
            enable_forum_digest=False,
            forum_digest_cap=0,
        )
        snapshot = builder.build()
        assert snapshot.peer_context == []
        assert snapshot.forum_digest == []

    def test_enabled_but_zero_cap_produces_empty(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "agent-2")
        _write_notebook_entries(storage, "agent-2", ["peer note"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=0,
        )
        snapshot = builder.build()
        assert snapshot.peer_context == []


# ---------------------------------------------------------------------------
# B) Peer context extraction
# ---------------------------------------------------------------------------

class TestPeerContext:
    def test_peer_context_basic_extraction(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _write_notebook_entries(storage, "peer-a", ["insight about topology"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
        )
        snapshot = builder.build()
        assert len(snapshot.peer_context) == 1
        seg = snapshot.peer_context[0]
        assert seg.source_type == "peer_notebook"
        assert "peer-a" in seg.source_agent_ids
        assert "insight about topology" in seg.text
        assert not seg.truncated

    def test_peer_context_provenance_fields(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _write_notebook_entries(storage, "peer-a", ["note one"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
        )
        snapshot = builder.build()
        seg = snapshot.peer_context[0]
        assert seg.source_ledger.endswith("notebook.jsonl")
        assert "peer-a" in seg.source_ledger
        assert len(seg.source_event_ids) >= 1
        assert seg.source_agent_ids == ["peer-a"]

    def test_peer_context_excludes_self(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _write_notebook_entries(storage, "agent-1", ["own note"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
        )
        snapshot = builder.build()
        agent_ids_seen = [seg.source_agent_ids for seg in snapshot.peer_context]
        assert all("agent-1" not in ids for ids in agent_ids_seen)

    def test_peer_context_cap_truncates(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _write_notebook_entries(storage, "peer-a", ["A" * 200])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=50,
        )
        snapshot = builder.build()
        assert len(snapshot.peer_context) == 1
        seg = snapshot.peer_context[0]
        assert seg.truncated is True
        assert len(seg.text) <= 50

    def test_peer_context_multiple_peers(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _init_agent(storage, "peer-b")
        _write_notebook_entries(storage, "peer-a", ["note from A"])
        _write_notebook_entries(storage, "peer-b", ["note from B"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=10000,
        )
        snapshot = builder.build()
        agent_ids = [seg.source_agent_ids[0] for seg in snapshot.peer_context]
        assert "peer-a" in agent_ids
        assert "peer-b" in agent_ids

    def test_peer_context_graceful_with_no_peers(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
        )
        snapshot = builder.build()
        assert snapshot.peer_context == []

    def test_peer_context_graceful_with_empty_notebooks(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
        )
        snapshot = builder.build()
        assert snapshot.peer_context == []


# ---------------------------------------------------------------------------
# C) Forum digest extraction
# ---------------------------------------------------------------------------

class TestForumDigest:
    def test_roundtable_digest_basic(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _write_roundtable_utterances(storage, [
            ("speaker-x", "First point about convergence"),
            ("speaker-y", "Counterpoint on divergence"),
        ])

        builder = StateBuilder(
            storage, "agent-1",
            enable_forum_digest=True,
            forum_digest_cap=5000,
        )
        snapshot = builder.build()
        rt_segments = [s for s in snapshot.forum_digest if s.source_type == "forum_roundtable"]
        assert len(rt_segments) == 1
        seg = rt_segments[0]
        assert "convergence" in seg.text
        assert "divergence" in seg.text
        assert not seg.truncated

    def test_townhall_digest_basic(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _write_townhall_broadcast(storage, "speaker-z", "Important announcement")

        builder = StateBuilder(
            storage, "agent-1",
            enable_forum_digest=True,
            forum_digest_cap=5000,
        )
        snapshot = builder.build()
        th_segments = [s for s in snapshot.forum_digest if s.source_type == "forum_townhall"]
        assert len(th_segments) == 1
        assert "Important announcement" in th_segments[0].text

    def test_forum_digest_provenance_fields(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _write_roundtable_utterances(storage, [("speaker-x", "hello")])

        builder = StateBuilder(
            storage, "agent-1",
            enable_forum_digest=True,
            forum_digest_cap=5000,
        )
        snapshot = builder.build()
        seg = snapshot.forum_digest[0]
        assert seg.source_ledger.endswith("roundtable.jsonl")
        assert len(seg.source_event_ids) >= 1
        assert "speaker-x" in seg.source_agent_ids

    def test_forum_digest_cap_truncates(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _write_roundtable_utterances(storage, [("s", "X" * 500)])

        builder = StateBuilder(
            storage, "agent-1",
            enable_forum_digest=True,
            forum_digest_cap=50,
        )
        snapshot = builder.build()
        seg = snapshot.forum_digest[0]
        assert seg.truncated is True
        assert len(seg.text) <= 50

    def test_forum_digest_graceful_with_no_forums(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")

        builder = StateBuilder(
            storage, "agent-1",
            enable_forum_digest=True,
            forum_digest_cap=5000,
        )
        snapshot = builder.build()
        assert snapshot.forum_digest == []


# ---------------------------------------------------------------------------
# D) Total cap enforcement
# ---------------------------------------------------------------------------

class TestTotalCap:
    def test_total_cap_limits_combined_output(self, tmp_path: Path) -> None:
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _write_notebook_entries(storage, "peer-a", ["A" * 300])
        _write_roundtable_utterances(storage, [("s", "B" * 300)])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
            enable_forum_digest=True,
            forum_digest_cap=5000,
            memory_context_total_cap=100,
        )
        snapshot = builder.build()
        total_chars = sum(len(s.text) for s in snapshot.peer_context + snapshot.forum_digest)
        assert total_chars <= 100

    def test_total_cap_zero_means_no_limit(self, tmp_path: Path) -> None:
        """memory_context_total_cap=0 is the default and means no global cap."""
        storage = _setup_ecosystem(tmp_path)
        _init_agent(storage, "agent-1")
        _init_agent(storage, "peer-a")
        _write_notebook_entries(storage, "peer-a", ["note"])

        builder = StateBuilder(
            storage, "agent-1",
            enable_peer_context=True,
            peer_context_cap=5000,
            memory_context_total_cap=0,
        )
        snapshot = builder.build()
        assert len(snapshot.peer_context) == 1
        assert snapshot.peer_context[0].truncated is False


# ---------------------------------------------------------------------------
# E) Prompt block inclusion/exclusion logic (via real Executor)
# ---------------------------------------------------------------------------

class _CaptureMockAdapter(MockAdapter):
    """MockAdapter that records the last user message for prompt inspection."""

    def __init__(self) -> None:
        super().__init__(model_id="mock-capture", seed=42)
        self.last_user_content: str = ""

    def complete(self, system, messages, *, max_tokens=4096, temperature=0.7):
        if messages:
            self.last_user_content = messages[-1].get("content", "")
        return super().complete(system, messages, max_tokens=max_tokens, temperature=temperature)


class TestPromptAssembly:
    @staticmethod
    def _make_snapshot(
        *,
        peer_context: list[ContextSegment] | None = None,
        forum_digest: list[ContextSegment] | None = None,
        retrieved_context: list[dict] | None = None,
    ) -> StateSnapshot:
        return StateSnapshot(
            snapshot_id="snap-1",
            constitution_text="test constitution",
            recent_events=[],
            recent_notebook=["note1"],
            recent_notebook_summary=None,
            belief_state={"event_density": 0.1, "notebook_dup_ratio": 0.0, "in_commons": 0.0},
            field_chosen="topology",
            in_commons=False,
            embedding_blob_ref=None,
            retrieved_context=retrieved_context or [],
            peer_context=peer_context or [],
            forum_digest=forum_digest or [],
        )

    @staticmethod
    def _make_executor(llm: _CaptureMockAdapter, tmp_path: Path) -> tuple[Executor, dict[str, ChainWriter]]:
        storage = EcosystemStorage("alpha", tmp_path)
        _init_agent(storage, "agent-1")
        executor = Executor(llm=llm, storage=storage, agent_id="agent-1")
        writers = {
            "public": ChainWriter(storage.public_ledger()),
            "commons": ChainWriter(storage.commons_ledger()),
            "notebook": ChainWriter(storage.agent_notebook("agent-1")),
        }
        return executor, writers

    def test_no_blocks_when_empty(self, tmp_path: Path) -> None:
        llm = _CaptureMockAdapter()
        executor, writers = self._make_executor(llm, tmp_path)
        snapshot = self._make_snapshot()
        executor.execute("RESEARCH", "READ", snapshot, writers)
        assert "PEER CONTEXT" not in llm.last_user_content
        assert "FORUM DIGEST" not in llm.last_user_content
        assert "RETRIEVED CONTEXT" not in llm.last_user_content

    def test_peer_block_present_when_populated(self, tmp_path: Path) -> None:
        llm = _CaptureMockAdapter()
        executor, writers = self._make_executor(llm, tmp_path)
        seg = ContextSegment(
            source_type="peer_notebook",
            source_ledger="ecosystems/alpha/agents/peer-a/notebook.jsonl",
            source_event_ids=["e1"],
            source_agent_ids=["peer-a"],
            text="peer insight",
        )
        snapshot = self._make_snapshot(peer_context=[seg])
        executor.execute("RESEARCH", "READ", snapshot, writers)
        assert "--- PEER CONTEXT (opt-in, capped) ---" in llm.last_user_content
        assert "peer insight" in llm.last_user_content
        assert "--- END PEER CONTEXT ---" in llm.last_user_content
        assert "peer-a" in llm.last_user_content
        assert "events: e1" in llm.last_user_content

    def test_forum_block_present_when_populated(self, tmp_path: Path) -> None:
        llm = _CaptureMockAdapter()
        executor, writers = self._make_executor(llm, tmp_path)
        seg = ContextSegment(
            source_type="forum_roundtable",
            source_ledger="ecosystems/alpha/roundtable.jsonl",
            source_event_ids=["e2"],
            source_agent_ids=["speaker-x"],
            text="roundtable point",
        )
        snapshot = self._make_snapshot(forum_digest=[seg])
        executor.execute("RESEARCH", "READ", snapshot, writers)
        assert "--- FORUM DIGEST (opt-in, capped) ---" in llm.last_user_content
        assert "roundtable point" in llm.last_user_content
        assert "--- END FORUM DIGEST ---" in llm.last_user_content
        assert "events: e2" in llm.last_user_content

    def test_retrieval_block_present_when_populated(self, tmp_path: Path) -> None:
        llm = _CaptureMockAdapter()
        executor, writers = self._make_executor(llm, tmp_path)
        snapshot = self._make_snapshot(retrieved_context=[{
            "id": "doc-1",
            "text": "retrieved finding",
            "relevance": 0.85,
            "agent_id": "agent-1",
            "source_type": "research",
        }])
        executor.execute("RESEARCH", "READ", snapshot, writers)
        assert "--- RETRIEVED CONTEXT (opt-in, capped) ---" in llm.last_user_content
        assert "retrieved finding" in llm.last_user_content
        assert "--- END RETRIEVED CONTEXT ---" in llm.last_user_content

    def test_block_ordering_is_deterministic(self, tmp_path: Path) -> None:
        llm = _CaptureMockAdapter()
        executor, writers = self._make_executor(llm, tmp_path)
        peer_seg = ContextSegment(
            source_type="peer_notebook",
            source_ledger="ecosystems/alpha/agents/peer-a/notebook.jsonl",
            source_event_ids=["e1"],
            source_agent_ids=["peer-a"],
            text="peer text",
        )
        forum_seg = ContextSegment(
            source_type="forum_roundtable",
            source_ledger="ecosystems/alpha/roundtable.jsonl",
            source_event_ids=["e2"],
            source_agent_ids=["speaker-x"],
            text="forum text",
        )
        snapshot = self._make_snapshot(
            peer_context=[peer_seg],
            forum_digest=[forum_seg],
            retrieved_context=[{"id": "r1", "text": "rag text", "relevance": 0.9, "agent_id": "", "source_type": ""}],
        )
        executor.execute("RESEARCH", "READ", snapshot, writers)
        content = llm.last_user_content
        peer_idx = content.index("PEER CONTEXT")
        forum_idx = content.index("FORUM DIGEST")
        retrieval_idx = content.index("RETRIEVED CONTEXT")
        assert peer_idx < forum_idx < retrieval_idx


# ---------------------------------------------------------------------------
# F) Config validation
# ---------------------------------------------------------------------------

class TestConfigValidation:
    def test_negative_cap_rejected(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict[str, object] = {
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "peer_context_cap": -1,
        }
        with pytest.raises(ValueError, match="non-negative"):
            _validate_run_config_modes(config)

    def test_valid_caps_accepted(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict[str, object] = {
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "peer_context_cap": 500,
            "forum_digest_cap": 300,
            "memory_context_total_cap": 1000,
        }
        _validate_run_config_modes(config)
        assert config["peer_context_cap"] == 500
        assert config["forum_digest_cap"] == 300
        assert config["memory_context_total_cap"] == 1000

    def test_string_bool_rejected_for_enable_peer_context(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict[str, object] = {
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_peer_context": "false",
        }
        with pytest.raises(ValueError, match="boolean"):
            _validate_run_config_modes(config)

    def test_string_bool_rejected_for_enable_forum_digest(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict[str, object] = {
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_forum_digest": "true",
        }
        with pytest.raises(ValueError, match="boolean"):
            _validate_run_config_modes(config)

    def test_actual_bool_accepted(self) -> None:
        from agent.runner import _validate_run_config_modes

        config: dict[str, object] = {
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_peer_context": True,
            "enable_forum_digest": False,
        }
        _validate_run_config_modes(config)


# ---------------------------------------------------------------------------
# G) Truncation helper
# ---------------------------------------------------------------------------

class TestTruncateToCap:
    def test_no_truncation_when_within_cap(self) -> None:
        text, truncated = _truncate_to_cap("hello", 10)
        assert text == "hello"
        assert truncated is False

    def test_exact_boundary_no_truncation(self) -> None:
        text, truncated = _truncate_to_cap("hello", 5)
        assert text == "hello"
        assert truncated is False

    def test_truncation_fits_within_cap(self) -> None:
        text, truncated = _truncate_to_cap("A" * 100, 50)
        assert truncated is True
        assert len(text) <= 50
        assert text.endswith(" [truncated]")

    def test_very_small_cap(self) -> None:
        text, truncated = _truncate_to_cap("A" * 100, 5)
        assert truncated is True
        assert len(text) <= 5

    def test_zero_cap(self) -> None:
        text, truncated = _truncate_to_cap("A" * 100, 0)
        assert truncated is True
        assert len(text) == 0


# ---------------------------------------------------------------------------
# H) ContextSegment dataclass
# ---------------------------------------------------------------------------

class TestContextSegment:
    def test_default_truncated_is_false(self) -> None:
        seg = ContextSegment(
            source_type="peer_notebook",
            source_ledger="path/to/notebook.jsonl",
            source_event_ids=["e1"],
            source_agent_ids=["agent-x"],
            text="hello",
        )
        assert seg.truncated is False

    def test_required_fields_present(self) -> None:
        seg = ContextSegment(
            source_type="forum_roundtable",
            source_ledger="ecosystems/alpha/roundtable.jsonl",
            source_event_ids=["e1", "e2"],
            source_agent_ids=["a1", "a2"],
            text="content",
            truncated=True,
        )
        assert seg.source_type == "forum_roundtable"
        assert seg.source_ledger == "ecosystems/alpha/roundtable.jsonl"
        assert seg.source_event_ids == ["e1", "e2"]
        assert seg.source_agent_ids == ["a1", "a2"]
        assert seg.truncated is True
