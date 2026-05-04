from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from agent.constitution_manager import ConstitutionManager
from infra.storage import EcosystemStorage


@dataclass
class StateSnapshot:
    snapshot_id: str
    constitution_text: str
    recent_events: list[dict]
    recent_notebook: list[str]
    recent_notebook_summary: str | None
    belief_state: dict[str, float]
    field_chosen: str | None
    in_commons: bool
    embedding_blob_ref: None


class StateBuilder:
    def __init__(
        self,
        storage: EcosystemStorage,
        agent_id: str,
        *,
        recent_events_cap: int = 20,
        recent_notebook_cap: int = 5,
    ):
        self.storage = storage
        self.agent_id = agent_id
        self.constitution = ConstitutionManager(storage, agent_id)
        self.recent_events_cap = recent_events_cap
        self.recent_notebook_cap = recent_notebook_cap

    def build(self) -> StateSnapshot:
        public_events = self._load_jsonl(self.storage.public_ledger())
        notebook_events = self._load_jsonl(self.storage.agent_notebook(self.agent_id))
        constitution_text = self.constitution.read_body()
        field_chosen = self._frontmatter_field(self.constitution.read(), "field_chosen")

        recent_events = [event for event in public_events if event.get("agent_id") == self.agent_id][-self.recent_events_cap :]
        all_notebook_texts = [
            event.get("payload", {}).get("text", "")
            for event in notebook_events
            if event.get("event_type") == "agent.notebook.appended"
        ]
        recent_notebook = all_notebook_texts[-self.recent_notebook_cap :]
        older_notebook = all_notebook_texts[:-self.recent_notebook_cap] if self.recent_notebook_cap > 0 else all_notebook_texts
        recent_notebook_summary = self._summarize_notebook_prefix(older_notebook)
        belief_state = self._build_belief_state(recent_events, recent_notebook, in_commons=False)

        in_commons = False
        for event in reversed(public_events):
            if event.get("agent_id") != self.agent_id:
                continue
            if event.get("event_type") == "commons.visited":
                in_commons = True
                break
            if event.get("event_type") == "commons.left":
                in_commons = False
                break
        belief_state["in_commons"] = 1.0 if in_commons else 0.0

        return StateSnapshot(
            snapshot_id=str(uuid4()),
            constitution_text=constitution_text,
            recent_events=recent_events,
            recent_notebook=recent_notebook,
            recent_notebook_summary=recent_notebook_summary,
            belief_state=belief_state,
            field_chosen=None if field_chosen in {"None", "null", ""} else field_chosen,
            in_commons=in_commons,
            embedding_blob_ref=None,
        )

    @staticmethod
    def _load_jsonl(path) -> list[dict]:
        if not path.exists():
            return []
        events: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    @staticmethod
    def _frontmatter_field(text: str, key: str) -> str | None:
        if not text.startswith("---\n"):
            return None
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return None
        for line in text[4:end_idx].splitlines():
            if line.startswith(f"{key}:"):
                return line.split(":", 1)[1].strip()
        return None

    @staticmethod
    def _summarize_notebook_prefix(texts: list[str]) -> str | None:
        if not texts:
            return None
        unique_count = len(set(texts))
        excerpt = []
        for text in texts[-2:]:
            short = " ".join(text.split())
            excerpt.append(short[:120])
        return (
            f"Older notebook context: {len(texts)} entries "
            f"({unique_count} unique). Recent older excerpts: {excerpt}"
        )

    @staticmethod
    def _build_belief_state(
        recent_events: list[dict],
        recent_notebook: list[str],
        *,
        in_commons: bool,
    ) -> dict[str, float]:
        event_type_counts: dict[str, int] = {}
        for event in recent_events:
            event_type = str(event.get("event_type", "unknown"))
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        total_events = max(sum(event_type_counts.values()), 1)
        notebook_unique = len(set(text.strip() for text in recent_notebook if text.strip()))
        notebook_total = len(recent_notebook)
        notebook_dup_ratio = 0.0
        if notebook_total:
            notebook_dup_ratio = 1.0 - (notebook_unique / notebook_total)
        return {
            "event_density": min(1.0, total_events / 20.0),
            "notebook_dup_ratio": round(notebook_dup_ratio, 4),
            "in_commons": 1.0 if in_commons else 0.0,
        }
