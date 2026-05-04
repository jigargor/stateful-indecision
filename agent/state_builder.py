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
    field_chosen: str | None
    in_commons: bool
    embedding_blob_ref: None


class StateBuilder:
    def __init__(self, storage: EcosystemStorage, agent_id: str):
        self.storage = storage
        self.agent_id = agent_id
        self.constitution = ConstitutionManager(storage, agent_id)

    def build(self) -> StateSnapshot:
        public_events = self._load_jsonl(self.storage.public_ledger())
        notebook_events = self._load_jsonl(self.storage.agent_notebook(self.agent_id))
        constitution_text = self.constitution.read_body()
        field_chosen = self._frontmatter_field(self.constitution.read(), "field_chosen")

        recent_events = [event for event in public_events if event.get("agent_id") == self.agent_id][-20:]
        recent_notebook = [
            event.get("payload", {}).get("text", "")
            for event in notebook_events
            if event.get("event_type") == "agent.notebook.appended"
        ][-5:]

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

        return StateSnapshot(
            snapshot_id=str(uuid4()),
            constitution_text=constitution_text,
            recent_events=recent_events,
            recent_notebook=recent_notebook,
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
