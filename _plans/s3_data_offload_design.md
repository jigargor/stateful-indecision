# S3 data offload design — stateful-indecision

This document specifies how ledger-first ecosystem data under `ecosystems/<id>/` is archived from EBS-backed Docker workloads on AWS EC2 Spot to Amazon S3, with resumable sync, Spot-friendly shutdown behavior, and clear separation from the hot write path.

**Scope assumptions**

- Hot path stays **filesystem + `ChainWriter`** (`core/writer.py`); S3 is **durability offload**, not a replacement for locked `r+` appends.
- Existing integrity model: **`record_hash` / `prev_hash` chains**, canonical JSON (`core/canonical_json.py`), verifier tooling (`tools.verify_chains`).
- Container layout: codebase at `/app`, data volume at **`/app/ecosystems`** (or `base_dir` equivalent).

---

## 1. S3 bucket layout

### Recommendation

Use a **prefix mirror** of the on-disk ecosystem tree:

```text
s3://<bucket>/<optional_root_prefix>/ecosystems/<ecosystem_id>/
  public.jsonl                       # canonical key mirrors local basename
  evaluation.jsonl
  commons.jsonl
  roundtable.jsonl
  townhall.jsonl
  agents/<agent-id>/
    notebook.jsonl
    constitution.md
    research/
      <artifact_files...>
  .sync/
    manifests/<ledger_name>/<manifest_id>.json   # bookkeeping (see §4)
    incrementals/<ledger_name>/<seq>_<first_event_id>_<last_event_id>.jsonl  # optional
```

`<optional_root_prefix>` can encode environment (`prod/`, `lab/`) or AWS account shorthand so one bucket serves multiple deployments without collisions.

### Rationale

| Approach | Why not (for this project) |
|----------|----------------------------|
| **Date partitioning only** (`.../dt=2026-05-04/public.jsonl`) | Ledgers are **single growing files**. Partitioning by day forces either **duplicate full copies per day** or **non-intuitive fragmentation** that breaks `resolve("public.jsonl")`-style tooling. |
| **Flat UUID blobs** | Loses ergonomic **round-trip**: `tools/export_to_sqlite.py` and **`EcosystemStorage.resolve()`** semantics are path-oriented; recovery means extra mapping tables. |

**Mirroring relative paths**:

- **`python -m tools.verify_chains`** and **SQLite export** can run against a **`aws s3 sync`-restored directory** tree with minimal adaptation.
- Keys stay **human-auditable** in the console.
- IAM policies can scope `ecosystems/beta/*` vs `ecosystems/alpha/*`.

**`.sync/` subfolder** (under each ecosystem root on S3) holds **small JSON manifests** and optional **incremental shard objects** without polluting the agent-facing layout. If you prefer manifests outside the mirrored tree, use `s3://<bucket>/meta/<ecosystem_id>/...` instead—same idea.

### Code sketch (key builder)

```python
def s3_ecosystem_prefix(bucket: str, root_prefix: str, ecosystem_id: str) -> str:
    root = root_prefix.strip("/")
    base = f"ecosystems/{ecosystem_id}"
    return f"s3://{bucket}/{root}/{base}" if root else f"s3://{bucket}/{base}"
```

---

## 2. Sync granularity

### Recommendation

Implement a **layered policy** (all three, configurable):

1. **Periodic background sync** (default: every **N minutes** or **M MB** of new bytes per ledger, whichever comes first) while the process is healthy.
2. **Post-run hook** after a well-defined **`run.completed`** (or equivalent terminal event) for the active ecosystem—**lowest latency** to “durable in S3” without waiting for the timer.
3. **Spot / SIGTERM path**: on **`SIGTERM` / `SIGINT`**, run a **best-effort, time-bounded** sync (see §9) before `exec` replacement exits.

Disable layers via env (e.g. `S3_SYNC_ON_SHUTDOWN=0`).

### Rationale

