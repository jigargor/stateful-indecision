from __future__ import annotations

from pathlib import Path

from schemas.events import ActionVocabulary


def load_action_vocabulary(path: Path) -> ActionVocabulary:
    return ActionVocabulary.load(path)
