from __future__ import annotations

import json
from pathlib import Path


def load_field_list(seeds_dir: Path) -> list[str]:
    data = json.loads((seeds_dir / "field_list.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("field_list.json must be a string list")
    if not data:
        raise ValueError("field_list.json cannot be empty")
    return data
