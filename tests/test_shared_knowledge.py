from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from agent.constitution_manager import ConstitutionManager
from agent.runner import _validate_run_config_modes
from agent.state_builder import StateBuilder
from infra.shared_knowledge import compute_grants_hash, validate_family_id
from infra.storage import EcosystemStorage


def _init_agent(tmp_path: Path, ecosystem_id: str = "alpha", agent_id: str = "agent-1") -> EcosystemStorage:
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=tmp_path)
    cm = ConstitutionManager(storage, agent_id)
    cm.initialize(seed_text="seed constitution", ecosystem_id=ecosystem_id)
    return storage


def _write_grant_state(storage: EcosystemStorage, family_id: str, payload: dict) -> None:
    state_path = storage.shared_knowledge_grant_state(family_id)
    data = dict(payload)
    data["grants_hash"] = compute_grants_hash(data)
    state_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_validate_family_id_rejects_invalid_and_reserved() -> None:
    assert validate_family_id("research-family") == "research-family"
    with pytest.raises(ValueError):
        validate_family_id("has_underscore")
    with pytest.raises(ValueError):
        validate_family_id("shared")


def test_run_config_shared_knowledge_cross_validation() -> None:
    bad_missing_family = {
        "config_version": "0.0.1",
        "enable_shared_knowledge_retrieval": True,
        "shared_knowledge_access_profile": "lead",
    }
    with pytest.raises(ValueError, match="shared_knowledge_family_id"):
        _validate_run_config_modes(bad_missing_family)

    bad_missing_profile = {
        "config_version": "0.0.1",
        "enable_shared_knowledge_retrieval": True,
        "shared_knowledge_family_id": "research-family",
    }
    with pytest.raises(ValueError, match="shared_knowledge_access_profile"):
        _validate_run_config_modes(bad_missing_profile)

    good = {
        "config_version": "0.0.1",
        "enable_shared_knowledge_retrieval": True,
        "shared_knowledge_family_id": "research-family",
        "shared_knowledge_access_profile": "lead",
        "shared_knowledge_n_results": 4,
        "shared_knowledge_min_relevance": 0.2,
    }
    _validate_run_config_modes(good)
    assert good["shared_knowledge_family_id"] == "research-family"


def test_shared_retrieval_denied_skips_shared_query(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = _init_agent(tmp_path)
    family_id = "research-family"
    _write_grant_state(storage, family_id, {
        "family_id": family_id,
        "grant_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "grants": [{
            "access_profile": "checker",
            "allow_ecosystems": ["alpha"],
            "allow_agents": ["agent-1"],
            "enabled": True,
        }],
    })

    query_calls: list[tuple[str, dict | None]] = []

    class FakeStore:
        def __init__(self, persist_dir):
            pass

        def query(self, collection, query_text, embedder, *, n_results=5, where=None, min_relevance=0.0):
            query_calls.append((collection, where))
            return types.SimpleNamespace(ids=[], documents=[], metadatas=[], distances=[])

    class FakeEmbedder:
        def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

        def embed_query(self, text):
            return [0.0] * 3

    fake_embeddings = types.SimpleNamespace(get_embedder=lambda: FakeEmbedder())
    fake_vector_store = types.SimpleNamespace(VectorStore=FakeStore)
    monkeypatch.setitem(__import__("sys").modules, "infra.embeddings", fake_embeddings)
    monkeypatch.setitem(__import__("sys").modules, "infra.vector_store", fake_vector_store)

    builder = StateBuilder(
        storage,
        "agent-1",
        enable_rag=True,
        enable_shared_knowledge_retrieval=True,
        shared_knowledge_family_id=family_id,
        shared_knowledge_access_profile="lead",
        shared_knowledge_n_results=3,
    )
    snapshot = builder.build()
    event_types = [row.get("event_type") for row in snapshot.shared_knowledge_audits]
    assert "shared_knowledge.retrieval_denied" in event_types
    assert "shared_knowledge.context_used" not in event_types
    assert len(query_calls) == 1


def test_shared_retrieval_allowed_emits_context_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = _init_agent(tmp_path)
    family_id = "research-family"
    _write_grant_state(storage, family_id, {
        "family_id": family_id,
        "grant_version": 2,
        "updated_at": "2099-01-01T00:00:00Z",
        "grants": [{
            "access_profile": "lead",
            "allow_ecosystems": ["alpha"],
            "allow_agents": [],
            "enabled": True,
        }],
    })

    class FakeStore:
        def __init__(self, persist_dir):
            pass

        def query(self, collection, query_text, embedder, *, n_results=5, where=None, min_relevance=0.0):
            if collection == "shared_knowledge":
                return types.SimpleNamespace(
                    ids=["research-family:abc123"],
                    documents=["shared context text"],
                    metadatas=[{"action": "SYNTHESIZE"}],
                    distances=[0.01],
                )
            return types.SimpleNamespace(
                ids=["local1"],
                documents=["local context text"],
                metadatas=[{"action": "ANALYZE", "source_type": "local", "agent_id": "agent-1"}],
                distances=[0.2],
            )

    class FakeEmbedder:
        def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

        def embed_query(self, text):
            return [0.0] * 3

    fake_embeddings = types.SimpleNamespace(get_embedder=lambda: FakeEmbedder())
    fake_vector_store = types.SimpleNamespace(VectorStore=FakeStore)
    monkeypatch.setitem(__import__("sys").modules, "infra.embeddings", fake_embeddings)
    monkeypatch.setitem(__import__("sys").modules, "infra.vector_store", fake_vector_store)

    builder = StateBuilder(
        storage,
        "agent-1",
        enable_rag=True,
        enable_shared_knowledge_retrieval=True,
        shared_knowledge_family_id=family_id,
        shared_knowledge_access_profile="lead",
    )
    snapshot = builder.build()
    event_types = [row.get("event_type") for row in snapshot.shared_knowledge_audits]
    assert "shared_knowledge.retrieval_allowed" in event_types
    assert "shared_knowledge.context_used" in event_types
    assert any(item.get("source_type") == "shared_knowledge" for item in snapshot.retrieved_context)
