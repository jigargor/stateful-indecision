from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core.timestamps import wall_utc

_ECOSYSTEM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")

_RESERVED_ECOSYSTEM_IDS: frozenset[str] = frozenset({
    "agents", "corpora", "evaluation",
    "public", "commons", "roundtable", "townhall",
    "tmp", "test", "none", "null", "default",
})


def validate_ecosystem_id(raw: str) -> str:
    """Validate an ecosystem ID against the grammar and return the cleaned value.

    Grammar: ``^[a-z][a-z0-9_-]{0,62}$`` — lowercase, starts with a letter,
    max 63 characters, no reserved words.
    """
    cleaned = raw.strip()
    if not _ECOSYSTEM_ID_RE.match(cleaned):
        raise ValueError(
            f"Invalid ecosystem_id {cleaned!r}: must match {_ECOSYSTEM_ID_RE.pattern} "
            f"(lowercase, starts with letter, max 63 chars)"
        )
    if cleaned in _RESERVED_ECOSYSTEM_IDS:
        raise ValueError(
            f"Invalid ecosystem_id {cleaned!r}: reserved word "
            f"(reserved: {', '.join(sorted(_RESERVED_ECOSYSTEM_IDS))})"
        )
    return cleaned


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class FirewallError(Exception):
    pass


class EcosystemStorage:
    def __init__(self, ecosystem_id: str, base_dir: Path):
        self.ecosystem_id = validate_ecosystem_id(ecosystem_id)
        self.base_dir = Path(base_dir).resolve()
        self.ecosystem_dir = (self.base_dir / "ecosystems" / self.ecosystem_id).resolve()
        self.ecosystem_dir.mkdir(parents=True, exist_ok=True)
        (self.ecosystem_dir / "agents").mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        candidate = (self.ecosystem_dir / relative).resolve()
        eco_prefix = str(self.ecosystem_dir) + os.sep
        if not (candidate == self.ecosystem_dir or str(candidate).startswith(eco_prefix)):
            raise FirewallError(f"path escapes ecosystem scope: {relative}")
        return candidate

    def public_ledger(self) -> Path:
        return self.resolve("public.jsonl")

    def evaluation_ledger(self) -> Path:
        return self.resolve("evaluation.jsonl")

    def commons_ledger(self) -> Path:
        return self.resolve("commons.jsonl")

    def agent_dir(self, agent_id: str) -> Path:
        if "/" in agent_id or "\\" in agent_id or ".." in agent_id:
            raise FirewallError("agent_id contains unsafe path segments")
        path = self.resolve(f"agents/{agent_id}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def agent_constitution(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "constitution.md"

    def agent_notebook(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "notebook.jsonl"

    def agent_research_dir(self, agent_id: str) -> Path:
        path = self.agent_dir(agent_id) / "research"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def count_artifacts(self, agent_id: str) -> int:
        research_dir = self.agent_research_dir(agent_id)
        return sum(1 for p in research_dir.glob("*.json") if p.is_file())

    def corpus_dir(self) -> Path:
        corpus_path = (self.base_dir / "corpora" / self.ecosystem_id).resolve()
        if not str(corpus_path).startswith(str(self.base_dir) + os.sep):
            raise FirewallError("corpus path outside base_dir")
        corpus_path.mkdir(parents=True, exist_ok=True)
        return corpus_path

    def roundtable_ledger(self) -> Path:
        return self.resolve("roundtable.jsonl")

    def townhall_ledger(self) -> Path:
        return self.resolve("townhall.jsonl")

    @contextmanager
    def acquire_run_lock(self, agent_id: str) -> Iterator[None]:
        if "/" in agent_id or "\\" in agent_id or ".." in agent_id:
            raise FirewallError("agent_id contains unsafe path segments")
        lock_path = self.ecosystem_dir / f".run.lock.{agent_id}"
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
                existing_pid = lock_data.get("pid")
                if existing_pid is not None and _pid_alive(existing_pid):
                    raise RuntimeError(
                        f"Another run is active for agent '{agent_id}' in ecosystem '{self.ecosystem_id}': "
                        f"agent={lock_data.get('agent_id')}, pid={existing_pid}, "
                        f"started_at={lock_data.get('started_at')}"
                    )
            except (json.JSONDecodeError, KeyError):
                pass
        lock_data = {
            "agent_id": agent_id,
            "pid": os.getpid(),
            "started_at": wall_utc(),
        }
        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        try:
            yield
        finally:
            if lock_path.exists():
                lock_path.unlink()

    def syncable_ledger_paths(self) -> list[Path]:
        """Fixed set of ecosystem-level JSONL surfaces eligible for S3 sync."""
        return [
            self.public_ledger(),
            self.evaluation_ledger(),
            self.commons_ledger(),
            self.roundtable_ledger(),
            self.townhall_ledger(),
        ]

    def iter_agent_ids(self) -> list[str]:
        """List agent subdirectory names sorted alphabetically."""
        agents_root = self.ecosystem_dir / "agents"
        if not agents_root.is_dir():
            return []
        return sorted(p.name for p in agents_root.iterdir() if p.is_dir())

    def agent_sync_paths(self, agent_id: str) -> dict[str, Path]:
        """Return paths for an agent's syncable data surfaces."""
        return {
            "notebook": self.agent_notebook(agent_id),
            "constitution": self.agent_constitution(agent_id),
            "research_dir": self.agent_research_dir(agent_id),
        }

    @staticmethod
    def blocked_for_agent() -> set[str]:
        return {"evaluation.jsonl"}
