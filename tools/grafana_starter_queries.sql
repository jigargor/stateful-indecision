-- Grafana starter query pack for dashboard.db
-- Schema expected from: python -m tools.export_to_sqlite --db dashboard.db --base-dir .
--
-- Tables:
--   events(event_id, event_type, ecosystem_id, agent_id, wall_time, payload_json, ...)
--   runs(event_id, ecosystem_id, agent_id, decisions_completed, run_seed, field_chosen, run_config_version, wall_time, ...)
--   artifacts(artifact_id, agent_id, ecosystem_id, action, config_version, created_at, ...)


-- 1) Event throughput over time by ecosystem
SELECT
  strftime('%Y-%m-%d %H:00:00', wall_time) AS hour_bucket,
  ecosystem_id,
  COUNT(*) AS event_count
FROM events
GROUP BY hour_bucket, ecosystem_id
ORDER BY hour_bucket, ecosystem_id;


-- 2) Top-level action distribution (decision.taken payload) by ecosystem
SELECT
  ecosystem_id,
  json_extract(payload_json, '$.top_action') AS top_action,
  COUNT(*) AS decisions
FROM events
WHERE event_type = 'agent.decision.taken'
GROUP BY ecosystem_id, top_action
ORDER BY ecosystem_id, decisions DESC;


-- 3) Per-agent action profile (top action) for alpha vs beta
SELECT
  ecosystem_id,
  agent_id,
  json_extract(payload_json, '$.top_action') AS top_action,
  COUNT(*) AS decisions
FROM events
WHERE event_type = 'agent.decision.taken'
  AND ecosystem_id IN ('alpha', 'beta')
GROUP BY ecosystem_id, agent_id, top_action
ORDER BY ecosystem_id, agent_id, decisions DESC;


-- 4) Collaboration signal: commons + roundtable + townhall events by ecosystem
SELECT
  ecosystem_id,
  SUM(CASE WHEN event_type = 'commons.utterance' THEN 1 ELSE 0 END) AS commons_utterances,
  SUM(CASE WHEN event_type = 'roundtable.utterance' THEN 1 ELSE 0 END) AS roundtable_utterances,
  SUM(CASE WHEN event_type = 'townhall.broadcast' THEN 1 ELSE 0 END) AS townhall_broadcasts
FROM events
GROUP BY ecosystem_id
ORDER BY ecosystem_id;


-- 5) Notebook duplicate ratio by agent (from events table)
-- Uses exact text equality from payload_json.text.
SELECT
  ecosystem_id,
  agent_id,
  COUNT(*) AS notebook_entries,
  COUNT(DISTINCT json_extract(payload_json, '$.text')) AS unique_entries,
  COUNT(*) - COUNT(DISTINCT json_extract(payload_json, '$.text')) AS duplicate_entries,
  ROUND(
    100.0 * (COUNT(*) - COUNT(DISTINCT json_extract(payload_json, '$.text')))
    / NULLIF(COUNT(*), 0),
    2
  ) AS duplicate_pct
FROM events
WHERE event_type = 'agent.notebook.appended'
GROUP BY ecosystem_id, agent_id
ORDER BY ecosystem_id, duplicate_pct DESC, notebook_entries DESC;


-- 6) Run progression by agent
SELECT
  ecosystem_id,
  agent_id,
  COUNT(*) AS run_count,
  MAX(wall_time) AS last_run_time,
  MAX(run_config_version) AS max_config_version_seen,
  SUM(decisions_completed) AS total_decisions_recorded
FROM runs
GROUP BY ecosystem_id, agent_id
ORDER BY ecosystem_id, agent_id;


-- 7) Alpha vs beta headline comparison (single row per ecosystem)
WITH decision_counts AS (
  SELECT ecosystem_id, COUNT(*) AS decisions
  FROM events
  WHERE event_type = 'agent.decision.taken'
  GROUP BY ecosystem_id
),
social_counts AS (
  SELECT
    ecosystem_id,
    SUM(CASE WHEN event_type = 'commons.utterance' THEN 1 ELSE 0 END) AS commons_utterances,
    SUM(CASE WHEN event_type = 'roundtable.utterance' THEN 1 ELSE 0 END) AS roundtable_utterances
  FROM events
  GROUP BY ecosystem_id
),
skill_counts AS (
  SELECT ecosystem_id, COUNT(*) AS skill_authored
  FROM events
  WHERE event_type = 'agent.skill.authored'
  GROUP BY ecosystem_id
),
notebook_stats AS (
  SELECT
    ecosystem_id,
    COUNT(*) AS notebook_entries,
    COUNT(DISTINCT ecosystem_id || '|' || agent_id || '|' || json_extract(payload_json, '$.text')) AS unique_notebook_entries
  FROM events
  WHERE event_type = 'agent.notebook.appended'
  GROUP BY ecosystem_id
)
SELECT
  d.ecosystem_id,
  d.decisions,
  s.commons_utterances,
  s.roundtable_utterances,
  COALESCE(sk.skill_authored, 0) AS skill_authored,
  n.notebook_entries,
  (n.notebook_entries - n.unique_notebook_entries) AS notebook_duplicates
FROM decision_counts d
LEFT JOIN social_counts s ON s.ecosystem_id = d.ecosystem_id
LEFT JOIN skill_counts sk ON sk.ecosystem_id = d.ecosystem_id
LEFT JOIN notebook_stats n ON n.ecosystem_id = d.ecosystem_id
WHERE d.ecosystem_id IN ('alpha', 'beta')
ORDER BY d.ecosystem_id;


