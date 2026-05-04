from __future__ import annotations

from uuid import uuid4

from core.writer import ChainWriter
from forums.base import ForumBase, ForumView


class TownhallViolation(Exception):
    pass


class Townhall(ForumBase):
    def __init__(
        self,
        townhall_writer: ChainWriter,
        public_writer: ChainWriter,
        ecosystem_id: str,
    ):
        super().__init__(forum_writer=townhall_writer, public_writer=public_writer, ecosystem_id=ecosystem_id)
        self._speaker_id: str | None = None
        self._respondents: set[str] = set()
        self._convened = False

    @property
    def event_prefix(self) -> str:
        return "townhall"

    def convene(self, speaker_id: str, topic: str) -> str:
        event_id = str(uuid4())
        payload = {"speaker_id": speaker_id, "topic": topic}
        self._dual_write("townhall.convened", payload, speaker_id, event_id)
        self._speaker_id = speaker_id
        self._convened = True
        self._respondents.clear()
        return event_id

    def broadcast(self, speaker_id: str, text: str) -> str:
        if speaker_id != self._speaker_id:
            raise TownhallViolation(
                f"Only the convening speaker ('{self._speaker_id}') can broadcast. "
                f"Agent '{speaker_id}' attempted to broadcast."
            )
        event_id = str(uuid4())
        payload = {"text": text}
        self._dual_write("townhall.broadcast", payload, speaker_id, event_id)
        return event_id

    def respond(self, agent_id: str, text: str, in_response_to: str | None = None) -> str:
        if agent_id in self._respondents:
            raise TownhallViolation(
                f"Agent '{agent_id}' has already responded in this townhall session. "
                f"Only one response per agent is allowed."
            )
        event_id = str(uuid4())
        payload = {"text": text, "in_response_to": in_response_to}
        self._dual_write("townhall.response", payload, agent_id, event_id)
        self._respondents.add(agent_id)
        return event_id

    def adjourn(self, speaker_id: str) -> str:
        if speaker_id != self._speaker_id:
            raise TownhallViolation(
                f"Only the convening speaker ('{self._speaker_id}') can adjourn. "
                f"Agent '{speaker_id}' attempted to adjourn."
            )
        event_id = str(uuid4())
        payload = {"speaker_id": speaker_id, "respondent_count": len(self._respondents)}
        self._dual_write("townhall.adjourned", payload, speaker_id, event_id)
        self._convened = False
        return event_id

    def _build_view(self, current_agent: str) -> ForumView:
        records = self._read_recent_lines(200)
        utterances = [
            r for r in records
            if r.get("event_type") in {"townhall.broadcast", "townhall.response"}
        ]
        participants = list({r.get("agent_id", "") for r in records if r.get("agent_id")})
        return ForumView(utterances=utterances, participants=participants)
