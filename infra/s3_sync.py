"""S3 offload sync for stateful-indecision ecosystem data.

Implements incremental, resumable upload of JSONL ledgers and research
artifacts from local EBS to S3.  Designed for Spot-instance lifecycle:
periodic sync, post-run sync, and shutdown-budget sync.

Usage (CLI):
    python -m infra.s3_sync --ecosystem alpha --mode once
    python -m infra.s3_sync --ecosystem alpha --mode shutdown --max-seconds 90
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from infra.storage import EcosystemStorage


class LedgerCursor(BaseModel):
    rel_path: str
    uploaded_through_byte_offset: int = 0
    uploaded_through_record_hash: str = "0" * 64
    last_event_id: str = ""
    s3_key: str = ""
    updated_at_wall: str = ""


class SyncState(BaseModel):
    ecosystem_id: str
    cursors: dict[str, LedgerCursor] = Field(default_factory=dict)
    research_bundles: dict[str, list[str]] = Field(default_factory=dict)


@dataclass(frozen=True)
class S3SyncConfig:
    bucket: str
    prefix: str = ""
    region: str | None = None
    sse_mode: str = "sse-s3"
    kms_key_id: str | None = None
    research_mode: str = "bundle"
    shutdown_max_sec: int = 90
    sync_interval_sec: int = 300
    sync_min_bytes: int = 4096


def _sse_extra_args(cfg: S3SyncConfig) -> dict[str, str]:
    if cfg.sse_mode == "sse-kms" and cfg.kms_key_id:
        return {
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": cfg.kms_key_id,
        }
    return {"ServerSideEncryption": "AES256"}


def _boto_client(cfg: S3SyncConfig) -> Any:
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError as exc:
        raise ImportError(
            "boto3 is required for S3 sync. Install with: pip install '.[s3]'"
        ) from exc

    kwargs: dict[str, Any] = {}
    if cfg.region:
        kwargs["region_name"] = cfg.region
    return boto3.client(
        "s3",
        config=BotoConfig(retries={"max_attempts": 10, "mode": "standard"}),
        **kwargs,
    )


def _ecosystem_s3_prefix(cfg: S3SyncConfig, ecosystem_id: str) -> str:
    root = cfg.prefix.strip("/")
    base = f"ecosystems/{ecosystem_id}"
    return f"{root}/{base}" if root else base


def load_state(path: Path) -> SyncState:
    if not path.exists():
        return SyncState(ecosystem_id="")
    return SyncState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: SyncState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_newline_bounded_slice(path: Path, start: int) -> bytes:
    """Return bytes from *start* to the last complete line (ending with \\n).

    Per checker requirement: scan backward from file end to the last newline
    rather than trusting st_size as the boundary.  This prevents uploading
    partial lines written by a concurrent ChainWriter append.
    """
    size = path.stat().st_size
    if start >= size:
        return b""
    with path.open("rb") as fh:
        fh.seek(start)
        raw = fh.read(size - start)
    last_nl = raw.rfind(b"\n")
    if last_nl == -1:
        return b""
    return raw[: last_nl + 1]


def _parse_last_record_meta(chunk: bytes) -> tuple[str, str] | None:
    """Return (event_id, record_hash) for the last complete JSON line."""
    lines = chunk.rstrip(b"\n").split(b"\n")
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except (json.JSONDecodeError, ValueError):
        return None
    event_id = record.get("event_id", "")
    record_hash = record.get("record_hash", "")
    if not isinstance(record_hash, str) or len(record_hash) != 64:
        return None
    return event_id, record_hash


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload_ledger_incremental(
    s3: Any,
    cfg: S3SyncConfig,
    *,
    local_path: Path,
    rel_path: str,
    ecosystem_id: str,
    cursor: LedgerCursor | None,
) -> LedgerCursor | None:
    """Upload new bytes from a JSONL ledger file, resuming from cursor."""
    if not local_path.exists() or local_path.stat().st_size == 0:
        return cursor

    start = cursor.uploaded_through_byte_offset if cursor else 0
    file_size = local_path.stat().st_size

    if start > file_size:
        start = 0

    chunk = read_newline_bounded_slice(local_path, start)
    if not chunk:
        return cursor

    meta = _parse_last_record_meta(chunk)
    if meta is None:
        return cursor

    event_id, record_hash = meta
    s3_prefix = _ecosystem_s3_prefix(cfg, ecosystem_id)
    s3_key = f"{s3_prefix}/{rel_path}"
    extra_args = _sse_extra_args(cfg)

    if start == 0:
        s3.put_object(
            Bucket=cfg.bucket,
            Key=s3_key,
            Body=chunk,
            **extra_args,
        )
    else:
        existing = b""
        try:
            resp = s3.get_object(Bucket=cfg.bucket, Key=s3_key)
            existing = resp["Body"].read()
        except s3.exceptions.NoSuchKey:
            pass
        except Exception:
            existing = b""
        s3.put_object(
            Bucket=cfg.bucket,
            Key=s3_key,
            Body=existing + chunk,
            **extra_args,
        )

    from core.timestamps import wall_utc

    return LedgerCursor(
        rel_path=rel_path,
        uploaded_through_byte_offset=start + len(chunk),
        uploaded_through_record_hash=record_hash,
        last_event_id=event_id,
        s3_key=s3_key,
        updated_at_wall=wall_utc(),
    )


def bundle_and_upload_research(
    s3: Any,
    cfg: S3SyncConfig,
    *,
    storage: EcosystemStorage,
    agent_id: str,
    already_bundled: set[str],
    ecosystem_id: str,
) -> tuple[str | None, list[str]]:
    """Tar + upload research dir; return (s3_key, [member_filenames]) or (None, [])."""
    research_dir = storage.agent_research_dir(agent_id)
    json_files = sorted(
        p for p in research_dir.glob("*.json")
        if p.is_file() and p.name not in already_bundled
    )
    if not json_files:
        return None, []

    s3_prefix = _ecosystem_s3_prefix(cfg, ecosystem_id)

    if cfg.research_mode == "per_object":
        extra_args = _sse_extra_args(cfg)
        members = []
        last_key = None
        for jf in json_files:
            key = f"{s3_prefix}/agents/{agent_id}/research/{jf.name}"
            s3.put_object(
                Bucket=cfg.bucket,
                Key=key,
                Body=jf.read_bytes(),
                **extra_args,
            )
            members.append(jf.name)
            last_key = key
        return last_key, members

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for jf in json_files:
            tar.add(str(jf), arcname=jf.name)
    buf.seek(0)
    tar_bytes = buf.read()

    ts = int(time.time())
    bundle_name = f"sync_{ts}_{agent_id[:8]}.tar.gz"
    key = f"{s3_prefix}/agents/{agent_id}/research/bundles/{bundle_name}"
    extra_args = _sse_extra_args(cfg)
    s3.put_object(
        Bucket=cfg.bucket,
        Key=key,
        Body=tar_bytes,
        **extra_args,
    )
    return key, [jf.name for jf in json_files]


def upload_constitution(
    s3: Any,
    cfg: S3SyncConfig,
    *,
    local_path: Path,
    agent_id: str,
    ecosystem_id: str,
) -> str | None:
    """Upload constitution.md if it exists."""
    if not local_path.exists():
        return None
    s3_prefix = _ecosystem_s3_prefix(cfg, ecosystem_id)
    key = f"{s3_prefix}/agents/{agent_id}/constitution.md"
    extra_args = _sse_extra_args(cfg)
    s3.put_object(
        Bucket=cfg.bucket,
        Key=key,
        Body=local_path.read_bytes(),
        **extra_args,
    )
    return key


def sync_ecosystem_once(
    storage: EcosystemStorage,
    cfg: S3SyncConfig,
    *,
    state_path: Path,
    mode: str = "once",
    deadline_monotonic: float | None = None,
) -> SyncState:
    """Sync all ledgers + research for one ecosystem to S3."""
    state = load_state(state_path)
    state.ecosystem_id = storage.ecosystem_id
    s3 = _boto_client(cfg)
    ecosystem_id = storage.ecosystem_id

    def _budget_ok() -> bool:
        if deadline_monotonic is None:
            return True
        return time.monotonic() < deadline_monotonic

    for ledger_path in storage.syncable_ledger_paths():
        if not _budget_ok():
            break
        if not ledger_path.exists():
            continue
        rel = ledger_path.relative_to(storage.ecosystem_dir).as_posix()
        cursor = state.cursors.get(rel)
        new_cursor = upload_ledger_incremental(
            s3, cfg,
            local_path=ledger_path,
            rel_path=rel,
            ecosystem_id=ecosystem_id,
            cursor=cursor,
        )
        if new_cursor is not None:
            state.cursors[rel] = new_cursor

    for agent_id in storage.iter_agent_ids():
        if not _budget_ok():
            break
        paths = storage.agent_sync_paths(agent_id)

        nb_path = paths["notebook"]
        if nb_path.exists():
            rel = nb_path.relative_to(storage.ecosystem_dir).as_posix()
            cursor = state.cursors.get(rel)
            new_cursor = upload_ledger_incremental(
                s3, cfg,
                local_path=nb_path,
                rel_path=rel,
                ecosystem_id=ecosystem_id,
                cursor=cursor,
            )
            if new_cursor is not None:
                state.cursors[rel] = new_cursor

        if _budget_ok():
            upload_constitution(
                s3, cfg,
                local_path=paths["constitution"],
                agent_id=agent_id,
                ecosystem_id=ecosystem_id,
            )

        if _budget_ok():
            already = set(state.research_bundles.get(agent_id, []))
            key, members = bundle_and_upload_research(
                s3, cfg,
                storage=storage,
                agent_id=agent_id,
                already_bundled=already,
                ecosystem_id=ecosystem_id,
            )
            if key and members:
                existing = state.research_bundles.get(agent_id, [])
                existing.extend(members)
                state.research_bundles[agent_id] = existing

    save_state(state_path, state)
    return state


def config_from_env() -> S3SyncConfig | None:
    """Build S3SyncConfig from environment variables. Returns None if disabled."""
    if os.environ.get("S3_OFFLOAD_ENABLED", "0") != "1":
        return None
    bucket = os.environ.get("S3_OFFLOAD_BUCKET", "")
    if not bucket:
        return None
    return S3SyncConfig(
        bucket=bucket,
        prefix=os.environ.get("S3_OFFLOAD_PREFIX", ""),
        region=os.environ.get("AWS_REGION"),
        sse_mode=os.environ.get("S3_SSE", "sse-s3"),
        kms_key_id=os.environ.get("S3_KMS_KEY_ID"),
        research_mode=os.environ.get("S3_RESEARCH_MODE", "bundle"),
        shutdown_max_sec=int(os.environ.get("S3_SHUTDOWN_MAX_SEC", "90")),
        sync_interval_sec=int(os.environ.get("S3_SYNC_INTERVAL_SEC", "300")),
        sync_min_bytes=int(os.environ.get("S3_SYNC_MIN_BYTES", "4096")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync ecosystem data to S3")
    parser.add_argument("--ecosystem", required=True, choices=["alpha", "beta"])
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--mode",
        choices=["once", "periodic", "shutdown", "final"],
        default="once",
    )
    parser.add_argument("--max-seconds", type=int, default=None)
    args = parser.parse_args(argv)

    from infra.env import load_env
    load_env(args.base_dir.resolve())

    cfg = config_from_env()
    if cfg is None:
        print("S3 offload is disabled (S3_OFFLOAD_ENABLED != 1 or no bucket).")
        return 0

    base_dir = args.base_dir.resolve()
    storage = EcosystemStorage(args.ecosystem, base_dir)
    state_path = Path(
        os.environ.get(
            "S3_STATE_PATH",
            str(base_dir / ".sync_state" / f"{args.ecosystem}.json"),
        )
    )

    deadline = None
    if args.max_seconds is not None:
        deadline = time.monotonic() + args.max_seconds

    state = sync_ecosystem_once(
        storage, cfg,
        state_path=state_path,
        mode=args.mode,
        deadline_monotonic=deadline,
    )
    synced = len(state.cursors)
    bundled = sum(len(v) for v in state.research_bundles.values())
    print(f"Sync complete: {synced} ledger(s), {bundled} research file(s) tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
