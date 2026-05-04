from __future__ import annotations

import argparse
import os

from agent.runner import main


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="stateful-indecision agent runner")
    parser.add_argument("--ecosystem", default=None)
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--model", default="claude-sonnet-4-6-20250514", help="Model ID (legacy)")
    parser.add_argument(
        "--model-spec",
        default=None,
        help="provider:model format, e.g. anthropic:claude-sonnet-4-6-20250514 or openai:gpt-4o",
    )
    parser.add_argument("--max-decisions", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--config", default=None, help="Path to run_config.json; overrides individual knobs")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    os.chdir(args.base_dir)
    main(
        args.ecosystem,
        args.agent_id,
        args.model,
        args.max_decisions,
        args.seed,
        args.verbose,
        model_spec=args.model_spec,
        config_path=args.config,
    )