| Strategy | Fits Spot? | Notes |
|----------|--------------|-------|
| **Per-run only** | Partial | Spot can die **between** runs; hours of ledger growth **not yet in S3**. |
| **Periodic only** | Yes | Bounded loss window **≤ interval** (plus last partial incremental). |
| **Shutdown-only** | Risky | **~2 minutes** must cover **multipart completes + large tar uploads**; good as **supplement**, not sole strategy. |

**Combination** minimizes RPO (recovery point objective) while respecting **two-minute Spot grace**: periodic work amortizes uploads; shutdown does a **small delta** Manifest + pending incrementals.

---

## 3. Artifact handling (`research/`)

### Recommendation

- **Default path (cost-conscious)**: On each sync cycle, **`tar` (or zip) each agent’s `research/` directory** into a single compressed object uploaded with **multipart** if size > threshold (e.g. **64 MiB**).

  ```text
  .../agents/<agent-id>/research/bundles/sync_<unix_ts>_<run_id_short>.tar.zst   # or .tar.gz
  ```

  Maintain a tiny **index JSON** alongside or in `.sync/manifests/research_bundles.json` listing **member filenames → sha256** for idempotency.

- **Escape hatch**: `S3_RESEARCH_MODE=per_object` to **PUT each `*.json`** when debugging or when bundle compression is undesirable (accept higher **PUT** costs).

### Rationale

- **Per-object PUT** scales **$ + request rate** with thousands of small JSON files.
- **One tarball per agent per sync** caps PUTs to **~#agents per cycle** (often 1– few).
- **zstd/gzip** shrinks egress and storage; CPU on EC2 is usually cheaper than S3 API churn.

Tar members should use **deterministic ordering** (`sorted(filenames)`) so repeated bundles of unchanged files produce **optional** reproducible hashes (for testing); production idempotency should still rely on **manifest**, not tarball hash equality.

---

## 4. Deduplication, partial uploads, and sync state

### Recommendation

Treat each **append-only ledger** (`*.jsonl`) as a **byte stream** with **line boundaries**. Persist sync state **per logical file** in a **local sqlite or JSON sidecar** under the ecosystem dir (example: **`ecosystems/<id>/.sync_state/db.sqlite`** or **`<base>/.sync_state/<ecosystem_id>.json`**—keep it **out of verifier hash chain**):

**Primary cursor (required)**

- **`uploaded_through_byte_offset`** — exclusive end offset for bytes **known to be durably committed in S3** for the **current S3 incarnation** of that object **or** for the **latest contiguous incremental shard** (see below).
- **`uploaded_through_record_hash`** — `record_hash` of the **last fully uploaded line** (parsed by scanning from previous cursor).
- **`last_event_id`** — UUID of that same line (redundant but useful for debugging).

**On sync start**

1. `fstat` local file size `S`.
2. If `cursor.byte_offset > S`, treat as **corruption/restore** → re-seed cursor from S3 manifest or **full re-upload** policy.
3. Read local file from `cursor.byte_offset` to `S` **only on newline boundaries**; if the file ends mid-line (Spot mid-append), **stop at last `\n`** so **partial lines are never uploaded**.

**Partial multipart uploads**

- Record **`upload_id` + list of completed part ETags + part sizes** in the sidecar keyed by **`(bucket, key, multipart_session_id)`**.
- On resume: **`list_parts` / `complete_multipart_upload`** before starting a conflicting session.

**Alternatives**

- **Byte-only cursor** without `record_hash` verification: simpler but weaker against **silent local truncation restore** mistakes.
- **event_id-only** cursors without bytes: ambiguous if **duplicate event_id** policy ever loosened—keep bytes as source of truth.

### Rationale

- **Offsets** align with sequential **append-only fsync’d writes** (`ChainWriter`).
- **Last hash** aligns with **`tools.verify_chains`**—after restore, verifier can prove continuity from **genesis → last synced hash**.
- Incremental uploads that **skip** malformed tail preserve the invariant: **never upload incomplete JSON lines**.

### Code sketch (state record)

