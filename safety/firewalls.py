from __future__ import annotations

from pathlib import Path

from infra.storage import EcosystemStorage, FirewallError


def validate_agent_access(storage: EcosystemStorage, agent_id: str, path: Path) -> None:
    resolved = path.resolve()
    if not str(resolved).startswith(str(storage.ecosystem_dir)):
        raise FirewallError("path outside ecosystem scope")

    if resolved.name == "evaluation.jsonl":
        raise FirewallError("agent cannot access evaluation ledger")

    agents_root = (storage.ecosystem_dir / "agents").resolve()
    if str(resolved).startswith(str(agents_root)):
        this_agent_dir = storage.agent_dir(agent_id).resolve()
        if not str(resolved).startswith(str(this_agent_dir)):
            raise FirewallError("agent cannot access another agent directory")
