from __future__ import annotations

import pytest

from infra.storage import EcosystemStorage, FirewallError


def test_ecosystem_scope_resolution(tmp_path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    path = storage.resolve("public.jsonl")
    assert str(path).startswith(str((tmp_path / "ecosystems" / "alpha").resolve()))


def test_escape_path_is_blocked(tmp_path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    with pytest.raises(FirewallError):
        storage.resolve("../../etc/passwd")


def test_cross_ecosystem_escape_is_blocked(tmp_path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    with pytest.raises(FirewallError):
        storage.resolve("../beta/public.jsonl")


def test_agent_dir_resolution(tmp_path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    path = storage.agent_dir("agent-001")
    expected = (tmp_path / "ecosystems" / "alpha" / "agents" / "agent-001").resolve()
    assert path == expected


def test_invalid_agent_id_is_blocked(tmp_path) -> None:
    storage = EcosystemStorage("alpha", tmp_path)
    with pytest.raises(FirewallError):
        storage.agent_dir("../agent-002")
