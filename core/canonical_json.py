from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


def _reject_unsupported(value: Any) -> None:
    if isinstance(value, (datetime, date, time, UUID)):
        raise TypeError("datetime/date/time/UUID objects are not supported in canonical_json")


def _float_to_json(value: float) -> str:
    if not math.isfinite(value):
        raise TypeError("non-finite floats are not JSON-compatible")
    rounded = round(value, 6)
    if math.isclose(value, rounded, abs_tol=1e-12):
        return format(Decimal(str(rounded)).normalize(), "f")
    return format(Decimal(str(value)).normalize(), "f")


def _to_canonical_string(value: Any) -> str:
    _reject_unsupported(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _float_to_json(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_to_canonical_string(item) for item in value) + "]"
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise TypeError("canonical_json only supports string dictionary keys")
            parts.append(
                json.dumps(key, ensure_ascii=False, separators=(",", ":"))
                + ":"
                + _to_canonical_string(value[key])
            )
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"unsupported type for canonical_json: {type(value)!r}")


def canonical_json(obj: Any) -> bytes:
    return _to_canonical_string(obj).encode("utf-8")


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()
