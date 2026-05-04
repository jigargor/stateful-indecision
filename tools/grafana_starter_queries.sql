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
