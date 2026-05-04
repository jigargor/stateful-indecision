from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from core.writer import ChainWriter


@dataclass
class CommonsView:
    utterances: list[dict]
    agent_ids_present: list[str]


class Commons:
    def __init__(self, commons_writer: ChainWriter, public_writer: ChainWriter, ecosystem_id: str):
        self.commons_writer = commons_writer
        self.public_writer = public_writer
        self.ecosystem_id = ecosystem_id

    def visit(self, agent_id: str, snapshot_id: str) -> CommonsView:
        event_id = str(uuid4())
        payload = {"snapshot_id": snapshot_id}
        self._dual_write("commons.visited", payload, agent_id, event_id)
        return self._view(commons_path=self.commons_writer.path, current_agent=agent_id)

    def utter(self, agent_id: str, text: str, in_response_to: str | None = None) -> str:
        event_id = str(uuid4())
        payload = {"text": text, "in_response_to": in_response_to}
        self._dual_write("commons.utterance", payload, agent_id, event_id)
        return event_id

    def leave(self, agent_id: str, duration_steps: int) -> None:
        event_id = str(uuid4())
        payload = {"duration_steps": duration_steps}
        self._dual_write("commons.left", payload, agent_id, event_id)

    def _dual_write(self, event_type: str, payload: dict, agent_id: str, event_id: str) -> None:
        self.commons_writer.append(
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

    @staticmethod
    def _view(commons_path: Path, current_agent: str) -> CommonsView:
        utterances: list[dict] = []
        if commons_path.exists():
            for line in commons_path.read_text(encoding="utf-8").splitlines()[-200:]:
                record = json.loads(line)
                if record.get("event_type") == "commons.utterance":
                    utterances.append(record)
        return CommonsView(utterances=utterances[-100:], agent_ids_present=[current_agent])
