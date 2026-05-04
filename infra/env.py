from __future__ import annotations

import os
from pathlib import Path


def load_env(base_dir: Path | None = None) -> None:
    """Load .env then .env.local (override). Call once at process startup.

    Empty values (KEY=) are skipped so they cannot shadow credential sources
    that are resolved at runtime (e.g. EC2 instance profile / IMDS).
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        return

    root = Path(base_dir) if base_dir else Path(".").resolve()

    def _apply(path: Path, override: bool) -> None:
        if not path.exists():
            return
        for key, value in dotenv_values(path).items():
            if not value:
                continue
            if override or key not in os.environ:
                os.environ[key] = value

    _apply(root / ".env", override=False)
    _apply(root / ".env.local", override=True)
