"""Unpack S3 research bundles and build a local manifest for RAG ingestion.

Reads the s3_sync SyncState to find tracked research bundles, downloads and
unpacks them from S3, and writes a research_manifest.jsonl with metadata for
each artifact.  Can also index local research directories directly.

Usage:
    python -m tools.index_research --ecosystem beta --base-dir .
    python -m tools.index_research --ecosystem beta --from-s3 --base-dir .
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

from infra.storage import EcosystemStorage


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def index_local_artifacts(storage: EcosystemStorage) -> list[dict]:
    """Scan local research directories and produce manifest entries."""
    entries: list[dict] = []
    for agent_id in storage.iter_agent_ids():
        research_dir = storage.agent_research_dir(agent_id)
        for artifact_path in sorted(research_dir.glob("*.json")):
            if not artifact_path.is_file():
                continue
            try:
                data = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            content = data.get("content", "")
            structured = data.get("structured")
            summary = ""
            if isinstance(structured, dict):
                summary = structured.get("summary", "")

            entries.append({
                "artifact_id": data.get("artifact_id", artifact_path.stem),
                "agent_id": data.get("agent_id", agent_id),
                "ecosystem_id": data.get("ecosystem_id", storage.ecosystem_id),
                "action": data.get("action", ""),
                "config_version": data.get("config_version", ""),
                "created_at": data.get("created_at", ""),
                "snapshot_id": data.get("snapshot_id", ""),
                "content": content,
                "summary": summary,
                "content_hash": _content_hash(content),
                "source_path": str(artifact_path.relative_to(storage.base_dir).as_posix()),
                "source_type": "local",
            })
    return entries


def index_s3_bundles(
    storage: EcosystemStorage,
    *,
    base_dir: Path,
) -> list[dict]:
    """Download and unpack research bundles from S3, return manifest entries."""
    import boto3

    from infra.s3_sync import S3SyncConfig, config_from_env, load_state

    cfg = config_from_env()
    if cfg is None:
        print("[index_research] S3 offload not configured, skipping S3 bundles.")
        return []

    state_path = Path(
        __import__("os").environ.get(
            "S3_STATE_PATH",
            str(base_dir / ".sync_state" / f"{storage.ecosystem_id}.json"),
        )
    )
    state = load_state(state_path)

    s3 = boto3.client("s3")
    entries: list[dict] = []

    for agent_id, bundle_files in state.research_bundles.items():
        research_dir = storage.agent_research_dir(agent_id)

        for s3_key_or_name in _find_bundle_keys(s3, cfg, storage.ecosystem_id, agent_id):
            try:
                resp = s3.get_object(Bucket=cfg.bucket, Key=s3_key_or_name)
                body = resp["Body"].read()
            except Exception as exc:
                print(f"[index_research] failed to fetch {s3_key_or_name}: {exc}")
                continue

            if s3_key_or_name.endswith(".tar.gz"):
                entries.extend(
                    _unpack_tar_bundle(body, agent_id, storage, s3_key_or_name)
                )
            elif s3_key_or_name.endswith(".json"):
                entries.extend(
                    _index_single_json(body, agent_id, storage, s3_key_or_name)
                )

    return entries


def _find_bundle_keys(
    s3: Any, cfg: Any, ecosystem_id: str, agent_id: str
) -> list[str]:
    """List S3 keys under the agent's research path."""
    prefix_root = cfg.prefix.strip("/")
    base = f"ecosystems/{ecosystem_id}"
    s3_prefix = f"{prefix_root}/{base}" if prefix_root else base
    research_prefix = f"{s3_prefix}/agents/{agent_id}/research/"

    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=cfg.bucket, Prefix=research_prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _unpack_tar_bundle(
    tar_bytes: bytes,
    agent_id: str,
    storage: EcosystemStorage,
    s3_key: str,
) -> list[dict]:
    """Unpack a tar.gz bundle and return manifest entries."""
    entries: list[dict] = []
    research_dir = storage.agent_research_dir(agent_id)

    buf = io.BytesIO(tar_bytes)
    try:
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".json"):
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                raw = f.read()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                local_path = research_dir / member.name
                if not local_path.exists():
                    local_path.write_bytes(raw)

                content = data.get("content", "")
                structured = data.get("structured")
                summary = ""
                if isinstance(structured, dict):
                    summary = structured.get("summary", "")

                entries.append({
                    "artifact_id": data.get("artifact_id", member.name),
                    "agent_id": data.get("agent_id", agent_id),
                    "ecosystem_id": data.get("ecosystem_id", storage.ecosystem_id),
                    "action": data.get("action", ""),
                    "config_version": data.get("config_version", ""),
                    "created_at": data.get("created_at", ""),
                    "snapshot_id": data.get("snapshot_id", ""),
                    "content": content,
                    "summary": summary,
                    "content_hash": _content_hash(content),
                    "source_path": s3_key,
                    "source_type": "s3_bundle",
                })
    except tarfile.TarError as exc:
        print(f"[index_research] bad tar bundle {s3_key}: {exc}")

    return entries


