from __future__ import annotations

from dataclasses import dataclass

from core.writer import ChainWriter
from forums.base import ForumBase, ForumView


@dataclass
class CommonsView:
    utterances: list[dict]
    agent_ids_present: list[str]


class Commons(ForumBase):
    def __init__(self, commons_writer: ChainWriter, public_writer: ChainWriter, ecosystem_id: str):
        super().__init__(forum_writer=commons_writer, public_writer=public_writer, ecosystem_id=ecosystem_id)
        self.commons_writer = commons_writer

    @property
    def event_prefix(self) -> str:
        return "commons"

    def visit(self, agent_id: str, snapshot_id: str) -> CommonsView:
        view = self.join(agent_id, snapshot_id)
        return CommonsView(utterances=view.utterances, agent_ids_present=view.participants)

    def utter(self, agent_id: str, text: str, in_response_to: str | None = None) -> str:
        return self.speak(agent_id, text, in_response_to)

    def leave(self, agent_id: str, duration_steps: int) -> None:
        super().leave(agent_id, duration_steps)

    def _build_view(self, current_agent: str) -> ForumView:
        records = self._read_recent_lines(200)
        utterances = [r for r in records if r.get("event_type") == "commons.utterance"][-100:]
        return ForumView(utterances=utterances, participants=[current_agent])
