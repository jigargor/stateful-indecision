from __future__ import annotations

from pathlib import Path

from core.writer import ChainWriter
from schemas.events import EventEnvelope


class KillSwitchMonitor:
    def __init__(
        self,
        rubric_path: Path,
        eval_writer: ChainWriter,
        mode: str = "warn",
        reward_mode: str = "sparse",
    ):
        self.rubric_path = rubric_path
        self.eval_writer = eval_writer
        self.mode = mode
        self.reward_mode = reward_mode

    def arm(self, agent_id: str, rubric_version: str) -> None:
        self.eval_writer.append(
            "safety.trigger.armed",
            {
                "rubric_path": str(self.rubric_path),
                "rubric_version": rubric_version,
            },
            ecosystem_id=self._ecosystem(),
            agent_id=agent_id,
        )

    def evaluate(self, event: EventEnvelope) -> None:
        outcome = self._classify(event)
        self.eval_writer.append(
            "safety.trigger.evaluated",
            {
                "source_event_type": event.event_type,
                "source_event_id": event.event_id,
                "outcome": outcome,
                "mode": self.mode,
                "reward_mode": self.reward_mode,
                "reward_signal": self._reward_signal(outcome),
            },
            ecosystem_id=self._ecosystem(),
            agent_id=event.agent_id,
        )
        return None

    def _ecosystem(self) -> str:
        return self.eval_writer.path.parent.name

    def _classify(self, event: EventEnvelope) -> str:
        if event.event_type == "agent.step.completed":
            decision_number = int(event.payload.get("decision_number", 0))
            if decision_number <= 0:
                return "fail"
            if decision_number % 50 == 0:
                return "warn"
            return "pass"
        if event.event_type == "agent.run.completed":
            decisions_completed = int(event.payload.get("decisions_completed", 0))
            if decisions_completed <= 0:
                return "fail"
            return "pass"
        return "warn"

    def _reward_signal(self, outcome: str) -> float:
        if self.reward_mode == "dense":
            return {"pass": 1.0, "warn": 0.2, "fail": -1.0}.get(outcome, 0.0)
        return {"pass": 1.0, "warn": 0.0, "fail": -1.0}.get(outcome, 0.0)
