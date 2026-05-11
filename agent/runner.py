from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from pathlib import Path

from adapters import MockAdapter, create_adapter_auto
from adapters.base import LLMAdapter
from agent.constitution_manager import ConstitutionManager
from agent.decision import step
from agent.executor import Executor
from agent.policy import Policy
from agent.state_builder import StateBuilder
from core.verifier import verify_chain
from core.writer import ChainCorruptionError, ChainWriter
from infra.env import load_env
from infra.llm_client import LLMError
from infra.shared_knowledge import validate_family_id
from infra.storage import EcosystemStorage, FirewallError
from safety.kill_switch import KillSwitchMonitor
from schemas.events import ActionVocabulary, EventEnvelope
from tools.consolidate_notebook import consolidate_older_entries

RUN_CONFIG_HARD_STOP_VERSION = "1.0.0"


def _verify_boundary(
    *,
    eval_writer: ChainWriter,
    ledger_path: Path,
    boundary: str,
    ecosystem_id: str,
    agent_id: str,
    verifier_mode: str,
) -> None:
    """Run chain verification at a run boundary and emit result to evaluation ledger.

    boundary should be "start" or "terminal".
    """
    result = verify_chain(ledger_path)
    error_dicts = [
        {"line_number": e.line_number, "event_id": e.event_id, "error": e.error}
        for e in result.errors
    ]
    eval_writer.append(
        "verifier.boundary_checked",
        {
            "boundary": boundary,
            "outcome": "pass" if result.valid else "fail",
            "ledger": str(ledger_path.name),
            "total_events": result.total_events,
            "errors": error_dicts,
            "verifier_mode": verifier_mode,
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    if not result.valid and verifier_mode == "enforce":
        raise ChainCorruptionError(
            f"verifier {boundary} check failed on {ledger_path.name}: "
            f"{len(result.errors)} error(s)"
        )


def _maybe_inject_external_townhall_visitor(
    *,
    storage: EcosystemStorage,
    public_writer: ChainWriter,
    run_config: dict[str, object] | None,
) -> None:
    """Append a closed external-visitor townhall session when `townhall_visitor` is set on run_config.

    Skips if the ledger already ends with the same visitor topic (session_kind external_visitor) so
    multi-agent waves do not duplicate identical briefings.
    """
    if run_config is None:
        return
    raw = run_config.get("townhall_visitor")
    if not isinstance(raw, dict):
        return
    topic = str(raw.get("topic", "")).strip()
    if not topic:
        return

    from forums.townhall import Townhall

    th_path = storage.townhall_ledger()
    if th_path.exists():
        lines = [ln for ln in th_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        last_visitor_topic: str | None = None
        for ln in reversed(lines):
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if ev.get("event_type") != "townhall.convened":
                continue
            p = ev.get("payload") or {}
            if p.get("session_kind") == "external_visitor":
                last_visitor_topic = str(p.get("topic", "")).strip()
                break
        if last_visitor_topic == topic:
            return

    speaker_id = str(raw.get("speaker_id", "external-expert")).strip() or "external-expert"
    bridge = str(raw.get("tangential_bridge", raw.get("relation_to_team_work", ""))).strip()
    brief = str(raw.get("brief", raw.get("message", ""))).strip()
    th = Townhall(ChainWriter(th_path), public_writer, storage.ecosystem_id)
    th.convene(
        speaker_id,
        topic,
        session_kind="external_visitor",
        tangential_bridge=bridge or None,
    )
    to_broadcast = brief if brief else topic
    if len(to_broadcast) > 8000:
        to_broadcast = to_broadcast[:8000] + "…"
    th.broadcast(speaker_id, to_broadcast)
    th.adjourn(speaker_id)


def _try_s3_sync(storage: EcosystemStorage, base_dir: Path, run_config: dict | None, mode: str = "once") -> None:
    """Best-effort S3 sync; never raises."""
    try:
        from infra.s3_sync import S3SyncConfig, config_from_env, sync_ecosystem_once

        cfg = config_from_env()
        if cfg is None:
            if run_config and isinstance(run_config.get("s3_offload"), dict):
                offload = run_config["s3_offload"]
                if not offload.get("enabled", False):
                    return
                bucket = str(offload.get("bucket", ""))
                if not bucket:
                    return
                cfg = S3SyncConfig(
                    bucket=bucket,
                    prefix=str(offload.get("prefix", "")),
                    region=os.environ.get("AWS_REGION"),
                    sync_interval_sec=int(offload.get("sync_interval_sec", 300)),
                    research_mode=str(offload.get("research_mode", "bundle")),
                )
            else:
                return

        state_path = Path(
            os.environ.get(
                "S3_STATE_PATH",
                str(base_dir / ".sync_state" / f"{storage.ecosystem_id}.json"),
            )
        )
        sync_ecosystem_once(storage, cfg, state_path=state_path, mode=mode)
    except ImportError:
        pass
    except Exception as exc:
        print(f"[s3_sync] {mode} sync failed: {exc}")


class _PeriodicSyncThread:
    """Background thread that runs S3 sync on a configurable interval."""

    def __init__(
        self,
        storage: EcosystemStorage,
        base_dir: Path,
        run_config: dict | None,
        interval_sec: int = 300,
    ):
        self._storage = storage
        self._base_dir = base_dir
        self._run_config = run_config
        self._interval = interval_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="s3-periodic-sync")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(timeout=self._interval):
            _try_s3_sync(self._storage, self._base_dir, self._run_config, mode="periodic")


def _count_full_ledger_actions(ledger_path: Path, agent_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not ledger_path.exists():
        return counts
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_type") != "agent.decision.taken":
            continue
        if event.get("agent_id") != agent_id:
            continue
        payload = event.get("payload", {})
        key = f"{payload.get('top_action', '?')}/{payload.get('sub_action', '?')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid config_version '{version}', expected MAJOR.MINOR.PATCH")
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"invalid config_version '{version}', expected integers") from exc
    return major, minor, patch


def _version_gte(left: str, right: str) -> bool:
    return _parse_version(left) >= _parse_version(right)


def _bump_patch(version: str) -> str:
    major, minor, patch = _parse_version(version)
    patch += 1
    return f"{major}.{minor}.{patch}"


def _resolve_path(base_dir: Path, relative_or_absolute: str, default_relative: str) -> Path:
    candidate = Path(relative_or_absolute) if relative_or_absolute else Path(default_relative)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not str(candidate).startswith(str(base_dir)):
        raise FirewallError(f"run_config path escapes base_dir: {relative_or_absolute}")
    return candidate


def _load_field_list_from_file(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("field list file must be a string list")
    if not data:
        raise ValueError("field list file cannot be empty")
    return data


def _load_prompt_pack(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("prompt pack must be a JSON object")
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise ValueError("prompt pack must include a 'roles' object")
    shared = data.get("shared")
    if shared is not None and not isinstance(shared, dict):
        raise ValueError("prompt pack 'shared' must be an object when present")
    return data


def _parse_tool_allowlist(raw: object | None) -> set[str] | None:
    if raw is None:
        return set()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("run_config 'tool_allowlist' must be a list of strings when provided")
    return {item.strip() for item in raw if item.strip()}


def _validate_run_config_modes(config: dict[str, object]) -> None:
    # DEPRECATION(E4): Reliance on absent prompt_progression key implying "off"
    # is deprecated.  All run_config files should include an explicit value.
    # Transition window: 2 config versions.  Removal target: v2.0.0.
    prompt_progression = str(config.get("prompt_progression", "off")).strip().lower()
    if prompt_progression not in {"off", "standard", "aggressive"}:
        raise ValueError("run_config 'prompt_progression' must be one of: off, standard, aggressive")
    config["prompt_progression"] = prompt_progression

    # DEPRECATION(E4): verifier_mode "warn" is supported but promotion to "enforce"
    # is pending operator acceptance testing.  Target: evaluate in v2.0.0 cycle.
    verifier_mode = str(config.get("verifier_mode", "warn")).strip().lower()
    if verifier_mode not in {"warn", "enforce"}:
        raise ValueError("run_config 'verifier_mode' must be one of: warn, enforce")
    config["verifier_mode"] = verifier_mode

    reward_mode = str(config.get("reward_mode", "sparse")).strip().lower()
    if reward_mode not in {"sparse", "dense"}:
        raise ValueError("run_config 'reward_mode' must be one of: sparse, dense")
    config["reward_mode"] = reward_mode

    config["tool_allowlist"] = sorted(_parse_tool_allowlist(config.get("tool_allowlist")) or [])

    for bool_key in (
        "enable_peer_context",
        "enable_forum_digest",
        "enable_rag_retrieval",
        "enable_shared_knowledge_retrieval",
        "emit_latent_reasoning_events",
        "enable_pi_reason_then_action",
    ):
        raw = config.get(bool_key)
        if raw is not None and not isinstance(raw, bool):
            raise ValueError(
                f"run_config '{bool_key}' must be a boolean (true/false), got {type(raw).__name__}: {raw!r}"
            )

    for int_key in (
        "peer_context_cap",
        "forum_digest_cap",
        "memory_context_total_cap",
        "memory_recent_events_cap",
        "memory_recent_notebook_cap",
        "notebook_consolidation_interval",
        "rag_n_results",
        "shared_knowledge_n_results",
        "shared_knowledge_grant_max_age_sec",
    ):
        raw = config.get(int_key)
        if raw is not None:
            if isinstance(raw, bool):
                raise ValueError(f"run_config '{int_key}' must be an integer, got bool: {raw!r}")
            val = int(raw)
            if val < 0:
                raise ValueError(f"run_config '{int_key}' must be non-negative, got {val}")
            config[int_key] = val

    for positive_key in ("rag_n_results", "shared_knowledge_n_results"):
        if positive_key in config and int(config[positive_key]) <= 0:
            raise ValueError(f"run_config '{positive_key}' must be > 0")

    for float_key in ("rag_min_relevance", "shared_knowledge_min_relevance"):
        raw = config.get(float_key)
        if raw is not None:
            if isinstance(raw, bool):
                raise ValueError(f"run_config '{float_key}' must be a float, got bool: {raw!r}")
            val = float(raw)
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"run_config '{float_key}' must be within [0.0, 1.0], got {val}")
            config[float_key] = val

    if bool(config.get("enable_shared_knowledge_retrieval", False)):
        family_id = str(config.get("shared_knowledge_family_id", "")).strip()
        if not family_id:
            raise ValueError(
                "run_config 'shared_knowledge_family_id' is required when enable_shared_knowledge_retrieval=true"
            )
        config["shared_knowledge_family_id"] = validate_family_id(family_id)
        access_profile = str(config.get("shared_knowledge_access_profile", "")).strip()
        if not access_profile:
            raise ValueError(
                "run_config 'shared_knowledge_access_profile' is required when enable_shared_knowledge_retrieval=true"
            )
        config["shared_knowledge_access_profile"] = access_profile

    raw_ob = config.get("openai_base_url")
    if raw_ob is not None:
        if not isinstance(raw_ob, str):
            raise ValueError(
                f"run_config 'openai_base_url' must be a string when set, got {type(raw_ob).__name__}: {raw_ob!r}"
            )
        stripped = raw_ob.strip()
        if not stripped:
            raise ValueError("run_config 'openai_base_url' must be a non-empty string when set")
        config["openai_base_url"] = stripped


def load_run_config(base_dir: Path, config_path: str | None) -> tuple[dict[str, object], dict[str, Path], Path] | None:
    if not config_path:
        return None
    resolved_config_path = _resolve_path(base_dir, config_path, "run_config.json")
    if not resolved_config_path.exists():
        raise FileNotFoundError(f"run_config not found: {resolved_config_path}")
    config = json.loads(resolved_config_path.read_text(encoding="utf-8"))

    if "config_version" not in config:
        raise ValueError("run_config must include 'config_version'")

    paths = {
        "constitution_seed_path": _resolve_path(
            base_dir,
            str(config.get("constitution_seed_path", "seeds/constitution_seed.md")),
            "seeds/constitution_seed.md",
        ),
        "field_list_path": _resolve_path(
            base_dir,
            str(config.get("field_list_path", "seeds/field_list.json")),
            "seeds/field_list.json",
        ),
        "action_vocabulary_path": _resolve_path(
            base_dir,
            str(config.get("action_vocabulary_path", "seeds/action_vocabulary.json")),
            "seeds/action_vocabulary.json",
        ),
        "executor_templates_path": _resolve_path(
            base_dir,
            str(config.get("executor_templates_path", "agent/executor.py")),
            "agent/executor.py",
        ),
    }
    prompt_pack_path_value = str(config.get("prompt_pack_path", "")).strip()
    if prompt_pack_path_value:
        paths["prompt_pack_path"] = _resolve_path(base_dir, prompt_pack_path_value, prompt_pack_path_value)

    expected_hashes = {
        "constitution_seed_hash": _sha256_file(paths["constitution_seed_path"]),
        "field_list_hash": _sha256_file(paths["field_list_path"]),
        "action_vocabulary_hash": _sha256_file(paths["action_vocabulary_path"]),
        "executor_templates_hash": _sha256_file(paths["executor_templates_path"]),
    }
    if "prompt_pack_path" in paths:
        expected_hashes["prompt_pack_hash"] = _sha256_file(paths["prompt_pack_path"])
    for hash_key, actual_hash in expected_hashes.items():
        expected = config.get(hash_key)
        if expected and expected != actual_hash:
            raise ValueError(
                f"run_config hash mismatch for {hash_key}: expected {expected}, got {actual_hash}. "
                "Update the run_config hash fields to match current source files before running."
            )
        config.setdefault(hash_key, actual_hash)

    config.setdefault("constitution_seed_path", str(paths["constitution_seed_path"].relative_to(base_dir)))
    config.setdefault("field_list_path", str(paths["field_list_path"].relative_to(base_dir)))
    config.setdefault("action_vocabulary_path", str(paths["action_vocabulary_path"].relative_to(base_dir)))
    config.setdefault("executor_templates_path", str(paths["executor_templates_path"].relative_to(base_dir)))
    if "prompt_pack_path" in paths:
        config.setdefault("prompt_pack_path", str(paths["prompt_pack_path"].relative_to(base_dir)))
    _validate_run_config_modes(config)
    return config, paths, resolved_config_path


def _log_run_summary(
    public_writer: ChainWriter,
    constitution: ConstitutionManager,
    ledger_path: Path,
    ecosystem_id: str,
    agent_id: str,
    decisions_completed: int,
    run_seed: int,
    artifacts_stored: int = 0,
    run_config: dict[str, object] | None = None,
) -> None:
    action_counts = _count_full_ledger_actions(ledger_path, agent_id)

    constitution_text = constitution.read_body()
    revision_count = 0
    raw = constitution.read()
    for line in raw.splitlines():
        if line.startswith("revision_count:"):
            try:
                revision_count = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    field_chosen = None
    for line in raw.splitlines():
        if line.startswith("field_chosen:"):
            val = line.split(":", 1)[1].strip()
            if val not in {"None", "null", ""}:
                field_chosen = val

    notebook_count = 0
    notebook_path = public_writer.path.parent / "agents" / agent_id / "notebook.jsonl"
    if notebook_path.exists():
        notebook_count = sum(1 for l in notebook_path.read_text("utf-8").splitlines() if l.strip())

    payload: dict[str, object] = {
        "decisions_completed": decisions_completed,
        "run_seed": run_seed,
        "field_chosen": field_chosen,
        "constitution_revision_count": revision_count,
        "constitution_body_length": len(constitution_text),
        "action_distribution_observed": action_counts,
        "notebook_entries": notebook_count,
        "artifacts_stored": artifacts_stored,
        "run_purpose": "explore possible avenues of research",
    }
    if run_config is not None:
        payload["run_config_version"] = run_config.get("config_version")
        payload["gamma"] = run_config.get("discount_gamma", 0.99)
        payload["horizon_T"] = run_config.get("horizon_T", decisions_completed)
        payload["reward_mode"] = run_config.get("reward_mode", "sparse")
        payload["run_config"] = run_config
    public_writer.append("run.completed", payload, ecosystem_id=ecosystem_id, agent_id=agent_id)


def _extract_field_choice(response_text: str, offered_fields: list[str]) -> str:
    lowered = response_text.lower()
    for field in offered_fields:
        if field.lower() in lowered:
            return field
    return offered_fields[0]


def main(
    ecosystem_id: str | None,
    agent_id: str | None,
    model_id: str | None,
    max_decisions: int | None,
    seed: int | None,
    verbose: bool = False,
    model_spec: str | None = None,
    config_path: str | None = None,
) -> None:
    base_dir = Path(".").resolve()
    load_env(base_dir)
    run_config_data = load_run_config(base_dir, config_path)
    run_config: dict[str, object] | None = None
    run_config_paths: dict[str, Path] | None = None
    run_config_file: Path | None = None
    if run_config_data is not None:
        run_config, run_config_paths, run_config_file = run_config_data
        config_version = str(run_config.get("config_version"))
        if _version_gte(config_version, RUN_CONFIG_HARD_STOP_VERSION):
            raise SystemExit(
                f"run_config hard-stop reached at {config_version} (>= {RUN_CONFIG_HARD_STOP_VERSION})"
            )
        ecosystem_id = str(run_config.get("ecosystem_id", ecosystem_id))
        agent_id = str(run_config.get("agent_id", agent_id))
        model_id = str(run_config.get("model_id", model_id or "claude-sonnet-4-6-20250514"))
        model_spec = str(run_config.get("model_spec", model_spec or "")) or model_spec
        max_decisions = int(run_config.get("max_decisions", max_decisions or 100))
        if run_config.get("seed") is not None:
            seed = int(run_config["seed"])

    if not ecosystem_id:
        raise ValueError("ecosystem_id is required (CLI or run_config)")
    if not agent_id:
        raise ValueError("agent_id is required (CLI or run_config)")
    if not model_id:
        model_id = "claude-sonnet-4-6-20250514"
    if max_decisions is None:
        max_decisions = 100

    storage = EcosystemStorage(ecosystem_id=ecosystem_id, base_dir=base_dir)
    if "evaluation.jsonl" not in storage.blocked_for_agent():
        raise RuntimeError("blocked_for_agent sanity check failed")

    openai_base_url: str | None = None
    if run_config is not None:
        ou = run_config.get("openai_base_url")
        openai_base_url = ou if isinstance(ou, str) else None

    with storage.acquire_run_lock(agent_id):
        _run_inner(
            storage=storage,
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
            base_dir=base_dir,
            llm_model_spec=model_spec or model_id,
            openai_base_url=openai_base_url,
            max_decisions=max_decisions,
            seed=seed,
            verbose=verbose,
            run_config=run_config,
            run_config_paths=run_config_paths,
            run_config_file=run_config_file,
            constitution_seed_path=(
                run_config_paths["constitution_seed_path"] if run_config_paths else base_dir / "seeds" / "constitution_seed.md"
            ),
            field_list_path=run_config_paths["field_list_path"] if run_config_paths else base_dir / "seeds" / "field_list.json",
            action_vocabulary_path=(
                run_config_paths["action_vocabulary_path"] if run_config_paths else base_dir / "seeds" / "action_vocabulary.json"
            ),
        )


def _run_inner(
    *,
    storage: EcosystemStorage,
    ecosystem_id: str,
    agent_id: str,
    base_dir: Path,
    llm_model_spec: str,
    openai_base_url: str | None,
    max_decisions: int,
    seed: int | None,
    verbose: bool,
    run_config: dict[str, object] | None,
    run_config_paths: dict[str, Path] | None,
    run_config_file: Path | None,
    constitution_seed_path: Path,
    field_list_path: Path,
    action_vocabulary_path: Path,
) -> None:
    public_writer = ChainWriter(storage.public_ledger())
    commons_writer = ChainWriter(storage.commons_ledger())
    notebook_writer = ChainWriter(storage.agent_notebook(agent_id))
    eval_writer = ChainWriter(storage.evaluation_ledger())
    writers = {"public": public_writer, "commons": commons_writer, "notebook": notebook_writer}

    verifier_mode = str(run_config.get("verifier_mode", "warn")) if run_config is not None else "warn"
    _verify_boundary(
        eval_writer=eval_writer,
        ledger_path=storage.public_ledger(),
        boundary="start",
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
        verifier_mode=verifier_mode,
    )

    llm: LLMAdapter = create_adapter_auto(llm_model_spec, openai_base_url=openai_base_url)

    vocab = ActionVocabulary.load(action_vocabulary_path)
    blocked_leaves = set()
    if run_config is not None:
        blocked_leaves = set(str(leaf) for leaf in run_config.get("blocked_leaf_actions", []) if str(leaf).strip())
    policy = Policy(vocab, blocked_leaves=blocked_leaves)
    public_writer.append(
        "agent.policy.masks_applied",
        {
            "blocked_leaves": sorted(policy.blocked_leaves),
            "source": "config" if blocked_leaves else "none",
            "vocab_version": vocab.version,
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    # DEPRECATION(E4): Implicit defaults for memory caps below are deprecated.
    # All run_config files should carry explicit values for these keys.
    # Transition window: 2 config versions.  Removal target: v2.0.0.
    recent_events_cap = 20
    recent_notebook_cap = 5
    enable_rag = False
    rag_n_results = 5
    rag_min_relevance = 0.3
    enable_peer_context = False
    peer_context_cap = 0
    enable_forum_digest = False
    forum_digest_cap = 0
    memory_context_total_cap = 0
    enable_shared_knowledge_retrieval = False
    shared_knowledge_family_id: str | None = None
    shared_knowledge_access_profile = "default"
    shared_knowledge_n_results = 5
    shared_knowledge_min_relevance = 0.3
    shared_knowledge_grant_max_age_sec = 86400
    if run_config is not None:
        recent_events_cap = int(run_config.get("memory_recent_events_cap", recent_events_cap))
        recent_notebook_cap = int(run_config.get("memory_recent_notebook_cap", recent_notebook_cap))
        enable_rag = bool(run_config.get("enable_rag_retrieval", False))
        rag_n_results = int(run_config.get("rag_n_results", rag_n_results))
        rag_min_relevance = float(run_config.get("rag_min_relevance", rag_min_relevance))
        enable_peer_context = bool(run_config.get("enable_peer_context", False))
        peer_context_cap = int(run_config.get("peer_context_cap", 0))
        enable_forum_digest = bool(run_config.get("enable_forum_digest", False))
        forum_digest_cap = int(run_config.get("forum_digest_cap", 0))
        memory_context_total_cap = int(run_config.get("memory_context_total_cap", 0))
        enable_shared_knowledge_retrieval = bool(run_config.get("enable_shared_knowledge_retrieval", False))
        family_value = run_config.get("shared_knowledge_family_id")
        shared_knowledge_family_id = str(family_value) if family_value is not None else None
        shared_knowledge_access_profile = str(
            run_config.get("shared_knowledge_access_profile", shared_knowledge_access_profile)
        )
        shared_knowledge_n_results = int(run_config.get("shared_knowledge_n_results", shared_knowledge_n_results))
        shared_knowledge_min_relevance = float(
            run_config.get("shared_knowledge_min_relevance", shared_knowledge_min_relevance)
        )
        shared_knowledge_grant_max_age_sec = int(
            run_config.get("shared_knowledge_grant_max_age_sec", shared_knowledge_grant_max_age_sec)
        )
    state_builder = StateBuilder(
        storage,
        agent_id,
        recent_events_cap=recent_events_cap,
        recent_notebook_cap=recent_notebook_cap,
        enable_rag=enable_rag,
        rag_n_results=rag_n_results,
        rag_min_relevance=rag_min_relevance,
        vectordb_dir=base_dir / ".vectordb",
        enable_peer_context=enable_peer_context,
        peer_context_cap=peer_context_cap,
        enable_forum_digest=enable_forum_digest,
        forum_digest_cap=forum_digest_cap,
        memory_context_total_cap=memory_context_total_cap,
        enable_shared_knowledge_retrieval=enable_shared_knowledge_retrieval,
        shared_knowledge_family_id=shared_knowledge_family_id,
        shared_knowledge_access_profile=shared_knowledge_access_profile,
        shared_knowledge_n_results=shared_knowledge_n_results,
        shared_knowledge_min_relevance=shared_knowledge_min_relevance,
        shared_knowledge_grant_max_age_sec=shared_knowledge_grant_max_age_sec,
    )
    executor = Executor(
        llm=llm,
        storage=storage,
        agent_id=agent_id,
        scite_api_key=os.getenv("SCITE_API_KEY"),
        scite_partner_key=os.getenv("SCITE_PARTNER_KEY"),
        zotero_api_key=os.getenv("ZOTERO_API_KEY"),
        zotero_library_id=os.getenv("ZOTERO_LIBRARY_ID"),
        config_version=str(run_config.get("config_version")) if run_config is not None else "unversioned",
        tool_allowlist=(set(str(tool) for tool in run_config.get("tool_allowlist", [])) if run_config is not None else None),
        emit_latent_reasoning_events=(
            bool(run_config.get("emit_latent_reasoning_events", False))
            if run_config is not None
            else False
        ),
        prompt_pack=(
            _load_prompt_pack(run_config_paths["prompt_pack_path"])
            if run_config_paths is not None and "prompt_pack_path" in run_config_paths
            else None
        ),
        team_role=(
            str(run_config.get("team_role"))
            if run_config is not None and run_config.get("team_role") is not None
            else None
        ),
        research_seed_doc_ids=(
            [str(doc_id) for doc_id in run_config.get("research_seed_doc_ids", [])]
            if run_config is not None and isinstance(run_config.get("research_seed_doc_ids"), list)
            else None
        ),
        llm_effort=(
            str(run_config.get("llm_effort"))
            if run_config is not None and run_config.get("llm_effort") is not None
            else None
        ),
        llm_max_tokens=(
            int(run_config.get("llm_max_tokens", 4096))
            if run_config is not None
            else 4096
        ),
        prompt_progression=(str(run_config.get("prompt_progression", "off")) if run_config is not None else "off"),
    )
    # Secure-by-default: when run_config is present but omits tool_allowlist,
    # _parse_tool_allowlist(None) → set() → sorted to [].  The runner then
    # passes set() to Executor, blocking all tools.  When run_config is absent,
    # None is passed (allow-all).  This is intentional: using a run_config opts
    # the operator into explicit tool governance.
    public_writer.append(
        "agent.tool.allowlist_applied",
        {
            "tool_allowlist": sorted(executor.tool_allowlist) if executor.tool_allowlist is not None else None,
            "policy": "allow_all" if executor.tool_allowlist is None else "explicit_list",
        },
        ecosystem_id=ecosystem_id,
        agent_id=agent_id,
    )
    constitution = ConstitutionManager(storage, agent_id)
    monitor = KillSwitchMonitor(
        base_dir / "safety" / "kill_switch_rubric.md",
        eval_writer,
        mode=str(run_config.get("verifier_mode", "warn")) if run_config is not None else "warn",
        reward_mode=str(run_config.get("reward_mode", "sparse")) if run_config is not None else "sparse",
    )
    monitor.arm(agent_id=agent_id, rubric_version="0.1.0")

    notebook_consolidation_interval = 0
    if run_config is not None:
        notebook_consolidation_interval = int(run_config.get("notebook_consolidation_interval", 0))

    s3_sync_interval = 300
    if run_config is not None:
        offload = run_config.get("s3_offload")
        if isinstance(offload, dict):
            s3_sync_interval = int(offload.get("sync_interval_sec", 300))
    if os.environ.get("S3_SYNC_INTERVAL_SEC"):
        s3_sync_interval = int(os.environ["S3_SYNC_INTERVAL_SEC"])

    periodic_sync = _PeriodicSyncThread(storage, base_dir, run_config, interval_sec=s3_sync_interval)
    periodic_sync.start()

    run_seed = seed if seed is not None else int(time.time())
    rng = random.Random(run_seed)
    action_tally: dict[str, int] = {}

    is_mock = isinstance(llm, MockAdapter)

    if verbose:
        scite_live = executor.scite.enabled
        zotero_live = executor.zotero.enabled
        print(f"=== v1 run: {agent_id} in {ecosystem_id} ===")
        print(f"  provider: {llm.provider}  model: {llm.model_id} {'(MOCK)' if is_mock else '(LIVE)'}")
        print(f"  seed: {run_seed}  budget: {max_decisions}")
        print(f"  scite: {'ON' if scite_live else 'off'}  zotero: {'ON' if zotero_live else 'off'}")
        print()

    try:
        if not storage.agent_constitution(agent_id).exists():
            seed_text = constitution_seed_path.read_text(encoding="utf-8")
            constitution.initialize(seed_text=seed_text, ecosystem_id=ecosystem_id)
            public_writer.append(
                "agent.instantiated",
                {
                    "seed_source": str(constitution_seed_path.relative_to(base_dir)),
                    "model_id": llm.model_id,
                    "provider": llm.provider,
                },
                ecosystem_id=ecosystem_id,
                agent_id=agent_id,
            )

            offered_fields = _load_field_list_from_file(field_list_path)
            rng.shuffle(offered_fields)
            public_writer.append(
                "field.offered",
                {"fields": offered_fields},
                ecosystem_id=ecosystem_id,
                agent_id=agent_id,
            )
            field_response = llm.complete(
                system="Choose one specialization field from the list.",
                messages=[{"role": "user", "content": f"Choose one field: {offered_fields}"}],
                max_tokens=128,
                temperature=0.0,
            )
            field_chosen = _extract_field_choice(field_response.text, offered_fields)
            constitution.set_field_chosen(field_chosen)
            public_writer.append(
                "field.chosen",
                {"field": field_chosen},
                ecosystem_id=ecosystem_id,
                agent_id=agent_id,
            )

        if verbose:
            field_text = constitution.read()
            for line in field_text.splitlines():
                if line.startswith("field_chosen:"):
                    print(f"  field: {line.split(':', 1)[1].strip()}")
                    break
            print()

        _maybe_inject_external_townhall_visitor(
            storage=storage,
            public_writer=public_writer,
            run_config=run_config,
        )

        for decision_number in range(1, max_decisions + 1):
            result = step(
                policy=policy,
                executor=executor,
                state_builder=state_builder,
                writers=writers,
                agent_id=agent_id,
                ecosystem_id=ecosystem_id,
                rng=rng,
                enable_pi_reason_then_action=(
                    bool(run_config.get("enable_pi_reason_then_action", False))
                    if run_config is not None
                    else False
                ),
                decision_number=decision_number,
                max_decisions=max_decisions,
            )
            key = f"{result.top_action}/{result.sub_action}"
            action_tally[key] = action_tally.get(key, 0) + 1
            if verbose:
                preview = result.raw_output[:120].replace("\n", " ")
                print(
                    f"  [{decision_number:>3}/{max_decisions}] "
                    f"{key:<40} "
                    f"tok={result.tokens_in}+{result.tokens_out}  "
                    f"{result.latency_ms:.0f}ms"
                )
                if result.side_effects:
                    print(f"           side: {', '.join(result.side_effects)}")
                print(f"           >>> {preview}")
                print()
            monitor.evaluate(
                EventEnvelope(
                    schema_version="0.1.0",
                    event_id=f"heartbeat-{decision_number}",
                    event_type="agent.step.completed",
                    ecosystem_id=ecosystem_id,
                    agent_id=agent_id,
                    wall_time="1970-01-01T00:00:00.000000Z",
                    monotonic_ns=0,
                    payload={"decision_number": decision_number},
                    prev_hash="0" * 64,
                    record_hash="0" * 64,
                )
            )

            if (
                notebook_consolidation_interval > 0
                and decision_number % notebook_consolidation_interval == 0
            ):
                try:
                    consolidate_older_entries(
                        storage.agent_notebook(agent_id),
                        recent_cap=recent_notebook_cap,
                    )
                except Exception as consolidation_exc:
                    print(f"[consolidation] error at decision {decision_number}, continuing: {consolidation_exc}")

        _log_run_summary(
            public_writer, constitution, storage.public_ledger(),
            ecosystem_id, agent_id, max_decisions, run_seed,
            artifacts_stored=storage.count_artifacts(agent_id),
            run_config=run_config,
        )
        _verify_boundary(
            eval_writer=eval_writer,
            ledger_path=storage.public_ledger(),
            boundary="terminal",
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
            verifier_mode=verifier_mode,
        )
        monitor.evaluate(
            EventEnvelope(
                schema_version="0.1.0",
                event_id="heartbeat-run-completed",
                event_type="run.completed",
                ecosystem_id=ecosystem_id,
                agent_id=agent_id,
                wall_time="1970-01-01T00:00:00.000000Z",
                monotonic_ns=0,
                payload={"decisions_completed": max_decisions},
                prev_hash="0" * 64,
                record_hash="0" * 64,
            )
        )

        if run_config is not None and run_config_file is not None:
            run_config["config_version"] = _bump_patch(str(run_config["config_version"]))
            run_config_file.write_text(json.dumps(run_config, indent=2) + "\n", encoding="utf-8")
            if verbose:
                print(f"  next config_version: {run_config['config_version']}")

        periodic_sync.stop()
        _try_s3_sync(storage, base_dir, run_config, mode="final")

        if verbose:
            print("=== run complete ===")
            print(f"  decisions: {max_decisions}")
            print("  action tally:")
            for act, count in sorted(action_tally.items(), key=lambda x: -x[1]):
                print(f"    {act:<40} {count}")
            print()

    except KeyboardInterrupt:
        periodic_sync.stop()
        _try_s3_sync(storage, base_dir, run_config, mode="shutdown")
        public_writer.append(
            "agent.shutdown",
            {"reason": "user_interrupt", "decisions_completed": max_decisions},
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
        )
        return
    except LLMError as exc:
        periodic_sync.stop()
        _try_s3_sync(storage, base_dir, run_config, mode="shutdown")
        public_writer.append(
            "agent.error",
            {"error_type": "LLMError", "message": str(exc), "decision_number": max_decisions},
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
        )
        raise SystemExit(1) from exc
    except ChainCorruptionError as exc:
        periodic_sync.stop()
        raise SystemExit(2) from exc
    except FirewallError as exc:
        periodic_sync.stop()
        raise SystemExit(3) from exc
