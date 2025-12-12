# OPC-UA Data Pipeline

Industrial OPC-UA data pipeline simulating a Pick-and-Place SMT machine with real-time visualization in Grafana.

## Architecture
```
OPC-UA Server → MQTT → Redis/Kafka → TimescaleDB → Grafana
```

## Quick Start

### 1. Start all services
```bash
docker-compose up --build -d
```

### 2. Access the services
| Service | URL |
|---------|-----|
| **Grafana Dashboard** | http://localhost:3000 (admin/admin) |
| **Redpanda Console** | http://localhost:8080 |
| **OPC-UA Server** | opc.tcp://localhost:4840/pnp/ |

> **Note**: In Grafana, change the time range to **"Last 15 minutes"** (top right corner) to see the data.

### 3. Stop all services
```bash
docker-compose down -v
```

---

## Testing Guide

### Connect to OPC-UA Server (UAExpert)
1. Open UAExpert
2. Add server: `opc.tcp://localhost:4840/pnp/`
3. Connect (Anonymous authentication)
4. Navigate to: `Objects` → `PickAndPlace`

### Test Scenario 1: Simulate Error
1. In UAExpert, find `PickAndPlace` → `SimulateError`
2. Right-click → Call
3. Machine status changes to **Error**
4. Error message appears in Grafana dashboard

### Test Scenario 2: Acknowledge Error
1. In UAExpert, call `AcknowledgeAlarms` method
2. Machine automatically returns to **Running**
3. Error is cleared from dashboard

### Test Scenario 3: Empty Feeder
1. Wait for a feeder to reach 0 (or manually set `Feeder04Count` to 0)
2. Machine goes into **Error** state
3. In UAExpert, write a new value to the feeder (e.g., 5000)
4. Machine automatically resumes **Running**

### Test Scenario 4: Manual Value Changes
All variables under `PickAndPlace` are writable:
- `Feeder01Count` - `Feeder04Count`
- `ActualCycleTimeS`
- `VacuumPressureKPa`
- etc.

---

## Available OPC-UA Methods
| Method | Description |
|--------|-------------|
| `StartMachine()` | Start machine, clear all errors |
| `StopMachine()` | Stop machine |
| `SimulateError()` | Generate random error |
| `AcknowledgeAlarms()` | Clear errors, resume running |
| `EnterMaintenance()` | Enter maintenance mode |
| `EmergencyStop()` | Force error state |

---

## Project Structure
```
├── opcua_server/          # OPC-UA simulation server
├── opcua_mqtt_agent/      # OPC-UA → MQTT connector
├── hydration_agent/       # MQTT → Kafka with Redis enrichment
├── kafka_db_agent/        # Kafka → TimescaleDB writer
├── grafana/               # Dashboard configuration
├── database/              # TimescaleDB schema
└── docker-compose.yaml    # Complete infrastructure
```

## Documentation
See [DOCUMENTATION.md](DOCUMENTATION.md) for technical details.
