from __future__ import annotations

from pathlib import Path

from core.writer import ChainWriter
from schemas.events import EventEnvelope


class KillSwitchMonitor:
    def __init__(self, rubric_path: Path, eval_writer: ChainWriter):
        self.rubric_path = rubric_path
        self.eval_writer = eval_writer

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
        _ = event
        return None

    def _ecosystem(self) -> str:
        return self.eval_writer.path.parent.name
