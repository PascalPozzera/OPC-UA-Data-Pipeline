# Technical Documentation
## OPC-UA Industrial Data Pipeline

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [OPC-UA Server](#3-opc-ua-server)
4. [Pipeline Agents](#4-pipeline-agents)
5. [Database Schema](#5-database-schema)
6. [Alarm System](#6-alarm-system)
7. [Grafana Dashboard](#7-grafana-dashboard)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. System Overview

This project implements a complete industrial data pipeline that simulates a **Pick-and-Place SMT (Surface Mount Technology) machine**. The system demonstrates real-world concepts including:

- **OPC-UA Protocol**: Industry-standard communication for machine data
- **Message Streaming**: MQTT and Kafka for reliable data transport
- **Time-Series Database**: TimescaleDB with continuous aggregates for efficient storage
- **Real-Time Visualization**: Grafana dashboards with live updates
- **Context Enrichment**: Redis for adding metadata to events

### Key Features
- ✅ Fully containerized with Docker Compose
- ✅ Auto-reconnection on service failures
- ✅ Realistic machine simulation with alarms
- ✅ All OPC-UA variables writable via UAExpert
- ✅ Automatic recovery when feeders are refilled

---

## 2. Architecture

### Data Flow Diagram
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
    │   OPC-UA     │  OPC-UA  │  OPC-MQTT    │   MQTT   │    MQTT      │
    │   Server     │─────────▶│   Agent      │─────────▶│   Broker     │
    │ (Simulation) │          │              │          │ (Mosquitto)  │
    └──────────────┘          └──────────────┘          └──────┬───────┘
                                                               │
                                                               ▼
    ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
    │   Grafana    │◀─────────│ TimescaleDB  │◀─────────│  Hydration   │
    │  Dashboard   │   SQL    │              │  Kafka   │    Agent     │
    │              │          │              │          │              │
    └──────────────┘          └──────┬───────┘          └──────┬───────┘
                                     │                         │
                              ┌──────┴───────┐          ┌──────┴───────┐
                              │  Kafka-DB    │          │    Redis     │
                              │   Agent      │          │  (Context)   │
                              └──────────────┘          └──────────────┘
```

### Service Overview

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| **OPC-UA Server** | 4840 | opc.tcp | Simulates Pick-and-Place machine |
| **MQTT Broker** | 1883 | MQTT | Message queue for machine events |
| **Redis** | 6379 | Redis | Context storage (operator info) |
| **Redpanda** | 9092 | Kafka | Distributed streaming platform |
| **Redpanda Console** | 8080 | HTTP | Kafka monitoring UI |
| **TimescaleDB** | 5432 | PostgreSQL | Time-series database |
| **Grafana** | 3000 | HTTP | Visualization dashboard |

---

## 3. OPC-UA Server

### Server Configuration
| Property | Value |
|----------|-------|
| Endpoint | `opc.tcp://0.0.0.0:4840/pnp/` |
| Namespace URI | `urn:example:pick-and-place` |
| Security | NoSecurity (Anonymous) |
| Root Object | `PickAndPlace` |

### Available Variables

All variables are **writable** and can be modified via UAExpert.

#### Machine Identity
| Variable | Type | Example Value |
|----------|------|---------------|
| `MachineName` | String | "ChipPlace Lightning #4" |
| `MachineSerialNumber` | String | "CPL4000-2023-004" |
| `Plant` | String | "Dresden Electronics Manufacturing" |
| `ProductionLine` | String | "SMT Assembly Line 5" |

#### Production Data
| Variable | Type | Description |
|----------|------|-------------|
| `Status` | String | Current state (Running, Error, Stopped, etc.) |
| `CurrentOperation` | String | Current activity |
| `ProductionOrder` | String | Current order ID |
| `PCBsCompletedGood` | UInt32 | Completed good boards |
| `TotalPCBsOrder` | UInt32 | Total boards in order |
| `ProductionOrderProgressPct` | Double | Order completion percentage |

#### Process Parameters
| Variable | Type | Description |
|----------|------|-------------|
| `TargetPlacementRateCPH` | Double | Target components per hour |
| `ActualPlacementRateCPH` | Double | Actual placement rate |
| `TargetCycleTimeS` | Double | Target cycle time (seconds) |
| `ActualCycleTimeS` | Double | Actual cycle time |
| `VacuumPressureKPa` | Double | Vacuum pressure |
| `VisionPassRatePct` | Double | Vision system pass rate |

#### Feeders
| Variable | Type | Description |
|----------|------|-------------|
| `Feeder01Count` | UInt32 | Components remaining in Feeder 1 |
| `Feeder02Count` | UInt32 | Components remaining in Feeder 2 |
| `Feeder03Count` | UInt32 | Components remaining in Feeder 3 |
| `Feeder04Count` | UInt32 | Components remaining in Feeder 4 |

#### Alarms
| Variable | Type | Description |
|----------|------|-------------|
| `ActiveAlarms` | String | Current alarm message |
| `CurrentError` | String | Latched error (persists until acknowledged) |

### Available Methods

| Method | Description |
|--------|-------------|
| `StartMachine()` | Start machine, clear all errors |
| `StopMachine()` | Stop machine (controlled shutdown) |
| `SimulateError()` | Generate a random fault |
| `AcknowledgeAlarms()` | Clear errors, resume running |
| `EnterMaintenance()` | Enter maintenance mode |
| `EnterSetup()` | Enter setup mode |
| `EmergencyStop()` | Force immediate error state |

---

## 4. Pipeline Agents

### OPC-UA → MQTT Agent
**Purpose**: Subscribes to all OPC-UA variable changes and publishes to MQTT.

| Property | Value |
|----------|-------|
| Input | OPC-UA Subscription (500ms interval) |
| Output | MQTT Topic `machine/data` |
| Reconnection | Auto-reconnect every 5 seconds |

**Message Format**:
```json
{
  "node_id": "ActualCycleTimeS",
  "value": 0.73,
  "timestamp": "2024-12-12T06:30:00.123Z"
}
```

### Hydration Agent
**Purpose**: Enriches messages with context data from Redis and forwards to Kafka.

| Property | Value |
|----------|-------|
| Input | MQTT Topic `machine/data` |
| Output | Kafka Topic `machine_events` |
| Enrichment Source | Redis |

**Redis Context Keys**:
- `context:operator` → Current operator name
- `context:last_maintenance` → Last maintenance date

**Enriched Message Format**:
```json
{
  "original_data": {
    "node_id": "ActualCycleTimeS",
    "value": 0.73,
    "timestamp": "2024-12-12T06:30:00.123Z"
  },
  "context": {
    "operator": "John Doe",
    "last_maintenance": "2025-10-01",
    "enriched_at": 1702368600.123
  }
}
```

### Kafka → DB Agent
**Purpose**: Consumes enriched messages from Kafka and writes to TimescaleDB.

| Property | Value |
|----------|-------|
| Input | Kafka Topic `machine_events` |
| Output | TimescaleDB table `opcua_data` |
| Consumer Group | `db-writer-group` |

---

## 5. Database Schema

### Main Table: `opcua_data`
```sql
CREATE TABLE opcua_data (
    time        TIMESTAMPTZ NOT NULL,
    metric      TEXT NOT NULL,
    value_num   DOUBLE PRECISION,  -- For numeric values
    value_str   TEXT,              -- For string values
    operator    TEXT               -- Enriched from Redis
);

-- Convert to TimescaleDB hypertable for efficient time-series storage
SELECT create_hypertable('opcua_data', 'time', if_not_exists => TRUE);

-- Index for fast metric lookups
CREATE INDEX IF NOT EXISTS idx_opcua_metric ON opcua_data(metric, time DESC);
```

### Continuous Aggregate: Per-Minute Statistics
Pre-computed statistics refreshed every 30 seconds for demo purposes.

```sql
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

-- Refresh every 30 seconds, covering the last hour
SELECT add_continuous_aggregate_policy('machine_stats_minute',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '30 seconds');
```

### Continuous Aggregate: Hourly Statistics
Long-term historical analysis with 30-minute refresh.

```sql
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

-- Refresh every 30 minutes, covering the last 3 days
SELECT add_continuous_aggregate_policy('machine_stats_hourly',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes');
```

---

## 6. Alarm System

### Deviation Tracker (DeviationTracker Class)
Implements alarm logic based on assignment requirements:

| Condition | Alarm Type | Description |
|-----------|------------|-------------|
| **>10% deviation** | Immediate | Single cycle with >10% deviation triggers alarm |
| **>2% for 3 cycles** | Trend | Three consecutive cycles with >2% deviation |

### Feeder Monitoring
| Threshold | Behavior |
|-----------|----------|
| **< 200 components** | Info message: "Feeder Low Level - Please Refill!" |
| **= 0 components** | Error: Machine stops, "Feeder empty" alarm |

### Auto-Recovery
When all feeders are refilled (count > 0) and no pending critical alarms exist, the machine automatically returns to **Running** status.

### Error Types (SimulateError Method)
- Emergency Stop Button Pressed
- Feeder Jammed
- Nozzle Clogged
- Vision Camera Failure
- Safety Door Open

---

## 7. Grafana Dashboard

### Dashboard Sections

#### 1. Machine Overview
- **Status Indicator**: Color-coded current status
- **Current Error**: Displays latched error message
- **Order Progress**: Percentage completion gauge

#### 2. Real-Time Metrics
- **Cycle Time**: Actual vs. target gauge
- **Placement Rate**: Components per hour
- **Vision Pass Rate**: Quality indicator

#### 3. Feeder Status
- **4 Feeder Gauges**: Visual component levels
- Color thresholds: Green (>500), Yellow (200-500), Red (<200)

#### 4. Per-Minute Statistics
Using `machine_stats_minute` continuous aggregate:
- Cycle Time trends (avg/min/max)
- Data points per minute

#### 5. Hourly Trends
Using `machine_stats_hourly` for long-term analysis:
- Placement rate hourly trends

#### 6. Alarm Table
- Shows recent alarm messages
- Info messages always visible
- Error messages filtered based on status

### Example Grafana Queries

**Latest value (real-time)**:
```sql
SELECT NOW() as time, value_num as value 
FROM opcua_data 
WHERE metric = 'ActualCycleTimeS' 
ORDER BY time DESC LIMIT 1
```

**Per-minute aggregates**:
```sql
SELECT bucket as time, avg_value, min_value, max_value 
FROM machine_stats_minute 
WHERE metric = 'ActualCycleTimeS' 
  AND $__timeFilter(bucket) 
ORDER BY bucket
```

**Hourly trends**:
```sql
SELECT bucket as time, avg_value, min_value, max_value 
FROM machine_stats_hourly 
WHERE metric = 'ActualPlacementRateCPH' 
  AND $__timeFilter(bucket) 
ORDER BY bucket
```

---

## 8. Troubleshooting

### Common Issues

#### No Data in Dashboard
```bash
# Check if all agents are running
docker-compose ps

# View agent logs
docker-compose logs -f opcua-mqtt-agent
docker-compose logs -f hydration-agent
docker-compose logs -f kafka-db-agent
```

#### OPC-UA Connection Failed
```bash
# Check if server is running
docker-compose logs opcua-server

# Verify port is accessible
netstat -an | findstr 4840
```

#### Database Issues
```bash
# Connect to database
docker exec -it timescaledb psql -U postgres -d industrial_data

# Check data count
SELECT COUNT(*) FROM opcua_data;

# Check continuous aggregates
SELECT * FROM machine_stats_minute ORDER BY bucket DESC LIMIT 5;
```

### Complete Reset
```bash
# Stop all services and remove volumes
docker-compose down -v

# Rebuild and restart
docker-compose up --build -d
```

---

## Appendix: Environment Variables

### OPC-UA → MQTT Agent
| Variable | Default | Description |
|----------|---------|-------------|
| `OPCUA_ENDPOINT` | `opc.tcp://opcua-server:4840/pnp/` | OPC-UA server URL |
| `MQTT_BROKER` | `mqtt-broker` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |

### Hydration Agent
| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | `mqtt-broker` | MQTT broker hostname |
| `REDIS_HOST` | `redis` | Redis hostname |
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker URL |

### Kafka-DB Agent
| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `redpanda:9092` | Kafka broker URL |
| `DB_HOST` | `timescaledb` | Database hostname |
| `DB_NAME` | `industrial_data` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | `postgres` | Database password |
