from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


CONFIGS = [
    "run_config_beta_a1.json",
    "run_config_beta_a2.json",
    "run_config_beta_a3.json",
]
RUN_CONFIG_HARD_STOP_VERSION = "1.0.0"


def parse_version(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def version_gte(left: str, right: str) -> bool:
    return parse_version(left) >= parse_version(right)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def shift_weight(weights: dict[str, float], target: str, amount: float) -> dict[str, float]:
    out = dict(weights)
    if target not in out:
        out[target] = 0.0
    donor_candidates = [k for k in out if k != target and out[k] > 0]
    if not donor_candidates:
        return normalize(out)
    donor = max(donor_candidates, key=lambda key: out[key])
    delta = min(amount, out[donor])
    out[donor] -= delta
    out[target] += delta
    return normalize(out)


def normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return weights
    return {k: v / total for k, v in weights.items()}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def tune_action_vocabulary(base_dir: Path, checkpoint_index: int) -> None:
    vocab_path = base_dir / "seeds" / "action_vocabulary.json"
    vocab = load_json(vocab_path)
    weights: dict[str, dict[str, float]] = vocab.get("leaf_category_weights", {})

    beta_dir = base_dir / "ecosystems" / "beta"
    notebooks = list((beta_dir / "agents").glob("*/notebook.jsonl"))
    notebook_counts = []
    for notebook in notebooks:
        lines = [ln for ln in notebook.read_text(encoding="utf-8").splitlines() if ln.strip()]
        notebook_counts.append(len(lines))

    public_rows = read_jsonl(beta_dir / "public.jsonl")
    commons_rows = read_jsonl(beta_dir / "commons.jsonl")
    skill_events = [r for r in public_rows if r.get("event_type") == "agent.skill.authored"]
    commons_utterances = [r for r in commons_rows if r.get("event_type") == "commons.utterance"]

    changed = False

    # If notebooks are already rich, pull some weight from PONDER into RESEARCH.
    if any(count > 5 for count in notebook_counts):
        for leaf in ("SELF_REFLECT", "THINK_DEEPLY", "DEEP_PATTERN_RECOGNITION"):
            if leaf in weights:
                weights[leaf] = shift_weight(weights[leaf], "RESEARCH", 0.05)
                changed = True

    # If commons is quiet, increase RIFF affinity for common-space actions.
    rounds_seen = max(1, checkpoint_index * 5)
    if len(commons_utterances) < 5 * rounds_seen:
        for leaf in ("VISIT_COMMONS", "VISIT_ROUNDTABLE", "SHARE_IDEA"):
            if leaf in weights:
                weights[leaf] = shift_weight(weights[leaf], "RIFF", 0.06)
                changed = True

    # If no emergent skills by checkpoint 3+, boost WRITE toward PRACTICE.
    if checkpoint_index >= 3 and not skill_events and "WRITE" in weights:
        weights["WRITE"] = shift_weight(weights["WRITE"], "PRACTICE", 0.08)
        changed = True

    if not changed:
        print("[checkpoint] no action_vocabulary tuning applied")
        return

    vocab["leaf_category_weights"] = {
        leaf: normalize(leaf_weights) for leaf, leaf_weights in weights.items()
    }
    save_json(vocab_path, vocab)
    print("[checkpoint] action_vocabulary.json tuned")


def run_agent(base_dir: str, config_file: str) -> tuple[str, int]:
    """Run a single agent iteration. Returns (config_file, exit_code)."""
    command = [
        sys.executable,
        "-m",
        "agent",
        "--base-dir",
        base_dir,
        "--config",
        config_file,
    ]
    result = subprocess.run(command, cwd=base_dir)
    return config_file, result.returncode


def run_analysis(base_dir: Path, push_repo: str | None) -> None:
    command = [
        "uv",
        "run",
        "tools/analyze_run.py",
        "ecosystems/beta/public.jsonl",
    ]
    if push_repo:
        command.extend(["--push", push_repo])
    try:
        subprocess.run(command, check=True, cwd=base_dir)
    except subprocess.CalledProcessError:
        if not push_repo:
            raise
        # Keep the run loop moving even if Hub push is temporarily unavailable.
        fallback = [
            "uv",
            "run",
            "tools/analyze_run.py",
            "ecosystems/beta/public.jsonl",
        ]
        subprocess.run(fallback, check=True, cwd=base_dir)


def sync_hf_bucket(base_dir: Path, hf_bucket: str) -> None:
    """Sync ecosystem data to a HuggingFace bucket."""
    paths_to_sync = [
        ("ecosystems/beta", "ecosystems/beta"),
        (".sync_state", ".sync_state"),
    ]
    for local_rel, remote_rel in paths_to_sync:
        local_path = base_dir / local_rel
        if not local_path.exists():
            continue
        remote = f"{hf_bucket}/{remote_rel}"
        print(f"[hf-sync] {local_path} -> {remote}")
        try:
            subprocess.run(
                ["hf", "sync", str(local_path), remote],
                check=True,
                cwd=base_dir,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"[hf-sync] failed: {exc}")


def sync_s3(base_dir: Path) -> None:
    """Run S3 offload sync if enabled."""
    try:
        subprocess.run(
            [sys.executable, "-m", "infra.s3_sync", "--ecosystem", "beta", "--mode", "once"],
            check=True,
            cwd=base_dir,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[s3-sync] failed: {exc}")


def run_wave(base_dir: Path, active_configs: list[str]) -> dict[str, int]:
    """Run all active agents in parallel. Returns {config_file: exit_code}."""
    results: dict[str, int] = {}
    base_str = str(base_dir)
    with ProcessPoolExecutor(max_workers=len(active_configs)) as pool:
        futures = {
            pool.submit(run_agent, base_str, cfg): cfg
            for cfg in active_configs
        }
        for future in as_completed(futures):
            config_file, exit_code = future.result()
            results[config_file] = exit_code
            status = "ok" if exit_code == 0 else f"exit={exit_code}"
            print(f"  [{status}] {config_file}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel beta run loop")
    parser.add_argument(
        "--checkpoint-waves",
        type=int,
        default=5,
        help="Run analysis+tuning every N waves (default: 5)",
    )
    parser.add_argument(
        "--max-waves",
        type=int,
        default=None,
        help=f"Stop after N waves (default: unlimited, run until {RUN_CONFIG_HARD_STOP_VERSION})",
    )
    parser.add_argument(
        "--push-repo",
        default=None,
        help="Optional HF dataset repo id for checkpoint pushes",
    )
    parser.add_argument(
        "--hf-bucket",
        default="hf://buckets/metier/sage-train",
        help="HF bucket for checkpoint sync (default: hf://buckets/metier/sage-train)",
    )
    parser.add_argument(
        "--no-hf-sync",
        action="store_true",
        help="Disable HF bucket sync at checkpoints",
    )
    parser.add_argument(
        "--no-s3-sync",
        action="store_true",
        help="Disable S3 sync at checkpoints",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    config_paths = [base_dir / cfg for cfg in CONFIGS]
    wave_count = 0
    checkpoint_index = 0
    consecutive_wave_failures = 0

    while True:
        configs = [(path, load_json(path)) for path in config_paths]
        active = [
            (path, cfg) for path, cfg in configs
            if not version_gte(str(cfg["config_version"]), RUN_CONFIG_HARD_STOP_VERSION)
        ]

        if not active:
            print(f"[done] all agents reached {RUN_CONFIG_HARD_STOP_VERSION} hard-stop target")
            break

        if args.max_waves is not None and wave_count >= args.max_waves:
            print(f"[done] reached --max-waves={args.max_waves}")
            break

        wave_count += 1
        active_names = [cfg["agent_id"] for _, cfg in active]
        active_versions = [str(cfg["config_version"]) for _, cfg in active]
        print(f"\n[wave {wave_count}] {len(active)} agents: {', '.join(active_names)}")
        for name, ver in zip(active_names, active_versions):
            print(f"  {name} @ {ver}")

        t0 = time.monotonic()
        results = run_wave(base_dir, [path.name for path, _ in active])
        elapsed = time.monotonic() - t0
        print(f"[wave {wave_count}] completed in {elapsed:.1f}s")

        successes = sum(1 for rc in results.values() if rc == 0)
        failures = sum(1 for rc in results.values() if rc != 0)

        if successes == 0:
            consecutive_wave_failures += 1
            print(f"[warn] wave {wave_count} had 0 successes ({consecutive_wave_failures} consecutive)")
            if consecutive_wave_failures >= 3:
                print("[abort] 3 consecutive all-failure waves, stopping")
                break
        else:
            consecutive_wave_failures = 0

        if failures > 0:
            for cfg_file, rc in results.items():
                if rc != 0:
                    print(f"  [failed] {cfg_file} exit={rc}")

        if wave_count % args.checkpoint_waves == 0:
            checkpoint_index += 1
            print(f"\n[checkpoint] #{checkpoint_index} after wave {wave_count}")
            run_analysis(base_dir, args.push_repo)
            tune_action_vocabulary(base_dir, checkpoint_index)

            if not args.no_s3_sync:
                sync_s3(base_dir)
            if not args.no_hf_sync:
                sync_hf_bucket(base_dir, args.hf_bucket)

    if not args.no_s3_sync:
        sync_s3(base_dir)
    if not args.no_hf_sync:
        sync_hf_bucket(base_dir, args.hf_bucket)

    print(f"\n[summary] waves={wave_count}")


if __name__ == "__main__":
    main()