```python
from pydantic import BaseModel

class LedgerSyncCursor(BaseModel):
    rel_path: str                      # "public.jsonl", "agents/foo/notebook.jsonl"
    uploaded_through_byte_offset: int  # exclusive
    uploaded_through_record_hash: str
    last_event_id: str
    s3_key_current: str                # either full object key or "latest segment" key
    updated_at_wall: str
```

### Optional: “segmented” large ledgers

If **full-object overwrites** become too large, upload **only new ranges** as:

```text
.../.sync/incrementals/public/<seq>_<first_event_id>_<last_event_id>.jsonl
```

Maintain a **`manifest.head.json`** listing ordered segments composing a **virtual file** for downstream Athena/SQLite importers. The **canonical local file remains the merged truth** on disk until prune (§5).

---

## 5. Local cleanup policy

### Recommendation

**Do not delete local ledgers solely because S3 reports success.** Adopt:

1. **Minimum local retention window** (**configurable**, default **e.g. 7–14 days** or **`max(48h, 2 × sync_interval)`**) during which **no prune** occurs even if S3 is healthy—supports **fast re-verify** and **SQLite ad-hoc** workflows.
2. **Prune policy** (only after **both**):
   - **Manifest / cursor** shows **all bytes through `record_hash` H** uploaded and **CompleteMultipartUpload** succeeded.
   - **Optional**: spot instance runs **`python -m tools.verify_chains`** (or hash-spot check) **against a temp download** or **S3 Object Lock** / **versioning** enabled for the bucket.
3. **What to prune**:
   - **Safe first**: **research JSON originals** that are **listed in a completed bundle manifest** with matching **sha256**.
   - **Ledgers**: **truncation is dangerous** while the runtime still appends. Prefer:
     - **No truncation**; rely on **larger EBS** + S3 for archive **OR**
     - **Offline compaction** as a **separate, explicit job** (not in scope here) that **rewrites** chain with migration events.

**Verifier and chains**

- **Long-term verification** should run on **either** restored files **or** on **concatenated incrementals** per manifest—**the chain math is on JSON lines**, not on file inode layout.
- If local copies are pruned, **document** that **periodic verify** must use **S3-backed inputs** (download or Athena pipeline).

### Rationale

- **S3 eventual consistency** and **application bugs** make “upload OK ⇒ delete local” unsafe for **single source of truth** research data.
- **`ChainWriter` expects local file**; truncating `public.jsonl` **in place** while a writer could run is **unsafe** without a dedicated cutover protocol.

---

## 6. Dependency impact (`boto3` and alternatives)

### Recommendation

- Add **`boto3>=1.34,<2`** (pin minor via `uv.lock`) as an **optional extra** in `pyproject.toml`, e.g. **`pip install '.[s3]'`** or project extra **`stateful-indecision[s3]`**, so **local dev** without AWS stays lean.
- Docker **production image** that needs offload: build with **`uv sync --extra s3`** (or equivalent) so **`boto3`** + **`s3transfer`** are included.

**Image size**

- Expect on the order of **~10–25 MiB** extra layers depending on base image caching—**acceptable** vs custom HTTP SigV4.

### Alternatives

| Option | Tradeoff |
|--------|----------|
| **`aioboto3`** | Async uploads; adds complexity; only worth it if sync competes with event loop. |
| **AWS CLI + subprocess** | No Python dep; **harder** structured resume, error handling, and testing. |
| **`awscrt` + `smithy`** | Smaller/slimmer long-term, **higher** implementation cost. |

**Conclusion**: **`boto3`** is the **best implementability / ops** balance for a first version.

---

## 7. Configuration

### Recommendation

**Environment variables (primary for Docker/EC2)**