-- 8) Decision latency and token metrics (for p50/p95 panels)
-- Note: percentile functions are not native in SQLite; use this base query and
-- compute p50/p95 in Grafana transformations.
SELECT
  ecosystem_id,
  agent_id,
  wall_time,
  CAST(json_extract(payload_json, '$.metrics.wall_end_ms') AS REAL)
    - CAST(json_extract(payload_json, '$.metrics.wall_start_ms') AS REAL) AS latency_ms,
  CAST(json_extract(payload_json, '$.metrics.tokens_in') AS INTEGER) AS tokens_in,
  CAST(json_extract(payload_json, '$.metrics.tokens_out') AS INTEGER) AS tokens_out,
  CAST(json_extract(payload_json, '$.metrics.tokens_in') AS INTEGER)
    + CAST(json_extract(payload_json, '$.metrics.tokens_out') AS INTEGER) AS tokens_total
FROM events
WHERE event_type = 'action.executed'
ORDER BY wall_time;


-- 9) Stop reason distribution by ecosystem and agent
SELECT
  ecosystem_id,
  agent_id,
  json_extract(payload_json, '$.metrics.stop_reason') AS stop_reason,
  COUNT(*) AS event_count
FROM events
WHERE event_type = 'action.executed'
GROUP BY ecosystem_id, agent_id, stop_reason
ORDER BY ecosystem_id, agent_id, event_count DESC;


-- 10) p50 and p95 decision latency per ecosystem and agent
-- SQLite lacks native percentile functions. This approximates percentiles
-- via LIMIT+OFFSET on the ordered latency set per group.
-- The CAST(cnt * percentile AS INTEGER) + 1 formula is a nearest-rank
-- approximation with slight upper bias — standard for observability dashboards.
-- For Grafana, prefer query 8 with a "Percentile" transformation.
WITH latencies AS (
  SELECT
    ecosystem_id,
    agent_id,
    CAST(json_extract(payload_json, '$.metrics.wall_end_ms') AS REAL)
      - CAST(json_extract(payload_json, '$.metrics.wall_start_ms') AS REAL) AS latency_ms,
    ROW_NUMBER() OVER (PARTITION BY ecosystem_id, agent_id ORDER BY
      CAST(json_extract(payload_json, '$.metrics.wall_end_ms') AS REAL)
      - CAST(json_extract(payload_json, '$.metrics.wall_start_ms') AS REAL)
    ) AS rn,
    COUNT(*) OVER (PARTITION BY ecosystem_id, agent_id) AS cnt
  FROM events
  WHERE event_type = 'action.executed'
    AND json_extract(payload_json, '$.metrics.wall_end_ms') IS NOT NULL
    AND json_extract(payload_json, '$.metrics.wall_start_ms') IS NOT NULL
)
SELECT
  ecosystem_id,
  agent_id,
  cnt AS sample_count,
  MIN(latency_ms) AS min_latency_ms,
  MAX(CASE WHEN rn = CAST(cnt * 0.5 AS INTEGER) + 1 THEN latency_ms END) AS p50_latency_ms,
  MAX(CASE WHEN rn = CAST(cnt * 0.95 AS INTEGER) + 1 THEN latency_ms END) AS p95_latency_ms,
  MAX(latency_ms) AS max_latency_ms
FROM latencies
GROUP BY ecosystem_id, agent_id
ORDER BY ecosystem_id, agent_id;


-- 11) Tokens per decision aggregation by ecosystem and agent
SELECT
  ecosystem_id,
  agent_id,
  COUNT(*) AS executions,
  SUM(CAST(json_extract(payload_json, '$.metrics.tokens_in') AS INTEGER)) AS total_tokens_in,
  SUM(CAST(json_extract(payload_json, '$.metrics.tokens_out') AS INTEGER)) AS total_tokens_out,
  SUM(CAST(json_extract(payload_json, '$.metrics.tokens_in') AS INTEGER))
    + SUM(CAST(json_extract(payload_json, '$.metrics.tokens_out') AS INTEGER)) AS total_tokens,
  ROUND(
    AVG(CAST(json_extract(payload_json, '$.metrics.tokens_in') AS REAL)
      + CAST(json_extract(payload_json, '$.metrics.tokens_out') AS REAL)),
    1
  ) AS avg_tokens_per_decision
FROM events
WHERE event_type = 'action.executed'
GROUP BY ecosystem_id, agent_id
ORDER BY ecosystem_id, agent_id;


-- 12) Stop reason distribution over time (hourly buckets)
SELECT
  strftime('%Y-%m-%d %H:00:00', wall_time) AS hour_bucket,
  ecosystem_id,
  json_extract(payload_json, '$.metrics.stop_reason') AS stop_reason,
  COUNT(*) AS event_count
FROM events
WHERE event_type = 'action.executed'
GROUP BY hour_bucket, ecosystem_id, stop_reason
ORDER BY hour_bucket, ecosystem_id, stop_reason;


-- 13) Action mix over time (hourly buckets, top_action distribution)
SELECT
  strftime('%Y-%m-%d %H:00:00', wall_time) AS hour_bucket,
  ecosystem_id,
  json_extract(payload_json, '$.top_action') AS top_action,
  COUNT(*) AS decisions
FROM events
WHERE event_type = 'agent.decision.taken'
GROUP BY hour_bucket, ecosystem_id, top_action
ORDER BY hour_bucket, ecosystem_id, decisions DESC;
