from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.verifier import verify_chain


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify hash chains for an ecosystem")
    parser.add_argument("--ecosystem", required=True, help="alpha or beta")
    parser.add_argument("--base-dir", default=".", help="repo root")
    parser.add_argument("paths", nargs="*", help="additional .jsonl paths to verify")
    args = parser.parse_args()

    base = Path(args.base_dir).resolve()
    eco_dir = base / "ecosystems" / args.ecosystem

    chains: list[Path] = []
    for jsonl in sorted(eco_dir.rglob("*.jsonl")):
        chains.append(jsonl)
    for raw in args.paths:
        chains.append(Path(raw).resolve())

    if not chains:
        print(f"No .jsonl files found in {eco_dir}")
        return 1

    exit_code = 0
    for path in chains:
        if not path.exists():
            print(f"  MISSING  {path.relative_to(base)}")
            continue
        result = verify_chain(path)
        rel = path.relative_to(base) if str(path).startswith(str(base)) else path
        status = "OK" if result.valid else "FAIL"
        print(f"  {status:>6}  {rel}  ({result.total_events} events)")
        for error in result.errors:
            print(f"         line {error.line_number}: {error.error}")
        if not result.valid:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
