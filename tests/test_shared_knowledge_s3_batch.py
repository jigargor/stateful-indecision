from __future__ import annotations

import json
import sys
from pathlib import Path

from infra.storage import EcosystemStorage
from infra.shared_knowledge_s3 import shared_head_key
from tools.publish_shared_knowledge import publish_snapshot


class _FakeStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None:
        self.objects[key] = payload

    def get_bytes(self, *, key: str) -> bytes:
        return self.objects[key]


def _seed_research_artifact(base_dir: Path, ecosystem_id: str, agent_id: str) -> None:
    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    research_dir = storage.agent_research_dir(agent_id)
    payload = {
        "artifact_id": "a-1",
        "agent_id": agent_id,
        "ecosystem_id": ecosystem_id,
        "action": "ANALYZE",
        "content": "line one\nline two\nline three\nline four",
        "structured": {"summary": "A concise summary that is longer than threshold."},
        "created_at": "2026-01-01T00:00:00Z",
    }
    (research_dir / "a-1.json").write_text(json.dumps(payload), encoding="utf-8")


def test_publish_snapshot_writes_head_and_snapshot_objects(monkeypatch, tmp_path: Path) -> None:
    _seed_research_artifact(tmp_path, "alpha", "agent-1")
    fake = _FakeStore()
    monkeypatch.setattr("tools.publish_shared_knowledge.s3_object_store_from_env", lambda: fake)

    pointer = publish_snapshot(
        base_dir=tmp_path,
        family_id="research-family",
        ecosystem_id="alpha",
        ecosystems=["alpha"],
        min_quality=0.0,
        include_candidates=True,
    )

    assert shared_head_key("research-family") in fake.objects
    assert pointer.promoted_key in fake.objects
    assert pointer.grant_state_key in fake.objects
    assert pointer.candidates_key in fake.objects
    head = json.loads(fake.objects[shared_head_key("research-family")].decode("utf-8"))
    assert head["snapshot_id"] == pointer.snapshot_id


def test_ingest_from_head_skips_already_processed_snapshot(monkeypatch, tmp_path: Path) -> None:
    from tools import ingest_shared_knowledge as ingest_mod

    family_id = "research-family"
    head = {
        "family_id": family_id,
        "snapshot_id": "20260511T200000Z",
        "updated_at": "20260511T200000Z",
        "promoted_key": "shared_knowledge/research-family/snapshots/20260511T200000Z/promoted.jsonl",
        "grant_state_key": "shared_knowledge/research-family/snapshots/20260511T200000Z/grant_state.json",
        "promoted_sha256": "",
        "grant_state_sha256": "x",
    }
    promoted_rows = [{
        "promotion_id": "research-family:abc",
        "family_id": family_id,
        "content_hash": "abc",
        "content": "shared content",
        "action": "SYNTHESIZE",
        "quality_score": 0.9,
    }]
    promoted_blob = (json.dumps(promoted_rows[0]) + "\n").encode("utf-8")
    import hashlib

    head["promoted_sha256"] = hashlib.sha256(promoted_blob).hexdigest()

    fake = _FakeStore()
    fake.objects[shared_head_key(family_id)] = json.dumps(head).encode("utf-8")
    fake.objects[head["promoted_key"]] = promoted_blob
    monkeypatch.setattr("tools.ingest_shared_knowledge.s3_object_store_from_env", lambda: fake)

    calls: list[int] = []

    class FakeStore:
        def __init__(self, persist_dir):
            pass

        def upsert_documents(self, collection, ids, texts, metadatas, embedder):
            calls.append(len(ids))
            return len(ids)

    class FakeEmbedder:
        def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

        def embed_query(self, text):
            return [0.0] * 3

    monkeypatch.setitem(sys.modules, "infra.vector_store", type("M", (), {"VectorStore": FakeStore}))
    monkeypatch.setitem(sys.modules, "infra.embeddings", type("M", (), {"get_embedder": lambda: FakeEmbedder()}))

    argv = [
        "ingest_shared_knowledge.py",
        "--family-id",
        family_id,
        "--ecosystem",
        "alpha",
        "--base-dir",
        str(tmp_path),
        "--from-head",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    ingest_mod.main()
    ingest_mod.main()
    assert calls == [1]
