from __future__ import annotations

from pathlib import Path
from typing import Literal


class FirewallError(Exception):
    pass


class EcosystemStorage:
    def __init__(self, ecosystem_id: Literal["alpha", "beta"], base_dir: Path):
        if ecosystem_id not in {"alpha", "beta"}:
            raise ValueError("ecosystem_id must be 'alpha' or 'beta'")
        self.ecosystem_id = ecosystem_id
        self.base_dir = Path(base_dir).resolve()
        self.ecosystem_dir = (self.base_dir / "ecosystems" / ecosystem_id).resolve()
        self.ecosystem_dir.mkdir(parents=True, exist_ok=True)
        (self.ecosystem_dir / "agents").mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str) -> Path:
        candidate = (self.ecosystem_dir / relative).resolve()
        if not str(candidate).startswith(str(self.ecosystem_dir)):
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
        if not str(corpus_path).startswith(str(self.base_dir)):
            raise FirewallError("corpus path outside base_dir")
        corpus_path.mkdir(parents=True, exist_ok=True)
        return corpus_path

    @staticmethod
    def blocked_for_agent() -> set[str]:
        return {"evaluation.jsonl"}
