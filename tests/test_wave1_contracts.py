from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent.executor import Executor
from tools.check_run_config_hashes import check_config


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_parse_and_validate_structured_accepts_valid_analyze_json() -> None:
    raw = json.dumps(
        {
            "assumptions": ["a1"],
            "evidence_gaps": ["g1"],
            "structural_weaknesses": ["w1"],
            "summary": "ok",
        }
    )
    parsed = Executor._parse_and_validate_structured("ANALYZE", raw)
    assert parsed is not None
    assert parsed["summary"] == "ok"


def test_parse_and_validate_structured_rejects_non_json() -> None:
    parsed = Executor._parse_and_validate_structured("ANNOTATE", "not json")
    assert parsed is None


def test_run_config_hash_check_detects_mismatch(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# executor", encoding="utf-8")

    config_path = tmp_path / "run_config_test.json"
    config = {
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": "0" * 64,
        "executor_templates_hash": _sha256(exec_path),
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    errors = check_config(config_path, tmp_path)
    assert errors
    assert any("action_vocabulary_hash mismatch" in error for error in errors)
