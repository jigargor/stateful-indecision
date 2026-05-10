# Grafana dashboard (SQLite)

Quick path from repo data to `tools/grafana_dashboard_template.json`.

## Static PNG/HTML (no Grafana)

To generate charts without installing Grafana:

```bash
uv sync --extra charts
uv run python -m tools.export_to_sqlite --db exports/dashboard.db --base-dir .
uv run python -m tools.render_dashboard_graphs --base-dir . --db exports/dashboard.db --out-dir exports/dashboard_graphs
```

Open `exports/dashboard_graphs/index.html` in a browser (or open the `.png` files directly).

## 1. Export SQLite (from repo root)

```bash
python -m tools.export_to_sqlite --db dashboard.db --base-dir .
```

This writes `dashboard.db` in the current directory (override `--db` / `--base-dir` if you prefer). Re-run after new ledger or research data.

## 2. Install the SQLite datasource plugin

In Grafana: **Administration** → **Plugins and data** → **Plugins** → search **SQLite** → install **frser-sqlite-datasource** (Frser).

Restart Grafana if the UI prompts you.

## 3. Add the SQLite data source

**Connections** → **Add new connection** → choose **SQLite** (frser).

Configure:

- **Path**: absolute path to `dashboard.db`.  
  Example (Windows): `C:\Users\you\Documents\2026\stateful-indecision\dashboard.db`  
  Example (Unix): `/home/you/stateful-indecision/dashboard.db`

Save & test (**Save & test**).

## 4. Import the dashboard

**Dashboards** → **New** → **Import** → **Upload dashboard JSON file** → select `tools/grafana_dashboard_template.json`.

On the import screen:

- Set **Name** / folder as you like.
- Under **DS_SQLITE**, pick the SQLite datasource you created (this maps `${DS_SQLITE}` in the JSON).

**Import**.

Panels should load SQL queries against `events`, `artifacts`, and `runs`. If queries fail, confirm the DB path and that you re-exported after adding data.

## 4.1 Panels in the dashboard template

The template ships 9 panels (IDs 1–9). Panels 1–5 cover baseline operational
metrics; panels 6–9 add the Wave 4 observability extension.

### Baseline panels (pre-existing)

| ID | Title | Source query | Type |
|----|-------|--------------|------|
| 1 | Event Throughput by Ecosystem | Query 1 | timeseries |
| 2 | Beta Top Action Mix | Query 2 | piechart |
| 3 | Collaboration Signals (Alpha vs Beta) | Query 4 | barchart |
| 4 | Notebook Duplicate Ratio by Agent | Query 5 | table |
| 5 | Run Progression by Agent | Query 6 | table |

### Wave 4 panels

| ID | Title | Source query | Type |
|----|-------|--------------|------|
| 6 | Decision Latency Distribution (p50/p95) | Query 10 | table |
| 7 | Tokens per Decision by Agent | Query 11 | table |
| 8 | Stop Reason Mix Over Time | Query 12 | barchart (stacked) |
| 9 | Action Mix Over Time | Query 13 | barchart (stacked) |

### Panel details

**Panel 6 — Decision Latency Distribution (p50/p95)**
- Uses a CTE with `ROW_NUMBER()` to approximate p50 and p95 per ecosystem/agent.
- Columns: `ecosystem_id`, `agent_id`, `sample_count`, `min_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `max_latency_ms`.
- Alternative: use query **8** as the raw data source and add a Grafana "Stats" transformation to compute percentiles interactively.

**Panel 7 — Tokens per Decision by Agent**
- Aggregates `tokens_in`, `tokens_out`, and total across all `action.executed` events.
- Columns: `ecosystem_id`, `agent_id`, `executions`, `total_tokens_in`, `total_tokens_out`, `total_tokens`, `avg_tokens_per_decision`.

**Panel 8 — Stop Reason Mix Over Time**
- Hourly-bucketed stacked bar chart of stop reason distribution.
- Each bar segment represents a distinct `stop_reason` value.
- Note: this panel aggregates across all ecosystems for a combined overview.
  For per-ecosystem breakdown, use starter query 12 which includes
  `ecosystem_id` in its GROUP BY clause.

**Panel 9 — Action Mix Over Time**
- Hourly-bucketed stacked bar chart of `top_action` distribution from `agent.decision.taken` events.
- Visualizes how the action vocabulary shifts across runs.
- Note: this panel aggregates across all ecosystems for a combined overview.
  For per-ecosystem breakdown, use starter query 13 which includes
  `ecosystem_id` in its GROUP BY clause.

## 5. Optional: refresh data

After new runs or exports, either re-run the export command (overwriting `dashboard.db`) or point the datasource at the new file, then refresh the dashboard.
