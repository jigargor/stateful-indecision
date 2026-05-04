from __future__ import annotations

from uuid import uuid4

from core.writer import ChainWriter
from forums.base import ForumBase, ForumView


class RoundRobinViolation(Exception):
    pass


class Roundtable(ForumBase):
    def __init__(
        self,
        roundtable_writer: ChainWriter,
        public_writer: ChainWriter,
        ecosystem_id: str,
        participants: list[str],
    ):
        super().__init__(forum_writer=roundtable_writer, public_writer=public_writer, ecosystem_id=ecosystem_id)
        self.participants = list(participants)
        self._spoken_this_round: set[str] = set()
        self._convened = False
        self._facilitator_id: str | None = None

    @property
    def event_prefix(self) -> str:
        return "roundtable"

    def convene(self, facilitator_id: str, topic: str) -> str:
        event_id = str(uuid4())
        payload = {"facilitator_id": facilitator_id, "topic": topic, "participants": self.participants}
        self._dual_write("roundtable.convened", payload, facilitator_id, event_id)
        self._convened = True
        self._facilitator_id = facilitator_id
        return event_id

    def speak(self, agent_id: str, text: str, in_response_to: str | None = None) -> str:
        if agent_id in self._spoken_this_round:
            raise RoundRobinViolation(
                f"Agent '{agent_id}' has already spoken this round. "
                f"Call complete_round() before speaking again."
            )
        if agent_id not in self.participants:
            raise RoundRobinViolation(f"Agent '{agent_id}' is not a participant in this roundtable.")
        event_id = super().speak(agent_id, text, in_response_to)
        self._spoken_this_round.add(agent_id)
        return event_id

    def complete_round(self) -> str:
        event_id = str(uuid4())
        payload = {
            "speakers_this_round": sorted(self._spoken_this_round),
            "round_complete": len(self._spoken_this_round) == len(self.participants),
        }
        self._dual_write("roundtable.round_completed", payload, self._facilitator_id or "", event_id)
        self._spoken_this_round.clear()
        return event_id

    def adjourn(self, facilitator_id: str) -> str:
        event_id = str(uuid4())
        payload = {"facilitator_id": facilitator_id}
        self._dual_write("roundtable.adjourned", payload, facilitator_id, event_id)
        self._convened = False
        return event_id

    def _build_view(self, current_agent: str) -> ForumView:
        records = self._read_recent_lines(200)
        utterances = [r for r in records if r.get("event_type") == "roundtable.utterance"]
        return ForumView(utterances=utterances, participants=self.participants)
