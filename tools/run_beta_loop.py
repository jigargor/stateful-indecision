from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


CONFIGS = [
    "run_config_beta_a1.json",
    "run_config_beta_a2.json",
    "run_config_beta_a3.json",
]


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


def run_agent(base_dir: Path, config_file: str) -> None:
    command = [
        sys.executable,
        "-m",
        "agent",
        "--base-dir",
        str(base_dir),
        "--config",
        config_file,
    ]
    subprocess.run(command, check=True, cwd=base_dir)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequential beta run loop to 0.9.9")
    parser.add_argument(
        "--checkpoint-runs",
        type=int,
        default=15,
        help="Run analysis+tuning every N runs (default: 15)",
    )
    parser.add_argument(
        "--push-repo",
        default=None,
        help="Optional HF dataset repo id for checkpoint pushes",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    config_paths = [base_dir / cfg for cfg in CONFIGS]
    total_runs = 0
    checkpoint_index = 0

    while True:
        configs = [load_json(path) for path in config_paths]
        if any(version_gte(str(cfg["config_version"]), "0.9.9") for cfg in configs):
            print("[done] reached 0.9.9 hard-stop target")
            break

        for config_path, cfg in zip(config_paths, configs):
            if version_gte(str(cfg["config_version"]), "0.9.9"):
                continue
            print(
                f"[run] agent={cfg['agent_id']} version={cfg['config_version']} seed={cfg.get('seed')}"
            )
            run_agent(base_dir, config_path.name)
            total_runs += 1

            if total_runs % args.checkpoint_runs == 0:
                checkpoint_index += 1
                print(
                    f"[checkpoint] #{checkpoint_index} after {total_runs} runs: analyze + tune"
                )
                run_analysis(base_dir, args.push_repo)
                tune_action_vocabulary(base_dir, checkpoint_index)

    print(f"[summary] total_runs={total_runs}")


if __name__ == "__main__":
    main()
