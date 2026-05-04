from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from core.writer import ChainWriter


@dataclass
class ForumView:
    utterances: list[dict] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)


class ForumBase(ABC):
    def __init__(self, forum_writer: ChainWriter, public_writer: ChainWriter, ecosystem_id: str):
        self.forum_writer = forum_writer
        self.public_writer = public_writer
        self.ecosystem_id = ecosystem_id

    @property
    @abstractmethod
    def event_prefix(self) -> str:
        ...

    def join(self, agent_id: str, snapshot_id: str) -> ForumView:
        event_id = str(uuid4())
        payload = {"snapshot_id": snapshot_id}
        self._dual_write(f"{self.event_prefix}.visited", payload, agent_id, event_id)
        return self._build_view(agent_id)

    def speak(self, agent_id: str, text: str, in_response_to: str | None = None) -> str:
        event_id = str(uuid4())
        payload = {"text": text, "in_response_to": in_response_to}
        self._dual_write(f"{self.event_prefix}.utterance", payload, agent_id, event_id)
        return event_id

    def leave(self, agent_id: str, duration_steps: int) -> None:
        event_id = str(uuid4())
        payload = {"duration_steps": duration_steps}
        self._dual_write(f"{self.event_prefix}.left", payload, agent_id, event_id)

    def _dual_write(self, event_type: str, payload: dict, agent_id: str, event_id: str) -> None:
        self.forum_writer.append(
            event_type,
            payload,
            ecosystem_id=self.ecosystem_id,
            agent_id=agent_id,
            event_id_override=event_id,
        )
        self.public_writer.append(
            event_type,
            payload,
            ecosystem_id=self.ecosystem_id,
            agent_id=agent_id,
            event_id_override=event_id,
        )

    @abstractmethod
    def _build_view(self, current_agent: str) -> ForumView:
        ...

    def _read_recent_lines(self, max_lines: int = 200) -> list[dict]:
        path = self.forum_writer.path
        if not path.exists():
            return []
        records: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-max_lines:]:
            if line.strip():
                records.append(json.loads(line))
        return records
