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


def sync_config(config_path: Path, base_dir: Path) -> bool:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    changed = False
    for hash_field, path_field in HASH_FIELDS.items():
        source_path = config.get(path_field)
        if not source_path:
            continue
        resolved = Path(source_path)
        if not resolved.is_absolute():
            resolved = (base_dir / resolved).resolve()
        if not resolved.exists():
            continue
        actual_hash = sha256_file(resolved)
        if config.get(hash_field) != actual_hash:
            config[hash_field] = actual_hash
            changed = True
    if changed:
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return changed


def discover_configs(base_dir: Path) -> list[Path]:
    return sorted(base_dir.glob("run_config*.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync hash fields in run_config JSON files.")
    parser.add_argument("--base-dir", default=".", help="Repository base directory.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Specific run_config file path(s). If omitted, updates run_config*.json in base dir.",
    )
    args = parser.parse_args()
    base_dir = Path(args.base_dir).resolve()
    configs = [Path(cfg).resolve() for cfg in args.config] if args.config else discover_configs(base_dir)

    updated = 0
    for config_path in configs:
        if sync_config(config_path, base_dir):
            updated += 1

    print(f"Updated {updated} run_config file(s).")


if __name__ == "__main__":
    main()
