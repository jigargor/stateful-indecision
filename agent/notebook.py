from __future__ import annotations

import hashlib
import json

from core.writer import ChainWriter
from schemas.events import EventEnvelope, NotebookPayload


class Notebook:
    def __init__(self, writer: ChainWriter, agent_id: str, ecosystem_id: str):
        self.writer = writer
        self.agent_id = agent_id
        self.ecosystem_id = ecosystem_id

    def append(self, text: str, ref_decision_id: str) -> EventEnvelope | None:
        fingerprint = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        if fingerprint in self._existing_fingerprints():
            return None
        payload = NotebookPayload(
            text=text,
            ref_decision_id=ref_decision_id,
            fingerprint=fingerprint,
        ).model_dump()
        return self.writer.append(
            "agent.notebook.appended",
            payload,
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )

    def _existing_fingerprints(self) -> set[str]:
        if not self.writer.path.exists():
            return set()
        fps: set[str] = set()
        for line in self.writer.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            payload = event.get("payload", {})
            fp = payload.get("fingerprint")
            if fp:
                fps.add(fp)
            else:
                fps.add(hashlib.sha256(payload.get("text", "").strip().encode("utf-8")).hexdigest())
        return fps

    def recent(self, n: int = 5) -> list[str]:
        if not self.writer.path.exists():
            return []
        texts: list[str] = []
        for line in self.writer.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event_type") == "agent.notebook.appended":
                texts.append(event.get("payload", {}).get("text", ""))
        return texts[-n:]
