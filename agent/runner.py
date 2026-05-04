from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

from adapters import MockAdapter, create_adapter_auto
from adapters.base import LLMAdapter
from agent.constitution_manager import ConstitutionManager
from agent.decision import step
from agent.executor import Executor
from agent.policy import Policy
from agent.state_builder import StateBuilder
from core.writer import ChainCorruptionError, ChainWriter
from infra.env import load_env
from infra.llm_client import LLMError
from infra.storage import EcosystemStorage, FirewallError
from safety.kill_switch import KillSwitchMonitor
from schemas.events import ActionVocabulary, EventEnvelope


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

    expected_hashes = {
        "constitution_seed_hash": _sha256_file(paths["constitution_seed_path"]),
        "field_list_hash": _sha256_file(paths["field_list_path"]),
        "action_vocabulary_hash": _sha256_file(paths["action_vocabulary_path"]),
        "executor_templates_hash": _sha256_file(paths["executor_templates_path"]),
    }
    for hash_key, actual_hash in expected_hashes.items():
        expected = config.get(hash_key)
        if expected and expected != actual_hash:
            print(f"[run_config warning] {hash_key} mismatch: expected {expected}, got {actual_hash}")
        config.setdefault(hash_key, actual_hash)

    config.setdefault("constitution_seed_path", str(paths["constitution_seed_path"].relative_to(base_dir)))
    config.setdefault("field_list_path", str(paths["field_list_path"].relative_to(base_dir)))
    config.setdefault("action_vocabulary_path", str(paths["action_vocabulary_path"].relative_to(base_dir)))
    config.setdefault("executor_templates_path", str(paths["executor_templates_path"].relative_to(base_dir)))
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
        if _version_gte(config_version, "0.9.9"):
            raise SystemExit(f"run_config hard-stop reached at {config_version} (>= 0.9.9)")
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

    with storage.acquire_run_lock(agent_id):
        _run_inner(
            storage=storage,
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
            base_dir=base_dir,
            llm_model_spec=model_spec or model_id,
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

    llm: LLMAdapter = create_adapter_auto(llm_model_spec)

    vocab = ActionVocabulary.load(action_vocabulary_path)
    policy = Policy(vocab)
    state_builder = StateBuilder(storage, agent_id)
    executor = Executor(
        llm=llm,
        storage=storage,
        agent_id=agent_id,
        scite_api_key=os.getenv("SCITE_API_KEY"),
        scite_partner_key=os.getenv("SCITE_PARTNER_KEY"),
        zotero_api_key=os.getenv("ZOTERO_API_KEY"),
        zotero_library_id=os.getenv("ZOTERO_LIBRARY_ID"),
        config_version=str(run_config.get("config_version")) if run_config is not None else "unversioned",
    )
    constitution = ConstitutionManager(storage, agent_id)
    monitor = KillSwitchMonitor(base_dir / "safety" / "kill_switch_rubric.md", eval_writer)
    monitor.arm(agent_id=agent_id, rubric_version="0.1.0")

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

        for decision_number in range(1, max_decisions + 1):
            result = step(
                policy=policy,
                executor=executor,
                state_builder=state_builder,
                writers=writers,
                agent_id=agent_id,
                ecosystem_id=ecosystem_id,
                rng=rng,
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

        _log_run_summary(
            public_writer, constitution, storage.public_ledger(),
            ecosystem_id, agent_id, max_decisions, run_seed,
            artifacts_stored=storage.count_artifacts(agent_id),
            run_config=run_config,
        )

        if run_config is not None and run_config_file is not None:
            run_config["config_version"] = _bump_patch(str(run_config["config_version"]))
            run_config_file.write_text(json.dumps(run_config, indent=2) + "\n", encoding="utf-8")
            if verbose:
                print(f"  next config_version: {run_config['config_version']}")

        if verbose:
            print("=== run complete ===")
            print(f"  decisions: {max_decisions}")
            print("  action tally:")
            for act, count in sorted(action_tally.items(), key=lambda x: -x[1]):
                print(f"    {act:<40} {count}")
            print()

    except KeyboardInterrupt:
        public_writer.append(
            "agent.shutdown",
            {"reason": "user_interrupt", "decisions_completed": max_decisions},
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
        )
        return
    except LLMError as exc:
        public_writer.append(
            "agent.error",
            {"error_type": "LLMError", "message": str(exc), "decision_number": max_decisions},
            ecosystem_id=ecosystem_id,
            agent_id=agent_id,
        )
        raise SystemExit(1) from exc
    except ChainCorruptionError as exc:
        raise SystemExit(2) from exc
    except FirewallError as exc:
        raise SystemExit(3) from exc
