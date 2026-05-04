"""Supervisor entrypoint for Docker containers with S3 offload.

Spawns the child command, registers SIGTERM/SIGINT handlers that trigger
a shutdown sync before forwarding the signal to the child process.

Usage (Dockerfile ENTRYPOINT):
    python -m infra.entrypoint_supervisor python -m agent --config run_config.json

Only active when S3_OFFLOAD_ENABLED=1; otherwise execs the child directly.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _run_shutdown_sync(budget_sec: int) -> None:
    ecosystem_id = os.environ.get("ECOSYSTEM_ID", "alpha")
    base_dir = os.environ.get("BASE_DIR", "/app")
    try:
        subprocess.run(
            [
                sys.executable, "-m", "infra.s3_sync",
                "--ecosystem", ecosystem_id,
                "--base-dir", base_dir,
                "--mode", "shutdown",
                "--max-seconds", str(budget_sec),
            ],
            timeout=budget_sec + 5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[supervisor] shutdown sync timed out", file=sys.stderr)
    except Exception as exc:
        print(f"[supervisor] shutdown sync failed: {exc}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m infra.entrypoint_supervisor <command> [args...]", file=sys.stderr)
        return 1

    child_args = sys.argv[1:]
    offload_enabled = os.environ.get("S3_OFFLOAD_ENABLED", "0") == "1"

    if not offload_enabled:
        os.execvp(child_args[0], child_args)

    child = subprocess.Popen(child_args)
    sync_budget = int(os.environ.get("S3_SHUTDOWN_MAX_SEC", "75"))
    received_signal = None

    def _on_term(signum: int, frame: object) -> None:
        nonlocal received_signal
        received_signal = signum
        print(f"[supervisor] received signal {signum}, running shutdown sync...", file=sys.stderr)
        _run_shutdown_sync(sync_budget)
        print("[supervisor] forwarding signal to child", file=sys.stderr)
        child.send_signal(signum)

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    exit_code = child.wait()

    if received_signal is None and offload_enabled:
        print("[supervisor] child exited cleanly, running final sync...", file=sys.stderr)
        final_budget = int(os.environ.get("S3_SHUTDOWN_MAX_SEC", "90"))
        _run_shutdown_sync(final_budget)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
