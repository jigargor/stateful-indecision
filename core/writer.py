from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from core.canonical_json import canonical_hash, canonical_json
from core.timestamps import monotonic_ns, wall_utc
from schemas.events import EventEnvelope


NULL_HASH = "0" * 64


class ChainWriteError(Exception):
    pass


class ChainCorruptionError(ChainWriteError):
    pass


@contextmanager
def _exclusive_lock(file_obj) -> Iterator[None]:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            file_obj.seek(0)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _read_last_json_line(path: Path) -> dict | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ChainCorruptionError(f"malformed last line in {path}") from exc


def _last_hash_from_open_file(file_obj) -> str:
    file_obj.seek(0)
    lines = file_obj.read().splitlines()
    if not lines:
        return NULL_HASH
    try:
        last_record = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ChainCorruptionError("malformed last line in chain file") from exc
    record_hash = last_record.get("record_hash")
    if not isinstance(record_hash, str) or len(record_hash) != 64:
        raise ChainCorruptionError("invalid record_hash in last line")
    return record_hash


class ChainWriter:
    def __init__(self, path: Path, schema_version: str = "0.1.0"):
        self.path = path
        self.schema_version = schema_version
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def last_hash(self) -> str:
        last_record = _read_last_json_line(self.path)
        if last_record is None:
            return NULL_HASH
        record_hash = last_record.get("record_hash")
        if not isinstance(record_hash, str) or len(record_hash) != 64:
            raise ChainCorruptionError(f"invalid record_hash in last line of {self.path}")
        return record_hash

    def append(
        self,
        event_type: str,
        payload: dict,
        *,
        ecosystem_id: str,
        agent_id: str | None = None,
        event_id_override: str | None = None,
    ) -> EventEnvelope:
        try:
            with self.path.open("r+", encoding="utf-8", newline="\n") as file_obj:
                with _exclusive_lock(file_obj):
                    prev_hash = _last_hash_from_open_file(file_obj)
                    envelope_dict = {
                        "schema_version": self.schema_version,
                        "event_id": event_id_override or str(uuid4()),
                        "event_type": event_type,
                        "ecosystem_id": ecosystem_id,
                        "agent_id": agent_id,
                        "wall_time": wall_utc(),
                        "monotonic_ns": monotonic_ns(),
                        "payload": payload,
                        "prev_hash": prev_hash,
                        "record_hash": "",
                    }
                    hash_source = dict(envelope_dict)
                    hash_source.pop("record_hash")
                    envelope_dict["record_hash"] = canonical_hash(hash_source)
                    encoded = canonical_json(envelope_dict).decode("utf-8") + "\n"
                    file_obj.seek(0, os.SEEK_END)
                    file_obj.write(encoded)
                    file_obj.flush()
                    os.fsync(file_obj.fileno())
            return EventEnvelope.model_validate(envelope_dict)
        except ChainCorruptionError:
            raise
        except Exception as exc:
            raise ChainWriteError(f"failed append to {self.path}: {exc}") from exc
