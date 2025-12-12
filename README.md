# OPC-UA Data Pipeline

## Overview
Industrial OPC-UA data pipeline simulation running entirely in Docker. Simulates a "PickAndPlace" SMT machine with real-time data flow to Grafana dashboards.

## Architecture
```
OPC-UA Server → MQTT Broker → Redis/Kafka → TimescaleDB → Grafana
     ↓              ↓              ↓              ↓           ↓
  Simulation    Message Bus    Enrichment    Storage    Visualization
```

## Services
| Service | Port | Description |
|---------|------|-------------|
| OPC-UA Server | 4840 | Machine simulation |
| Grafana | 3000 | Dashboard (admin/admin) |
| Redpanda Console | 8080 | Kafka monitoring UI |
| TimescaleDB | 5432 | Time-series database |
| MQTT Broker | 1883 | Message broker |
| Redis | 6379 | Context store |
| Redpanda | 9092 | Kafka-compatible streaming |


## Quick Start
```bash
# Start all services
docker compose up --build -d

# View logs
docker compose logs -f

# Stop and clean
docker compose down -v
```

## OPC-UA Control Methods (via UAExpert)
| Method | Description |
|--------|-------------|
| `StartMachine()` | Set status to Running, clear errors |
| `StopMachine()` | Set status to Stopped |
| `SimulateError()` | Trigger random fault |
| `AcknowledgeAlarms()` | Clear error, resume Running |
| `EnterMaintenance()` | Set maintenance mode |
| `EmergencyStop()` | Force error state |

## Features
- **Latching Errors**: Errors persist until acknowledged
- **Auto-Reconnect**: Agents reconnect after server restart
- **Smart Alarm Filtering**: Errors hidden on Running, Info always visible
- **Real-time Dashboard**: Live machine metrics in Grafana

## Project Structure
```
├── opcua_server/        # OPC-UA simulation server
├── opcua_mqtt_agent/    # OPC-UA → MQTT connector
├── hydration_agent/     # MQTT → Kafka with Redis enrichment
├── kafka_db_agent/      # Kafka → TimescaleDB writer
├── grafana/             # Dashboard provisioning
├── database/            # TimescaleDB init scripts
└── mosquitto/           # MQTT broker config
```

## Dashboard Access
Open [http://localhost:3000](http://localhost:3000) (Login: admin/admin)

## Documentation
See [DOCUMENTATION.md](DOCUMENTATION.md) for detailed technical documentation.
