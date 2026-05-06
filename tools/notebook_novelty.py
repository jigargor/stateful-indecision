"""Notebook novelty metrics + share bundle (narrative-friendly + raw dataset).

Estimates how much notebook text is **not** already present in a **source pool**
(corpus markdown under ``corpora/<ecosystem>/`` plus, optionally, ``action.executed``
``raw_output`` from ``public.jsonl`` — i.e. material the run surfaced before
notebook capture). This is a **structural / overlap proxy**, not semantic
"truth of novelty"; treat it as a lower bound on net-new phrasing.

Metrics (per notebook entry):
- ``char_ngram_overlap``: fraction of overlapping character n-grams (see ``--ngram``)
  that also appear in the combined source pool (0 = no n-gram reuse detected).
- ``novelty_estimate``: ``1 - char_ngram_overlap`` (higher = less n-gram overlap
  with the pool).

Usage:
    python -m tools.notebook_novelty --ecosystem beta --base-dir .
    python -m tools.notebook_novelty --ecosystem beta --base-dir . \\
        --include-executed-raw --export-dir ./share_exports/beta_notebooks
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _alnum_compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _ngram_set(s: str, n: int) -> set[str]:
    t = _alnum_compact(s)
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def _overlap_fraction(notebook_text: str, source_grams: set[str], n: int) -> float:
    """Fraction of notebook n-grams that appear in source_grams."""
    grams = _ngram_set(notebook_text, n)
    if not grams:
        return 0.0
    hits = sum(1 for g in grams if g in source_grams)
    return hits / len(grams)


def _load_corpus_text(ecosystem_id: str, base_dir: Path) -> str:
    root = base_dir / "corpora" / ecosystem_id
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for p in sorted(root.rglob("*.md")):
        if p.is_file():
            try:
                parts.append(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(parts)


def _load_executed_raw_pool(
    public_path: Path,
    *,
    ecosystem_id: str,
    max_chars: int,
) -> str:
    if not public_path.exists():
        return ""
    chunks: list[str] = []
    total = 0
    for line in public_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("ecosystem_id") != ecosystem_id:
            continue
        if ev.get("event_type") != "action.executed":
            continue
        raw = (ev.get("payload") or {}).get("raw_output")
        if not isinstance(raw, str) or not raw.strip():
            continue
        piece = raw.strip()
        room = max_chars - total
        if room <= 0:
            break
        if len(piece) > room:
            piece = piece[:room]
        chunks.append(piece)
        total += len(piece)
    return "\n".join(chunks)


def _load_notebook_entries(notebook_path: Path) -> list[dict[str, object]]:
    if not notebook_path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in notebook_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event_type") != "agent.notebook.appended":
            continue
        pl = ev.get("payload") or {}
        out.append(
            {
                "event_id": ev.get("event_id", ""),
                "wall_time": ev.get("wall_time", ""),
                "agent_id": ev.get("agent_id", ""),
                "text": str(pl.get("text", "")),
                "ref_decision_id": pl.get("ref_decision_id", ""),
                "fingerprint": pl.get("fingerprint", ""),
            }
        )
    return out


@dataclass
class AgentRollup:
    agent_id: str
    entries: int
    total_chars: int
    weighted_novelty: float
    mean_overlap: float


def analyze_ecosystem(
    *,
    ecosystem_id: str,
    base_dir: Path,
    ngram: int,
    include_executed_raw: bool,
    executed_raw_max_chars: int,
) -> dict[str, object]:
    base_dir = base_dir.resolve()
    public_path = base_dir / "ecosystems" / ecosystem_id / "public.jsonl"
    agents_dir = base_dir / "ecosystems" / ecosystem_id / "agents"

    corpus = _load_corpus_text(ecosystem_id, base_dir)
    executed = ""
    if include_executed_raw:
        executed = _load_executed_raw_pool(
            public_path,
            ecosystem_id=ecosystem_id,
            max_chars=executed_raw_max_chars,
        )
    source_blob = corpus + "\n" + executed
    source_grams = _ngram_set(source_blob, ngram)

    per_agent: dict[str, list[dict[str, object]]] = {}
    rollups: list[AgentRollup] = []

    if not agents_dir.is_dir():
        return {
            "ecosystem_id": ecosystem_id,
            "ngram": ngram,
            "corpus_chars": len(corpus),
            "executed_raw_chars": len(executed),
            "source_ngrams": len(source_grams),
            "agents": {},
            "entries": [],
        }

    for agent_dir in sorted(p for p in agents_dir.iterdir() if p.is_dir()):
        agent_id = agent_dir.name
        nb_path = agent_dir / "notebook.jsonl"
        entries = _load_notebook_entries(nb_path)
        per_agent[agent_id] = []
        char_sum = 0
        weighted = 0.0
        overlaps: list[float] = []
        for row in entries:
            text = str(row["text"])
            ov = _overlap_fraction(text, source_grams, ngram)
            nov = 1.0 - ov
            char_sum += len(text)
            weighted += nov * max(1, len(text))
            overlaps.append(ov)
            per_agent[agent_id].append(
                {
                    **row,
                    "char_ngram_overlap": round(ov, 4),
                    "novelty_estimate": round(nov, 4),
                    "notebook_chars": len(text),
                }
            )
        wn = (weighted / char_sum) if char_sum else 0.0
        mo = sum(overlaps) / len(overlaps) if overlaps else 0.0
        rollups.append(
            AgentRollup(
                agent_id=agent_id,
                entries=len(entries),
                total_chars=char_sum,
                weighted_novelty=round(wn, 4),
                mean_overlap=round(mo, 4),
            )
        )

    flat_entries: list[dict[str, object]] = []
    for aid, rows in per_agent.items():
        for r in rows:
            flat_entries.append({"agent_id": aid, **r})

    return {
        "ecosystem_id": ecosystem_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ngram": ngram,
        "include_executed_raw": include_executed_raw,
        "corpus_chars": len(corpus),
        "executed_raw_chars": len(executed),
        "source_ngrams": len(source_grams),
        "agents": {
            r.agent_id: {
                "entries": r.entries,
                "total_chars": r.total_chars,
                "weighted_novelty_estimate": r.weighted_novelty,
                "mean_char_ngram_overlap": r.mean_overlap,
            }
            for r in rollups
        },
        "entries": flat_entries,
    }


def export_bundle(report: dict[str, object], export_dir: Path) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "metrics.json").write_text(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k != "entries"
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [json.dumps(e, ensure_ascii=False) for e in report["entries"]]
    (export_dir / "notebooks.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    narrative = export_dir / "NARRATIVE_STUB.md"
    eco = report["ecosystem_id"]
    narrative.write_text(
        f"# Notebook export — ecosystem `{eco}`\n\n"
        f"- **Generated:** {report.get('generated_at', '')}\n"
        f"- **N-gram size:** {report.get('ngram', '')} (character n-grams on alphanumeric-only fold)\n"
        f"- **Corpus pool chars:** {report.get('corpus_chars', 0)}\n"
        f"- **Executed raw pool chars:** {report.get('executed_raw_chars', 0)} "
        f"(included: {report.get('include_executed_raw', False)})\n\n"
        "## How to read `novelty_estimate`\n\n"
        "This is **one minus** the fraction of notebook character n-grams that also "
        "appear in the combined source pool (corpus markdown + optional `raw_output`). "
        "High values mean the notebook **phrasing** is less often byte-for-byte "
        "recoverable from that pool — not that claims are empirically novel or correct.\n\n"
        "## Per-agent rollups\n\n"
        + "\n".join(
            f"- **{aid}:** entries={blob['entries']}, chars={blob['total_chars']}, "
            f"weighted_novelty≈{blob['weighted_novelty_estimate']}, "
            f"mean_overlap≈{blob['mean_char_ngram_overlap']}"
            for aid, blob in (report.get("agents") or {}).items()
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Notebook novelty metrics + share export")
    p.add_argument("--ecosystem", required=True, help="Ecosystem ID")
    p.add_argument("--base-dir", default=".", type=Path)
    p.add_argument("--ngram", type=int, default=18, help="Character n-gram length (8–48)")
    p.add_argument(
        "--include-executed-raw",
        action="store_true",
        help="Fold action.executed raw_output from public.jsonl into the source pool",
    )
    p.add_argument(
        "--executed-raw-max-chars",
        type=int,
        default=1_500_000,
        help="Cap on executed raw text concatenated from public.jsonl",
    )
    p.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="If set, write metrics.json, notebooks.jsonl, NARRATIVE_STUB.md here",
    )
    args = p.parse_args()

    from infra.storage import validate_ecosystem_id
    eco_id = validate_ecosystem_id(args.ecosystem)

    n = max(8, min(48, args.ngram))
    report = analyze_ecosystem(
        ecosystem_id=eco_id,
        base_dir=args.base_dir,
        ngram=n,
        include_executed_raw=args.include_executed_raw,
        executed_raw_max_chars=max(10_000, args.executed_raw_max_chars),
    )

    print(json.dumps({k: v for k, v in report.items() if k != "entries"}, indent=2))
    if args.export_dir is not None:
        export_bundle(report, args.export_dir.resolve())
        print(f"\nWrote share bundle to {args.export_dir.resolve()}")


if __name__ == "__main__":
    main()
