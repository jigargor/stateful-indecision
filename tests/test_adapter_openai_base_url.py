"""Tests for OpenAI-compatible base URL wiring (local OSS stacks)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adapters import OpenAIAdapter, create_adapter_auto
from adapters.mock import MockAdapter
from agent.runner import load_run_config


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def test_create_adapter_auto_passes_base_url_for_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    adapter = create_adapter_auto("openai:llama3.2")

    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.base_url == "http://localhost:11434/v1"
    assert adapter.api_key == "local-openai-compat"


def test_create_adapter_auto_run_config_base_url_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://env-only/wrong")

    adapter = create_adapter_auto(
        "openai:llama3.2",
        openai_base_url="http://from-run-config/v1",
    )

    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.base_url == "http://from-run-config/v1"


def test_create_adapter_auto_openai_without_key_or_base_url_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    adapter = create_adapter_auto("openai:gpt-4o-mini")

    assert isinstance(adapter, MockAdapter)


def test_load_run_config_rejects_empty_openai_base_url(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# x", encoding="utf-8")

    cfg_path = tmp_path / "rc.json"
    cfg_path.write_text(
        json.dumps(
            {
                "config_version": "0.0.1",
                "ecosystem_id": "alpha",
                "agent_id": "a1",
                "model_id": "m",
                "model_spec": "openai:m",
                "openai_base_url": "   ",
                "constitution_seed_path": "seed.md",
                "field_list_path": "fields.json",
                "action_vocabulary_path": "vocab.json",
                "executor_templates_path": "executor.py",
                "constitution_seed_hash": _sha256_bytes(seed_path.read_bytes()),
                "field_list_hash": _sha256_bytes(fields_path.read_bytes()),
                "action_vocabulary_hash": _sha256_bytes(vocab_path.read_bytes()),
                "executor_templates_hash": _sha256_bytes(exec_path.read_bytes()),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="openai_base_url"):
        load_run_config(tmp_path, str(cfg_path.name))
