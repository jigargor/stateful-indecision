"""Render PNG charts + HTML index from SQLite dashboard export (no Grafana required).

Prerequisite::

    uv sync --extra charts
    uv run python -m tools.export_to_sqlite --db exports/dashboard.db --base-dir .

Then::

    uv run python -m tools.render_dashboard_graphs --base-dir . \\
        --db exports/dashboard.db --out-dir exports/dashboard_graphs

Open ``exports/dashboard_graphs/index.html`` in a browser.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401

        return matplotlib, sys.modules["matplotlib.pyplot"]
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required. Install with: uv sync --extra charts"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Render dashboard PNGs from SQLite export.")
    parser.add_argument("--db", default="exports/dashboard.db", help="SQLite DB from export_to_sqlite")
    parser.add_argument("--out-dir", default="exports/dashboard_graphs", help="Output directory")
    parser.add_argument("--base-dir", default=".", help="Repository root")
    args = parser.parse_args()

    _, plt = _require_matplotlib()

    base = Path(args.base_dir).resolve()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = (base / db_path).resolve()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (base / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise SystemExit(
            f"Database not found: {db_path}\n"
            f"Run: uv run python -m tools.export_to_sqlite --db {db_path} --base-dir {base}"
        )

    conn = sqlite3.connect(str(db_path))
    written: list[str] = []

    # 1) Top-level action mix by ecosystem (Grafana starter query #2 style)
    rows = conn.execute(
        """
        SELECT ecosystem_id,
               json_extract(payload_json, '$.top_action') AS top_action,
               COUNT(*) AS decisions
        FROM events
        WHERE event_type = 'agent.decision.taken'
        GROUP BY ecosystem_id, top_action
        ORDER BY ecosystem_id, decisions DESC
        """
    ).fetchall()

    if rows:
        fig, ax = plt.subplots(figsize=(10, max(4, len(rows) * 0.35)))
        labels = [f"{eco} — {act}" for eco, act, _ in rows]
        vals = [r[2] for r in rows]
        ax.barh(labels[::-1], vals[::-1], color="steelblue")
        ax.set_xlabel("Decisions")
        ax.set_title("Top-level actions by ecosystem")
        fig.tight_layout()
        out = out_dir / "action_mix_by_ecosystem.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        written.append(out.name)

    # 2) Event throughput by hour bucket
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m-%d %H:00:00', wall_time) AS hour_bucket,
               ecosystem_id,
               COUNT(*) AS event_count
        FROM events
        WHERE wall_time IS NOT NULL AND wall_time != ''
        GROUP BY hour_bucket, ecosystem_id
        ORDER BY hour_bucket
        """
    ).fetchall()

    if rows:
        from collections import defaultdict

        series: dict[str, dict[str, int]] = defaultdict(dict)
        hours_order: list[str] = []
        for hour_bucket, eco, cnt in rows:
            if hour_bucket not in hours_order:
                hours_order.append(hour_bucket)
            series[eco][hour_bucket] = cnt

        fig, ax = plt.subplots(figsize=(11, 5))
        x = range(len(hours_order))
        n = len(series)
        width = 0.8 / max(n, 1)
        for i, (eco, vals) in enumerate(sorted(series.items())):
            ys = [vals.get(h, 0) for h in hours_order]
            offset = (i - (n - 1) / 2) * width
            ax.bar([xi + offset for xi in x], ys, width=width * 0.9, label=eco)
        ax.set_xticks(list(x))
        ax.set_xticklabels(hours_order, rotation=45, ha="right")
        ax.set_ylabel("Events")
        ax.set_title("Event throughput over time")
        ax.legend()
        fig.tight_layout()
        out = out_dir / "events_per_hour.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        written.append(out.name)

    # 3) Runs per ecosystem/agent
    rows = conn.execute(
        """
        SELECT ecosystem_id, agent_id, COUNT(*) AS run_count,
               COALESCE(SUM(decisions_completed), 0) AS total_decisions
        FROM runs
        GROUP BY ecosystem_id, agent_id
        """
    ).fetchall()

    if rows:
        fig, ax = plt.subplots(figsize=(9, max(4, len(rows) * 0.45)))
        labels = [f"{r[0]} / {r[1]}" for r in rows]
        counts = [r[2] for r in rows]
        ax.barh(labels[::-1], counts[::-1], color="seagreen")
        ax.set_xlabel("Completed runs")
        ax.set_title("Runs per ecosystem / agent")
        fig.tight_layout()
        out = out_dir / "runs_per_agent.png"
        fig.savefig(out, dpi=120)
        plt.close(fig)
        written.append(out.name)

    conn.close()

    index = out_dir / "index.html"
    lines = [
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/><title>Ledger dashboard graphs</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:1100px;margin:1rem auto;} img{max-width:100%;border:1px solid #ddd;}</style>",
        "</head><body><h1>Ledger dashboard graphs</h1>",
        f"<p>Source DB: <code>{db_path}</code></p>",
        "<ul>",
    ]
    for name in written:
        lines.append(f'<li><h2>{name}</h2><img src="{name}" alt="{name}"/></li>')
    if not written:
        lines.append("<li>No charts generated (empty tables or no matching events).</li>")
    lines.append("</ul></body></html>")
    index.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(written)} chart(s) to {out_dir}")
    print(f"Open: file://{index}")
    if written:
        for w in written:
            print(f"  - {out_dir / w}")


if __name__ == "__main__":
    main()
