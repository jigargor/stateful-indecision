"""Wave E4 — Promotion defaults and deprecation tests.

Verifies:
- Promoted explicit defaults in run_config files are correctly loaded.
- Removing promoted keys falls back to safe defaults (rollback safety).
- All 4 real run_config files pass validation with promoted keys.
- Deprecated values remain functional within the transition window.
- Config version bumps are consistent across all files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent.runner import _validate_run_config_modes, load_run_config
from agent.state_builder import StateBuilder
from infra.storage import EcosystemStorage
from agent.constitution_manager import ConstitutionManager


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_minimal_config(tmp_path: Path, overrides: dict | None = None) -> tuple[Path, dict]:
    seed_path = tmp_path / "seed.md"
    fields_path = tmp_path / "fields.json"
    vocab_path = tmp_path / "vocab.json"
    exec_path = tmp_path / "executor.py"
    seed_path.write_text("seed", encoding="utf-8")
    fields_path.write_text("[]", encoding="utf-8")
    vocab_path.write_text("{}", encoding="utf-8")
    exec_path.write_text("# executor", encoding="utf-8")

    config: dict = {
        "config_version": "0.0.1",
        "constitution_seed_path": seed_path.name,
        "field_list_path": fields_path.name,
        "action_vocabulary_path": vocab_path.name,
        "executor_templates_path": exec_path.name,
        "constitution_seed_hash": _sha256(seed_path),
        "field_list_hash": _sha256(fields_path),
        "action_vocabulary_hash": _sha256(vocab_path),
        "executor_templates_hash": _sha256(exec_path),
    }
    if overrides:
        config.update(overrides)
    config_path = tmp_path / "run_config_test.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path, config


# ---------------------------------------------------------------------------
# Section A: Promoted explicit defaults load correctly
# ---------------------------------------------------------------------------

class TestPromotedExplicitDefaults:
    """All E4-promoted keys should be accepted by validation."""

    def test_prompt_progression_explicit_off(self) -> None:
        config: dict = {"config_version": "1.0.0", "prompt_progression": "off"}
        _validate_run_config_modes(config)
        assert config["prompt_progression"] == "off"

    def test_enable_peer_context_explicit_false(self) -> None:
        config: dict = {
            "config_version": "1.0.0",
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_peer_context": False,
        }
        _validate_run_config_modes(config)

    def test_enable_forum_digest_explicit_false(self) -> None:
        config: dict = {
            "config_version": "1.0.0",
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_forum_digest": False,
        }
        _validate_run_config_modes(config)

    def test_memory_caps_explicit_zero(self) -> None:
        config: dict = {
            "config_version": "1.0.0",
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "peer_context_cap": 0,
            "forum_digest_cap": 0,
            "memory_context_total_cap": 0,
            "notebook_consolidation_interval": 0,
        }
        _validate_run_config_modes(config)
        assert config["peer_context_cap"] == 0
        assert config["forum_digest_cap"] == 0
        assert config["memory_context_total_cap"] == 0
        assert config["notebook_consolidation_interval"] == 0

    def test_all_promoted_keys_together(self) -> None:
        config: dict = {
            "config_version": "1.0.0",
            "prompt_progression": "off",
            "verifier_mode": "warn",
            "reward_mode": "sparse",
            "enable_peer_context": False,
            "peer_context_cap": 0,
            "enable_forum_digest": False,
            "forum_digest_cap": 0,
            "enable_rag_retrieval": False,
            "memory_context_total_cap": 0,
            "notebook_consolidation_interval": 0,
            "enable_pi_reason_then_action": False,
            "emit_latent_reasoning_events": False,
        }
        _validate_run_config_modes(config)


# ---------------------------------------------------------------------------
# Section B: Rollback safety — removing promoted keys falls back safely
# ---------------------------------------------------------------------------

class TestRollbackDefaults:
    """Removing E4-promoted keys must produce safe fallback behavior."""

    def test_absent_prompt_progression_defaults_to_off(self) -> None:
        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)
        assert config["prompt_progression"] == "off"

    def test_absent_verifier_mode_defaults_to_warn(self) -> None:
        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)
        assert config["verifier_mode"] == "warn"

    def test_absent_reward_mode_defaults_to_sparse(self) -> None:
        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)
        assert config["reward_mode"] == "sparse"

    def test_absent_memory_caps_no_error(self) -> None:
        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)
        assert config.get("peer_context_cap") is None
        assert config.get("forum_digest_cap") is None
        assert config.get("memory_context_total_cap") is None

    def test_absent_boolean_toggles_no_error(self) -> None:
        config: dict = {"config_version": "1.0.0"}
        _validate_run_config_modes(config)

    def test_load_config_without_promoted_keys(self, tmp_path: Path) -> None:
        config_path, _ = _make_minimal_config(tmp_path)
        loaded, _, _ = load_run_config(tmp_path, config_path.name)
        assert loaded["prompt_progression"] == "off"
        assert loaded["verifier_mode"] == "warn"
        assert loaded["reward_mode"] == "sparse"
        assert loaded["tool_allowlist"] == []


# ---------------------------------------------------------------------------
# Section B2: Runtime fallback — StateBuilder defaults produce safe snapshots
# ---------------------------------------------------------------------------

def _init_ecosystem_agent(tmp_path: Path, ecosystem_id: str = "alpha", agent_id: str = "agent-1") -> EcosystemStorage:
    storage = EcosystemStorage(ecosystem_id, tmp_path)
    cm = ConstitutionManager(storage, agent_id)
    cm.initialize(seed_text="seed constitution", ecosystem_id=ecosystem_id)
    return storage


class TestRuntimeFallbackDefaults:
    """StateBuilder with default params (simulating absent config keys) must produce safe snapshots."""

    def test_default_statebuilder_has_empty_peer_and_forum(self, tmp_path: Path) -> None:
        storage = _init_ecosystem_agent(tmp_path)
        builder = StateBuilder(storage, "agent-1")
        snapshot = builder.build()
        assert snapshot.peer_context == []
        assert snapshot.forum_digest == []

    def test_default_statebuilder_has_no_rag_context(self, tmp_path: Path) -> None:
        storage = _init_ecosystem_agent(tmp_path)
        builder = StateBuilder(storage, "agent-1")
        snapshot = builder.build()
        assert snapshot.retrieved_context == []
        assert snapshot.embedding_blob_ref is None


# ---------------------------------------------------------------------------
# Section C: Real run_config files pass validation
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILES = [
    "run_config.json",
    "run_config_beta_a1.json",
    "run_config_beta_a2.json",
    "run_config_beta_a3.json",
]


class TestRealConfigFiles:
    """All 4 production run_config files must pass validation after E4 promotion."""

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_loads_successfully(self, config_file: str) -> None:
        result = load_run_config(_BASE_DIR, config_file)
        assert result is not None
        config, paths, config_path = result
        assert "config_version" in config
        assert config_path.exists()

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_has_explicit_prompt_progression(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        assert "prompt_progression" in raw, f"{config_file} missing explicit prompt_progression"
        assert raw["prompt_progression"] == "off"

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_has_explicit_memory_exposure_keys(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        for key in ("enable_peer_context", "enable_forum_digest", "enable_rag_retrieval"):
            assert key in raw, f"{config_file} missing explicit {key}"
            assert raw[key] is False

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_has_explicit_caps(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        for key in ("peer_context_cap", "forum_digest_cap", "memory_context_total_cap", "notebook_consolidation_interval"):
            assert key in raw, f"{config_file} missing explicit {key}"
            assert raw[key] == 0

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_verifier_mode_is_warn(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        assert raw["verifier_mode"] == "warn"

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_real_config_experimental_features_off(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        assert raw["enable_pi_reason_then_action"] is False
        assert raw["emit_latent_reasoning_events"] is False


# ---------------------------------------------------------------------------
# Section D: Deprecated values remain functional (transition window)
# ---------------------------------------------------------------------------

class TestDeprecatedValuesStillWork:
    """Deprecated defaults must remain functional during the transition window."""

    def test_verifier_mode_warn_still_accepted(self) -> None:
        config: dict = {"config_version": "1.0.0", "verifier_mode": "warn"}
        _validate_run_config_modes(config)
        assert config["verifier_mode"] == "warn"

    def test_verifier_mode_enforce_still_accepted(self) -> None:
        config: dict = {"config_version": "1.0.0", "verifier_mode": "enforce"}
        _validate_run_config_modes(config)
        assert config["verifier_mode"] == "enforce"

    def test_prompt_progression_all_values_accepted(self) -> None:
        for val in ("off", "standard", "aggressive"):
            config: dict = {"config_version": "1.0.0", "prompt_progression": val}
            _validate_run_config_modes(config)
            assert config["prompt_progression"] == val

    def test_prompt_progression_case_insensitive(self) -> None:
        config: dict = {"config_version": "1.0.0", "prompt_progression": "OFF"}
        _validate_run_config_modes(config)
        assert config["prompt_progression"] == "off"


# ---------------------------------------------------------------------------
# Section E: Config version consistency
# ---------------------------------------------------------------------------

class TestConfigVersionConsistency:
    """Config versions should have been bumped for E4."""

    def test_alpha_config_version_bumped(self) -> None:
        raw = json.loads((_BASE_DIR / "run_config.json").read_text(encoding="utf-8"))
        assert raw["config_version"] == "0.0.8"

    def test_beta_a1_config_version_bumped(self) -> None:
        raw = json.loads((_BASE_DIR / "run_config_beta_a1.json").read_text(encoding="utf-8"))
        assert raw["config_version"] == "0.0.197"

    def test_beta_a2_config_version_bumped(self) -> None:
        raw = json.loads((_BASE_DIR / "run_config_beta_a2.json").read_text(encoding="utf-8"))
        assert raw["config_version"] == "0.0.194"

    def test_beta_a3_config_version_bumped(self) -> None:
        raw = json.loads((_BASE_DIR / "run_config_beta_a3.json").read_text(encoding="utf-8"))
        assert raw["config_version"] == "0.0.196"

    @pytest.mark.parametrize("config_file", _CONFIG_FILES)
    def test_knob_changelog_references_e4(self, config_file: str) -> None:
        raw = json.loads((_BASE_DIR / config_file).read_text(encoding="utf-8"))
        assert "E4" in raw.get("knob_changelog", ""), f"{config_file} changelog missing E4 reference"
