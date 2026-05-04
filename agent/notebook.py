from __future__ import annotations

import json

from core.writer import ChainWriter
from schemas.events import EventEnvelope


class Notebook:
    def __init__(self, writer: ChainWriter, agent_id: str, ecosystem_id: str):
        self.writer = writer
        self.agent_id = agent_id
        self.ecosystem_id = ecosystem_id

    def append(self, text: str, ref_decision_id: str) -> EventEnvelope:
        return self.writer.append(
            "agent.notebook.appended",
            {"text": text, "ref_decision_id": ref_decision_id},
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )

    def recent(self, n: int = 5) -> list[str]:
        if not self.writer.path.exists():
            return []
        texts: list[str] = []
        for line in self.writer.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event_type") == "agent.notebook.appended":
                texts.append(event.get("payload", {}).get("text", ""))
        return texts[-n:]