| Variable | Required | Purpose |
|----------|----------|---------|
| `AWS_REGION` | Yes (or default chain) | Region for S3 client |
| `S3_OFFLOAD_BUCKET` | Yes when enabled | Target bucket |
| `S3_OFFLOAD_PREFIX` | No | Root prefix inside bucket (e.g. `prod/acct/`) |
| `S3_OFFLOAD_ENABLED` | No (`0`/`1`) | Feature gate |
| `S3_SYNC_INTERVAL_SEC` | No | Periodic timer (e.g. `300`) |
| `S3_SYNC_MIN_BYTES` | No | Coalesce until this many new bytes per file |
| `S3_SHUTDOWN_MAX_SEC` | No | Cap shutdown sync (e.g. `90` of 120s Spot) |
| `S3_RESEARCH_MODE` | No | `bundle` (default) \| `per_object` |
| `S3_STATE_PATH` | No | Override sidecar path for cursors |
| `S3_SSE` | No | `sse-s3` (default) \| `sse-kms` |
| `S3_KMS_KEY_ID` | If SSE-KMS | KMS key ARN/ID |

**Optional `run_config.json` fields** (for experiment-level overrides without rebuilding image)

```json
{
  "s3_offload": {
    "enabled": true,
    "bucket": "my-bucket",
    "prefix": "runs/beta-a1",
    "sync_interval_sec": 300,
    "research_mode": "bundle"
  }
}
```

**Precedence**: explicit **env** wins over **run_config** for overlapping keys (or document the opposite—pick one and keep it consistent).

---

## 8. Read path — cold data

### Recommendation

**Keep `EcosystemStorage` filesystem-first.** S3 remains **archive + batch analytics source**.

- **Operational reads** (agent loop, `ChainWriter`, notebooks): **local paths only**.
- **Cold / research reads**: standardize on **`aws s3 sync`** or **`python -m tools.export_to_sqlite`** against a **restored directory** or against **downloaded subset**.
- **Do not** add transparent S3 `get_object` inside **`ChainWriter`** hot path in v1.

### Rationale

- **Latency + consistency**: S3 is wrong for **locked sequential appends**.
- **Cost model**: per-request reads during training exploration explode without **local cache**.
- **Optional v2**: read-only **`S3SnapshotStore`** used **only** by offline tools, not `agent.runner`.

### Sketch (optional future helper, not wired by default)

```python
class S3EcosystemArchiveReader:
    def __init__(self, bucket: str, prefix: str, *, region: str | None = None): ...

    def download_ledger_snapshot(self, ecosystem_id: str, dest_dir: Path) -> None: ...

    def open_manifest_chain(self, ecosystem_id: str, ledger: str) -> Iterator[bytes]: ...
```

---

## 9. Docker integration and Spot lifecycle

### Recommendation

Introduce **`docker-entrypoint.sh`** chaining:

1. **Trap `TERM`/`INT`** → call **`python -m infra.s3_sync --mode shutdown`** with **`S3_SHUTDOWN_MAX_SEC`** budget → forward signal to child if needed.
2. **`exec` main command** (`python -m agent ...`) as today.
3. **In-process** (`agent.runner`): start a **`threading.Timer` / asyncio create_task** for **periodic** sync only if **`S3_OFFLOAD_ENABLED=1`**.

Alternatively, **`--wrap`** pattern:

```bash
# Pseudo
run_with_sync() {
  python -m agent "$@" &
  AGENT_PID=$!
  periodic_sync_loop &
  wait $AGENT_PID
  python -m infra.s3_sync --mode final
}
```

**Prefer trap + runner timer** so **SIGTERM hits the Python process tree** predictably **and** the shell guard still performs **last-chance sync** when the outer shell receives Spot termination (depends on **`PID 1`** behavior—prefer **`exec python -m tools.with_sync_wrapper`** Python entry if shell signals are unreliable).

**Sidecar container**

- **Possible** when using shared EBS/multi-attach (rare) or **EFS**; with **single-container Spot task**, sidecars add **minimal benefit** versus **integrated sync module**.

### Rationale

- Spot **two-minute** window → sync must be **incremental-ready** (**§4**) and **skipped** gracefully if budgets exceeded (log + retry next boot).
- **Post-run sync** aligns with natural **quiet points**.

### Sketch (`docker-entrypoint.sh` structure)

