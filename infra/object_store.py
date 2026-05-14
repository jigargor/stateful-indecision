from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol


class ObjectStore(Protocol):
    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None:
        ...

    def get_bytes(self, *, key: str) -> bytes:
        ...

    def list_keys(self, *, prefix: str) -> list[str]:
        ...

    def exists(self, *, key: str) -> bool:
        ...


@dataclass(frozen=True)
class S3ObjectStoreConfig:
    bucket: str
    prefix: str = ""
    region: str | None = None
    sse_mode: str = "sse-s3"
    kms_key_id: str | None = None

    def prefixed_key(self, key: str) -> str:
        root = self.prefix.strip("/")
        leaf = key.lstrip("/")
        return f"{root}/{leaf}" if root else leaf


def _sse_extra_args(cfg: S3ObjectStoreConfig) -> dict[str, str]:
    if cfg.sse_mode == "sse-kms" and cfg.kms_key_id:
        return {
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": cfg.kms_key_id,
        }
    return {"ServerSideEncryption": "AES256"}


class S3ObjectStore:
    def __init__(self, config: S3ObjectStoreConfig):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3 object storage. Install with: pip install '.[s3]'"
            ) from exc

        self.cfg = config
        kwargs: dict[str, Any] = {}
        if config.region:
            kwargs["region_name"] = config.region
        self._client = boto3.client(
            "s3",
            config=BotoConfig(retries={"max_attempts": 10, "mode": "standard"}),
            **kwargs,
        )

    def put_bytes(self, *, key: str, payload: bytes, content_type: str | None = None) -> None:
        args: dict[str, Any] = {
            "Bucket": self.cfg.bucket,
            "Key": self.cfg.prefixed_key(key),
            "Body": payload,
        }
        args.update(_sse_extra_args(self.cfg))
        if content_type:
            args["ContentType"] = content_type
        self._client.put_object(**args)

    def get_bytes(self, *, key: str) -> bytes:
        response = self._client.get_object(
            Bucket=self.cfg.bucket,
            Key=self.cfg.prefixed_key(key),
        )
        return response["Body"].read()

    def list_keys(self, *, prefix: str) -> list[str]:
        full_prefix = self.cfg.prefixed_key(prefix)
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.cfg.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if key:
                    keys.append(key)
        return keys

    def exists(self, *, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.cfg.bucket, Key=self.cfg.prefixed_key(key))
            return True
        except Exception:
            return False

    def put_json(self, *, key: str, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.put_bytes(key=key, payload=blob, content_type="application/json")

    def get_json(self, *, key: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(key=key).decode("utf-8"))


def s3_object_store_from_env() -> S3ObjectStore | None:
    enabled = os.environ.get("S3_OFFLOAD_ENABLED", "0") == "1"
    bucket = os.environ.get("S3_OFFLOAD_BUCKET", "").strip()
    if not enabled or not bucket:
        return None
    cfg = S3ObjectStoreConfig(
        bucket=bucket,
        prefix=os.environ.get("S3_OFFLOAD_PREFIX", ""),
        region=os.environ.get("AWS_REGION"),
        sse_mode=os.environ.get("S3_SSE", "sse-s3"),
        kms_key_id=os.environ.get("S3_KMS_KEY_ID"),
    )
    return S3ObjectStore(cfg)
