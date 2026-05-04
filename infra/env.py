from __future__ import annotations

from pathlib import Path


def load_env(base_dir: Path | None = None) -> None:
    """Load .env then .env.local (override). Call once at process startup."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = Path(base_dir) if base_dir else Path(".").resolve()
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.local", override=True)