```sh
#!/bin/sh
set -e

on_term() {
  if [ "${S3_OFFLOAD_ENABLED:-0}" = "1" ]; then
    python -m infra.s3_sync --mode shutdown --max-seconds "${S3_SHUTDOWN_MAX_SEC:-90}" || true
  fi
}
trap on_term TERM INT

if [ $# -eq 0 ]; then
  set -- python -m agent --help
fi

exec "$@"
```

Note: **`exec` replaces shell with PID 1 = python** loses shell traps—**solve** by **`python`** wrapper entry:

```bash
#!/bin/sh
if [ "${S3_OFFLOAD_ENABLED:-0}" = "1" ]; then
  exec python -m infra.entrypoint_supervisor "$@"
else
  exec "$@"
fi
```

where **`entrypoint_supervisor`** registers **`signal.signal(SIGTERM, ...)`** and spawns/syncs—**recommended** over pure shell for Spot correctness.

---

## 10. Encryption and access control

### Recommendation

- **At-rest**: **`SSE-S3` (`AES256`)** as default—**zero KMS operational overhead**, adequate for many research payloads.
- **Compliance / tenant isolation**: opt-in **`SSE-KMS`** with **`S3_KMS_KEY_ID`** and bucket policy denying `s3:PutObject` without `aws:kms`-style headers (enforce via SCP or IAM).

**Access**

- **EC2 Instance Profile → IAM Role** attaching policy:

  ```json
  {
    "Effect": "Allow",
    "Action": ["s3:PutObject","s3:AbortMultipartUpload","s3:ListBucketMultipartUploads","s3:ListMultipartUploadParts","s3:GetObject"],
    "Resource": [
      "arn:aws:s3:::BUCKET/ecosystems/*",
      "arn:aws:s3:::BUCKET"
    ]
  }
  ```

  Scope tighter with **`ecosystems/alpha/*`**.

- **Avoid long-lived access keys in env**. If unavoidable (local dev), use **`AWS_PROFILE`** / **`~/.aws/credentials`** on workstation, **`NONE` env keys** on EC2.

**Bucket hardening**

- **Block public access** (account defaults).
- **Versioning ON** if you treat S3 as **audit-grade archive** (rollback + accidental delete protection).
- **Lifecycle** to **Glacier / Intelligent-Tiering** optional for cost.

---

## Reference: env / config table

| Name | Origin | Purpose |
|------|--------|---------|
| `S3_OFFLOAD_ENABLED` | Env | Gate all sync behaviors |
| `S3_OFFLOAD_BUCKET` | Env / run_config | Bucket |
| `S3_OFFLOAD_PREFIX` | Env / run_config | Key prefix inside bucket |
| `AWS_REGION` | Env | Client region |
| `AWS_STS_REGIONAL_ENDPOINTS` | Env | Optional STS behavior |
| `S3_SYNC_INTERVAL_SEC` | Env / run_config | Periodic uploads |
| `S3_SYNC_MIN_BYTES` | Env | Debounce churn |
| `S3_SHUTDOWN_MAX_SEC` | Env | Spot budget |
| `S3_RESEARCH_MODE` | Env / run_config | `bundle` vs `per_object` |
| `S3_STATE_PATH` | Env | Sidecar DB/JSON location |
| `S3_SSE` | Env | `sse-s3` / `sse-kms` |
| `S3_KMS_KEY_ID` | Env | KMS key for SSE-KMS |
| `s3_offload.*` | run_config | JSON override namespace |

---

## Complete code sketch — `infra/s3_sync.py`

Module responsibilities: **cursor IO**, **multipart upload with resume**, **ledger incremental slice**, **research bundling**, **CLI**.

