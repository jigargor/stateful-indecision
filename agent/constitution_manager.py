from __future__ import annotations

import difflib
from pathlib import Path
from tempfile import NamedTemporaryFile

from core.timestamps import wall_utc
from infra.storage import EcosystemStorage
from safety.firewalls import validate_agent_access
from schemas.constitution import ConstitutionFrontmatter


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("constitution missing frontmatter start")
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        raise ValueError("constitution missing frontmatter end")
    raw_lines = text[4:end_idx].splitlines()
    body = text[end_idx + 5 :]
    data: dict[str, str] = {}
    for line in raw_lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data, body


def _render_frontmatter(frontmatter: ConstitutionFrontmatter) -> str:
    entries = [
        f"agent_id: {frontmatter.agent_id}",
        f"ecosystem_id: {frontmatter.ecosystem_id}",
        f"created_at: {frontmatter.created_at}",
        f"revision_count: {frontmatter.revision_count}",
        f"last_revised_event_id: {frontmatter.last_revised_event_id}",
        f"field_chosen: {frontmatter.field_chosen}",
    ]
    return "---\n" + "\n".join(entries) + "\n---\n"


class ConstitutionManager:
    def __init__(self, storage: EcosystemStorage, agent_id: str):
        self.storage = storage
        self.agent_id = agent_id
        self.path = storage.agent_constitution(agent_id)
        validate_agent_access(self.storage, self.agent_id, self.path)

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def read_body(self) -> str:
        _, body = _parse_frontmatter(self.read())
        return body

    def initialize(self, seed_text: str, ecosystem_id: str) -> None:
        if self.path.exists():
            return
        fm = ConstitutionFrontmatter(
            agent_id=self.agent_id,
            ecosystem_id=ecosystem_id,
            created_at=wall_utc(),
            revision_count=0,
            last_revised_event_id=None,
            field_chosen=None,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_render_frontmatter(fm) + seed_text.strip() + "\n", encoding="utf-8")

    def append_revision(self, amendment_text: str, source_event_id: str) -> str:
        old_text = self.read()
        data, body = _parse_frontmatter(old_text)
        fm = ConstitutionFrontmatter(
            agent_id=data["agent_id"],
            ecosystem_id=data["ecosystem_id"],
            created_at=data["created_at"],
            revision_count=int(data.get("revision_count", "0")) + 1,
            last_revised_event_id=source_event_id,
            field_chosen=None if data.get("field_chosen") in {"None", "", "null"} else data.get("field_chosen"),
        )
        new_body = body.rstrip() + "\n\n" + amendment_text.strip() + "\n"
        new_text = _render_frontmatter(fm) + new_body
        self._atomic_write(new_text)
        return "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile="before",
                tofile="after",
            )
        )

    def set_field_chosen(self, field: str) -> None:
        old_text = self.read()
        data, body = _parse_frontmatter(old_text)
        fm = ConstitutionFrontmatter(
            agent_id=data["agent_id"],
            ecosystem_id=data["ecosystem_id"],
            created_at=data["created_at"],
            revision_count=int(data.get("revision_count", "0")),
            last_revised_event_id=None if data.get("last_revised_event_id") in {"None", "", "null"} else data.get("last_revised_event_id"),
            field_chosen=field,
        )
        self._atomic_write(_render_frontmatter(fm) + body)

    def _atomic_write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=self.path.parent) as temp_file:
            temp_file.write(text)
            temp_name = temp_file.name
        Path(temp_name).replace(self.path)
