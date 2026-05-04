from __future__ import annotations

import time
from datetime import UTC, datetime


def wall_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def monotonic_ns() -> int:
    return time.monotonic_ns()