```python
# infra/s3_sync.py
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import boto3
from botocore.config import Config
from pydantic import BaseModel

from infra.storage import EcosystemStorage


class LedgerCursor(BaseModel):
    rel_path: str
    uploaded_through_byte_offset: int
    uploaded_through_record_hash: str
    last_event_id: str
    s3_key: str


class SyncState(BaseModel):
    ecosystem_id: str
    cursors: dict[str, LedgerCursor]
    research_bundles: dict[str, list[str]]  # agent_id -> list of bundle keys uploaded


@dataclass(frozen=True)
class S3SyncConfig:
    bucket: str
    prefix: str
    region: str | None
    sse_mode: str  # "sse-s3" | "sse-kms"
    kms_key_id: str | None
    research_mode: str  # "bundle" | "per_object"
    shutdown_max_sec: int


def _boto_client(cfg: S3SyncConfig):
    kwargs = {}
    if cfg.region:
        kwargs["region_name"] = cfg.region
    return boto3.client(
        "s3",
        config=Config(retries={"max_attempts": 10, "mode": "standard"}),
        **kwargs,
    )


def _ecosystem_s3_prefix(cfg: S3SyncConfig, ecosystem_id: str) -> str:
    p = cfg.prefix.strip("/")
    base = f"ecosystems/{ecosystem_id}"
    return f"{p}/{base}" if p else base


def load_state(path: Path) -> SyncState: ...
def save_state(path: Path, state: SyncState) -> None: ...


def _read_newline_bounded_slice(path: Path, start: int, end: int) -> bytes:
    """Return [start, end') trimmed to last complete line within file bounds."""
    ...


def _parse_last_record_meta(chunk: bytes) -> tuple[str, str] | None:
    """Return (event_id, record_hash) for last full JSON line in chunk."""
    ...


def upload_ledger_incremental(
    s3,
    cfg: S3SyncConfig,
    *,
    local_path: Path,
    rel_path: str,
    ecosystem_id: str,
    cursor: LedgerCursor | None,
) -> LedgerCursor:
    """Multipart upload of new bytes only; resume via stored upload_id in sidecar (not shown)."""
    ...


def bundle_and_upload_research(
    s3,
    cfg: S3SyncConfig,
    *,
    storage: EcosystemStorage,
    agent_id: str,
    since_bundle_names: set[str],
) -> str | None:
    """Tar.zst research dir; return S3 key or None if nothing new."""
    ...


def sync_ecosystem_once(
    storage: EcosystemStorage,
    cfg: S3SyncConfig,
    *,
    state_path: Path,
    mode: str,  # "periodic" | "shutdown" | "final"
    deadline_monotonic: float | None = None,
) -> SyncState:
    """Core routine: update all ledgers + research according to cfg."""
    ...


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ecosystem", required=True, choices=["alpha", "beta"])
    p.add_argument("--base-dir", type=Path, default=Path(os.environ.get("BASE_DIR", ".")))
    p.add_argument("--mode", choices=["periodic", "shutdown", "final", "once"], default="once")
    p.add_argument("--max-seconds", type=int, default=None)
    args = p.parse_args(argv)

    cfg = S3SyncConfig(
        bucket=os.environ["S3_OFFLOAD_BUCKET"],
        prefix=os.environ.get("S3_OFFLOAD_PREFIX", ""),
        region=os.environ.get("AWS_REGION"),
        sse_mode=os.environ.get("S3_SSE", "sse-s3"),
        kms_key_id=os.environ.get("S3_KMS_KEY_ID"),
        research_mode=os.environ.get("S3_RESEARCH_MODE", "bundle"),
        shutdown_max_sec=int(os.environ.get("S3_SHUTDOWN_MAX_SEC", "90")),
    )
    storage = EcosystemStorage(args.ecosystem, args.base_dir)
    state_path = Path(os.environ.get("S3_STATE_PATH", args.base_dir / ".sync_state" / f"{args.ecosystem}.json"))

    deadline = None
    if args.max_seconds is not None:
        deadline = time.monotonic() + args.max_seconds

    # Register soft timeout for shutdown mode
    if args.mode == "shutdown" and deadline is not None:
        def _halt(*_):
            raise TimeoutError("shutdown sync budget exhausted")

        signal.signal(signal.SIGALRM, _halt)  # Unix only; on Windows use threading.Timer
        signal.alarm(args.max_seconds)

    sync_ecosystem_once(storage, cfg, state_path=state_path, mode=args.mode, deadline_monotonic=deadline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Notes for real implementation**

- Replace **`signal.alarm`** with **`threading.Event`** + deadline checks for **Windows** parity.
- Integrate **`list_objects_v2` / `head_object`** for sanity checks after upload.
- Map **`sse-s3` / `sse-kms`** to `ExtraArgs` on **`upload_fileobj`**.

---

## Sketch — `EcosystemStorage` extension

Keep surface area small: **optional helpers** that list syncable paths **without** changing firewall rules.

```python
# infra/storage.py (additions)

