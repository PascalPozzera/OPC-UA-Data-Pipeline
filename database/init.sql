-- Create the main table
CREATE TABLE IF NOT EXISTS opcua_data (
    time TIMESTAMPTZ NOT NULL,
    metric TEXT NOT NULL,
    value_num DOUBLE PRECISION,
    value_str TEXT,
    operator TEXT
);

-- Convert to Hypertable
SELECT create_hypertable('opcua_data', 'time', if_not_exists => TRUE);

-- Add index on metric for fast filtering
CREATE INDEX IF NOT EXISTS idx_opcua_data_metric ON opcua_data (metric, time DESC);

-- Continuous Aggregate: Hourly Statistics
-- Calculates Avg, Min, Max for numeric values per metric per hour
CREATE MATERIALIZED VIEW machine_stats_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    metric,
    avg(value_num) AS avg_value,
    min(value_num) AS min_value,
    max(value_num) AS max_value,
    count(value_num) AS sample_count
FROM opcua_data
WHERE value_num IS NOT NULL
GROUP BY bucket, metric;

SELECT add_continuous_aggregate_policy('machine_stats_hourly',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');

-- Continuous Aggregate: Per-Minute Statistics (for demos/real-time monitoring)
CREATE MATERIALIZED VIEW machine_stats_minute
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    metric,
    avg(value_num) AS avg_value,
    min(value_num) AS min_value,
    max(value_num) AS max_value,
    count(value_num) AS sample_count
FROM opcua_data
WHERE value_num IS NOT NULL
GROUP BY bucket, metric;

-- Refresh policy for minute stats (refresh every 30 seconds for the last hour)
SELECT add_continuous_aggregate_policy('machine_stats_minute',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '30 seconds');
