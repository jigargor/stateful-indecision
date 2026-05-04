from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HASH_FIELDS = {
    "constitution_seed_hash": "constitution_seed_path",
    "field_list_hash": "field_list_path",
    "action_vocabulary_hash": "action_vocabulary_path",
    "executor_templates_hash": "executor_templates_path",
    "prompt_pack_hash": "prompt_pack_path",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def check_config(config_path: Path, base_dir: Path) -> list[str]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for hash_field, path_field in HASH_FIELDS.items():
        expected_hash = config.get(hash_field)
        source_path = config.get(path_field)
        if not expected_hash or not source_path:
            continue
        resolved = Path(source_path)
        if not resolved.is_absolute():
            resolved = (base_dir / resolved).resolve()
        if not resolved.exists():
            errors.append(f"{config_path.name}: missing source file for {path_field}: {resolved}")
            continue
        actual_hash = sha256_file(resolved)
        if actual_hash != expected_hash:
            errors.append(
                f"{config_path.name}: {hash_field} mismatch (expected {expected_hash}, got {actual_hash})"
            )
    return errors


def discover_configs(base_dir: Path) -> list[Path]:
    return sorted(base_dir.glob("run_config*.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate hash fields in run_config JSON files.")
    parser.add_argument("--base-dir", default=".", help="Repository base directory.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Specific run_config file path(s). If omitted, checks run_config*.json in base dir.",
    )
    args = parser.parse_args()
    base_dir = Path(args.base_dir).resolve()
    configs = [Path(cfg).resolve() for cfg in args.config] if args.config else discover_configs(base_dir)

    if not configs:
        raise SystemExit("No run_config files found.")

    all_errors: list[str] = []
    for config_path in configs:
        all_errors.extend(check_config(config_path, base_dir))

    if all_errors:
        print("Run config hash validation FAILED:")
        for error in all_errors:
            print(f"  - {error}")
        raise SystemExit(1)

    print(f"Run config hash validation passed for {len(configs)} file(s).")


if __name__ == "__main__":
    main()