class EcosystemStorage:
    ...

    def syncable_ledger_paths(self) -> list[Path]:
        """Fixed set of ecosystem-level JSONL surfaces (agent loops use these writers)."""
        return [
            self.public_ledger(),
            self.evaluation_ledger(),
            self.commons_ledger(),
            self.roundtable_ledger(),
            self.townhall_ledger(),
        ]

    def iter_agent_ids(self) -> list[str]:
        agents_root = self.ecosystem_dir / "agents"
        if not agents_root.is_dir():
            return []
        return sorted(p.name for p in agents_root.iterdir() if p.is_dir())

    def agent_sync_paths(self, agent_id: str) -> dict[str, Path]:
        return {
            "notebook": self.agent_notebook(agent_id),
            "constitution": self.agent_constitution(agent_id),
            "research_dir": self.agent_research_dir(agent_id),
        }
```

**Non-goals here**

- No S3 client import in `storage.py`.
- **`.run.lock`** remains **local transient** and is **not uploaded** by default (optional debug flag).

---

## Sketch — Docker / supervisor entrypoint integration

**`infra/entrypoint_supervisor.py`** (new, minimal):

```python
def main():
    import os, signal, subprocess, sys, threading
    from infra.s3_sync import S3SyncConfig, sync_ecosystem_once  # illustrative
    from pathlib import Path
    from infra.storage import EcosystemStorage

    child = subprocess.Popen(sys.argv[1:])
    stop = threading.Event()

    def _sync_shutdown():
        if os.environ.get("S3_OFFLOAD_ENABLED") != "1":
            return
        eco = os.environ.get("ECOSYSTEM_ID", "alpha")
        # build cfg from env...
        sync_ecosystem_once(
            EcosystemStorage(eco, Path("/app")),  # type: ignore[arg-type]
            ...,
            mode="shutdown",
        )

    def on_term(signum, frame):
        _sync_shutdown()
        child.send_signal(signum)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    raise SystemExit(child.wait())
