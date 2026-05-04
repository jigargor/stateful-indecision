# Grafana dashboard (SQLite)

Quick path from repo data to `tools/grafana_dashboard_template.json`.

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

## 4.1 Suggested panels from `grafana_starter_queries.sql`

- **Latency distribution (p50/p95):**
  - Use query **8** as the panel source.
  - In Grafana transformations/statistics, compute p50 and p95 over `latency_ms`.
- **Tokens per decision:**
  - Use query **8**, chart `tokens_total` over time or by agent.
- **Stop reason mix:**
  - Use query **9** for grouped bars or pie chart by `stop_reason`.

## 5. Optional: refresh data

After new runs or exports, either re-run the export command (overwriting `dashboard.db`) or point the datasource at the new file, then refresh the dashboard.