def _index_single_json(
    raw: bytes,
    agent_id: str,
    storage: EcosystemStorage,
    s3_key: str,
) -> list[dict]:
    """Index a single JSON artifact from S3."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    content = data.get("content", "")
    structured = data.get("structured")
    summary = ""
    if isinstance(structured, dict):
        summary = structured.get("summary", "")

    return [{
        "artifact_id": data.get("artifact_id", s3_key.rsplit("/", 1)[-1]),
        "agent_id": data.get("agent_id", agent_id),
        "ecosystem_id": data.get("ecosystem_id", storage.ecosystem_id),
        "action": data.get("action", ""),
        "config_version": data.get("config_version", ""),
        "created_at": data.get("created_at", ""),
        "snapshot_id": data.get("snapshot_id", ""),
        "content": content,
        "summary": summary,
        "content_hash": _content_hash(content),
        "source_path": s3_key,
        "source_type": "s3_object",
    }]


def write_manifest(entries: list[dict], manifest_path: Path) -> None:
    """Write or append entries to a JSONL manifest, deduplicating by content_hash."""
    existing_hashes: set[str] = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_hashes.add(json.loads(line).get("content_hash", ""))
                except json.JSONDecodeError:
                    continue

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    new_count = 0
    with manifest_path.open("a", encoding="utf-8") as f:
        for entry in entries:
            if entry.get("content_hash") in existing_hashes:
                continue
            if not entry.get("content", "").strip():
                continue
            existing_hashes.add(entry["content_hash"])
            f.write(json.dumps(entry) + "\n")
            new_count += 1

    return new_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index research artifacts into a manifest for RAG ingestion"
    )
    parser.add_argument("--ecosystem", required=True, choices=["alpha", "beta"])
    parser.add_argument("--base-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--from-s3", action="store_true",
        help="Also download and unpack research bundles from S3",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Output manifest path (default: .sync_state/<ecosystem>_research_manifest.jsonl)",
    )
    args = parser.parse_args()

    from infra.env import load_env
    base_dir = args.base_dir.resolve()
    load_env(base_dir)

    storage = EcosystemStorage(args.ecosystem, base_dir)

    manifest_path = Path(args.manifest) if args.manifest else (
        base_dir / ".sync_state" / f"{args.ecosystem}_research_manifest.jsonl"
    )

    entries = index_local_artifacts(storage)
    print(f"[index_research] {len(entries)} artifacts from local research directories")

    if args.from_s3:
        s3_entries = index_s3_bundles(storage, base_dir=base_dir)
        print(f"[index_research] {len(s3_entries)} artifacts from S3 bundles")
        entries.extend(s3_entries)

    new_count = write_manifest(entries, manifest_path)
    print(f"[index_research] wrote {new_count} new entries to {manifest_path}")
    print(f"[index_research] total entries in manifest: {len(entries)}")


if __name__ == "__main__":
    main()