```

Wire Dockerfile `ENTRYPOINT` to **`python -m infra.entrypoint_supervisor`** only when offload enabled; otherwise keep current **`exec`** simplicity.

---

## Implementation checklist (for a future PR)

1. Add **`[project.optional-dependencies] s3 = ["boto3>=1.34"]`** in `pyproject.toml`; document **extra** in README (user-requested README edits optional).
2. Implement **`infra/s3_sync.py`** + **`tests/test_s3_sync_cursor.py`** using **`moto`** or botocore **Stubber**.
3. Add **`EcosystemStorage` listing helpers** and **thin runner hooks** (`agent/runner.py`) for **periodic / post-run** invocation—**never block** decision loop on S3 timeouts (thread + bounded queue).
4. Add **IAM policy** snippet to **`tools/`** or internal ops doc.

---

## Summary

| Topic | Decision |
|-------|-----------|
| Layout | Mirror `ecosystems/<id>/...` under bucket prefix + `.sync/` metadata |
| When to sync | Periodic + post-run + shutdown budget |
| Artifacts | Default **bundled tarball per agent per cycle** |
| Dedup | **Byte offset + last `record_hash`**, multipart resume sidecar |
| Local prune | Conservative; prune research after bundle manifests; **avoid truncating hot ledgers** |
| Deps | **`boto3` optional extra** |
| Reads | **Archive-only**; keep `EcosystemStorage` local |
| Docker | **Python supervisor** with **SIGTERM** sync + **in-runner periodic** |
| Security | **SSE-S3** default, **IAM role**, avoid static keys |

This design is intentionally **incremental** (first ship: **multipart incremental JSONL + bundled research + durable local state**) with a clear path to **segmented ledger objects** if single-key overwrites become too large.

---

# Checker Validation Report

**Checker model:** claude-4.6-sonnet-medium

## Verdict: PASS

No critical issues found. The hash chain is fully preserved by the local-first write model, and the design correctly keeps S3 out of the hot append path.

## Scores

| Invariant | Score |
|-----------|-------|
| Hash-chain safety | 0.97 |
| Firewall preservation | 0.93 |
| Spot-termination safety | 0.82 |
| Backward compatibility | 0.98 |
| Configuration safety | 0.99 |

## Issues Found

### Issue 1 — Sync supervisor hold-open race (major)

**Area:** Spot-termination safety

**Problem:** The sync process can hold a JSONL file open for reading while `ChainWriter.append` has the exclusive lock. On Windows, the `msvcrt.LK_LOCK` byte-range lock covers only 1 byte at offset 0, not the entire file. A concurrent read by the sync thread could capture a partial last line. If that partial line's byte offset is persisted as `uploaded_through_byte_offset`, the cursor advances past a real line boundary.

**Required fix:** The sync implementation must scan backward from the file's reported size to find the last `\n` byte and treat that as the exclusive upper bound for the upload. It must not trust `st_size` directly as the end of valid content. Document this explicitly. On Windows, note that `msvcrt` byte-range locking does not block concurrent reads from other processes.

### Issue 2 — evaluation.jsonl sync scope (minor)

**Area:** Firewall preservation

**Problem:** `syncable_ledger_paths()` includes `evaluation.jsonl`. Uploading it read-only is safe, but if a future restore path writes S3 content back to local filesystem, `evaluation.jsonl` could be overwritten by an untrusted source.

**Required fix:** Add a note: `evaluation.jsonl` may be synced read-only to S3, but any future restore path must explicitly exclude it or require operator confirmation. No code change needed now.

### Issue 3 — Concurrent prune during tool execution (minor)

**Area:** Hash-chain safety (local cleanup)

**Problem:** `verify_chains.py` and `export_to_sqlite.py` glob `research/*.json` without file locks. On Windows, deleting an open file raises `PermissionError`. The 7–14 day retention window mitigates this but the constraint is not documented.

**Required fix:** Document cleanup as an offline/maintenance operation, or implement it as a separate CLI tool with advisory docs against concurrent execution.

## Accepted Design Elements

All 10 design decisions were validated as sound:

1. **Local-first write model** — Correct and critical. No network latency or partial-write risk in the hash-chain path.
2. **Byte-offset cursor + record_hash anchor** — Defense-in-depth dedup.
3. **Partial-line filtering** — Correct handling of SIGTERM mid-append (with Issue 1 fix).
4. **Sync state in local sidecar** — Only acceptable option; writing to the chain would break verifier.
5. **No S3 import in storage.py** — Preserves backward compat and firewall isolation.
6. **boto3 as optional extra** — Standard pattern; local dev stays lean.
7. **Env-var config + S3_OFFLOAD_ENABLED gate** — No secrets in code.
8. **Conservative local cleanup** — Rejecting hot-ledger truncation is the only safe choice given `ChainWriter` reads from offset 0 on every append.
9. **Multipart crash resume** — Standard S3 pattern, no chain impact.
10. **run_config compatibility** — Optional `s3_offload` object ignored by existing code.

## Implementation Recommendations

1. **SIGTERM budget:** Allocate 75s for sync, 5s forced kill of sync, then forward SIGTERM — leave 40s for the agent's `acquire_run_lock` finally block to complete.
2. **Sidecar format:** Use `.json` or `.sqlite`, NOT `.jsonl` — `verify_chains.py` uses `rglob("*.jsonl")` and would pick up sync-state files as malformed chains.
3. **Firewall test:** Assert `syncable_ledger_paths()` calls `self.resolve()` internally to preserve the ecosystem-dir boundary.
4. **run_config.s3_offload:** Must NOT be included in `_sha256_file` hash-integrity checks (it is not a seed file).
