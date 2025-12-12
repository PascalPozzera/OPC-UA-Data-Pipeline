# Technical Documentation - OPC-UA Data Pipeline

## 1. System Architecture

### Data Flow
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   OPC-UA        │     │     MQTT        │     │     Redis       │
│   Server        │────▶│    Broker       │────▶│  (Enrichment)   │
│  (Simulation)   │     │  (Mosquitto)    │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Grafana      │◀────│  TimescaleDB    │◀────│     Kafka       │
│  (Dashboard)    │     │  (Time-Series)  │     │   (Redpanda)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Service Ports
| Service | Internal Port | External Port | Protocol |
|---------|---------------|---------------|----------|
| OPC-UA Server | 4840 | 4840 | opc.tcp |
| Grafana | 3000 | 3000 | HTTP |
| TimescaleDB | 5432 | 5432 | PostgreSQL |
| MQTT Broker | 1883 | 1883 | MQTT |
| Redis | 6379 | 6379 | Redis |
| Redpanda | 9092 | 9092 | Kafka |

---

## 2. OPC-UA Server

### Namespace
- URI: `urn:example:pick-and-place`
- Root Object: `PickAndPlace`

### Variables (All use static String NodeIDs)
| Variable | Type | Description |
|----------|------|-------------|
| `Status` | String | Running, Stopped, Error, Maintenance, Setup |
| `CurrentError` | String | Latched error text until acknowledged |
| `ActiveAlarms` | String | Current alarm message (stream) |
| `ProductionOrder` | String | Current order ID |
| `PCBsCompletedGood` | UInt32 | Completed good boards |
| `TotalPCBsOrder` | UInt32 | Total order quantity |
| `ProductionOrderProgressPct` | Double | Progress percentage |
| `Feeder01Count` - `Feeder04Count` | UInt32 | Component counts |
| `ActualPlacementRateCPH` | Double | Current placement rate |
| `VacuumPressureKPa` | Double | Vacuum pressure |
| `VisionPassRatePct` | Double | Vision system pass rate |

### Methods
| Method | Arguments | Description |
|--------|-----------|-------------|
| `StartMachine` | None | Set Running, clear errors |
| `StopMachine` | None | Set Stopped |
| `SimulateError` | None | Trigger random fault |
| `AcknowledgeAlarms` | None | Clear error, resume Running |
| `EnterMaintenance` | None | Set Maintenance mode |
| `EnterSetup` | None | Set Setup mode |
| `EmergencyStop` | None | Force Error state |

### Simulation Logic
- **Production**: 50% chance per second to increment `PCBsCompletedGood`
- **Feeders**: Randomly consume 1-5 components per cycle
- **Alarms**: 
  - Feeder Low Level (< 200 components) → Info message
  - Feeder Empty (= 0) → Error message
  - Various threshold violations → Error messages

---

## 3. Alarm System

### Latching Behavior
1. **Error Triggered** → Status = "Error", `CurrentError` = fault text
2. **Stays in Error** → Until explicit acknowledgment
3. **Acknowledge/Start** → Status = "Running", errors cleared

### Grafana Filtering Logic
```sql
-- Show ALL Info messages (always visible)
-- Show Errors ONLY if occurred AFTER last Running status
WHERE (value_str LIKE '%Info:%' 
   OR (value_str LIKE '%Error:%' AND time > last_running_time))
```

### Error Types (Random)
- Emergency Stop Button Pressed
- Feeder Jammed
- Nozzle Clogged
- Vision Camera Failure
- Safety Door Open

---

## 4. Database Schema

### Table: `opcua_data` (Hypertable)
```sql
CREATE TABLE opcua_data (
    time        TIMESTAMPTZ NOT NULL,
    metric      TEXT NOT NULL,
    value_num   DOUBLE PRECISION,
    value_str   TEXT,
    operator    TEXT
);
SELECT create_hypertable('opcua_data', 'time');
```

### Continuous Aggregate: `machine_stats_hourly`
```sql
CREATE MATERIALIZED VIEW machine_stats_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', time) AS bucket,
       metric,
       avg(value_num) AS avg_value,
       min(value_num) AS min_value,
       max(value_num) AS max_value,
       count(*) AS sample_count
FROM opcua_data
GROUP BY bucket, metric;

-- Refresh Policy: Every 30 minutes for last 3 days
SELECT add_continuous_aggregate_policy('machine_stats_hourly',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');
```

### Continuous Aggregate: `machine_stats_minute`
For real-time demos (faster feedback than hourly):
```sql
CREATE MATERIALIZED VIEW machine_stats_minute
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', time) AS bucket,
       metric,
       avg(value_num) AS avg_value,
       min(value_num) AS min_value,
       max(value_num) AS max_value,
       count(*) AS sample_count
FROM opcua_data
GROUP BY bucket, metric;

-- Refresh Policy: Every 30 seconds for last hour
SELECT add_continuous_aggregate_policy('machine_stats_minute',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '30 seconds');
```

### Example Grafana Queries

**Real-time raw data (last value):**
```sql
SELECT NOW() as time, value_num as value 
FROM opcua_data 
WHERE metric = 'ActualCycleTimeS' 
ORDER BY time DESC LIMIT 1
```

**Per-minute aggregated statistics:**
```sql
SELECT bucket as time, avg_value, min_value, max_value 
FROM machine_stats_minute 
WHERE metric = 'ActualCycleTimeS' 
  AND $__timeFilter(bucket) 
ORDER BY bucket
```

**Long-term hourly trends:**
```sql
SELECT bucket as time, avg_value, min_value, max_value 
FROM machine_stats_hourly 
WHERE metric = 'ActualPlacementRateCPH' 
  AND $__timeFilter(bucket) 
ORDER BY bucket
```

---

## 5. Agent Configuration

### opcua_mqtt_agent
- **Purpose**: Subscribe to OPC-UA changes, publish to MQTT
- **Reconnection**: Auto-reconnect on server restart (5s interval)
- **Topic**: `machine/data`

### hydration_agent
- **Purpose**: Enrich with Redis context (operator name)
- **Reconnection**: Auto-reconnect on Redis/Kafka failure
- **Output Topic**: `machine_events`

### kafka_db_agent
- **Purpose**: Consume Kafka, write to TimescaleDB
- **Reconnection**: Auto-reconnect on Kafka/DB failure
- **Batch Size**: 1 (immediate write)

---

## 6. Grafana Dashboard

### Panels
1. **Machine Status** - Color-coded status indicator
2. **Cycle Time** - Gauge with thresholds
3. **Order Progress** - Progress gauge
4. **Feeder Gauges** - 4x component level indicators
5. **Vision Pass Rate** - Quality indicator
6. **Accuracy Charts** - X/Y placement accuracy time series
7. **Recent Alarms** - Filtered alarm table

### Alarm Table Behavior
- **Info messages**: Always visible (blue background)
- **Error messages**: Hidden when Status = Running (red background)
- **Empty messages**: Filtered out

---

## 7. Troubleshooting

### Dashboard Not Updating
```bash
docker compose logs opcua-mqtt-agent --tail=20
# Look for "Published to MQTT" messages
```

### OPC-UA Connection Failed
```bash
docker compose logs opcua-server --tail=20
# Verify server is running on port 4840
```

### Database Empty
```bash
docker compose logs kafka-db-agent --tail=20
# Check for "Inserted row" messages
```

### Reset Everything
```bash
docker compose down -v
docker compose up --build -d
```
