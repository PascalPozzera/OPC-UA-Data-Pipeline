# OPC-UA Data Pipeline

## Projektübersicht
Industrielle OPC-UA Datenpipeline, die eine Pick-and-Place SMT-Maschine simuliert. Daten fließen in Echtzeit durch mehrere Agenten bis zur Visualisierung in Grafana.

## Architektur
```
OPC-UA Server → MQTT Broker → Hydration Agent → Kafka → TimescaleDB → Grafana
     ↓              ↓              ↓               ↓          ↓           ↓
  Simulation    Message Bus    Redis Enrichment  Streaming  Storage   Dashboard
```

## Services
| Service | Port | Beschreibung |
|---------|------|--------------|
| OPC-UA Server | 4840 | Maschinen-Simulation |
| Grafana | 3000 | Dashboard (Login: admin/admin) |
| Redpanda Console | 8080 | Kafka Monitoring UI |
| TimescaleDB | 5432 | Zeit-Serien Datenbank |
| MQTT Broker | 1883 | Message Broker |
| Redis | 6379 | Kontext-Speicher |
| Redpanda | 9092 | Kafka-kompatibler Stream |

---

## Quick Start

### 1. Alle Services starten
```bash
docker-compose up --build -d
```

### 2. Warten bis alles läuft (~30 Sekunden)
```bash
docker-compose ps
```

### 3. Zugriff auf die Services
- **Grafana Dashboard**: http://localhost:3000 (Login: admin / admin)
- **Redpanda Console**: http://localhost:8080
- **OPC-UA Server**: opc.tcp://localhost:4840/pnp/ (via UAExpert)

### 4. Services stoppen
```bash
docker-compose down -v
```

---

## Anleitung für den Dozenten

### OPC-UA Server mit UAExpert verbinden
1. UAExpert öffnen
2. Server hinzufügen: `opc.tcp://localhost:4840/pnp/`
3. Verbinden (Anonymous)
4. Im "Address Space" → `Objects` → `PickAndPlace` finden

### Variablen in UAExpert
Alle Variablen unter `PickAndPlace` sind **beschreibbar** und können direkt in UAExpert geändert werden:
- `Feeder01Count` - `Feeder04Count`: Feeder-Zählerstände
- `ActualCycleTimeS`, `VacuumPressureKPa`: Prozesswerte
- `Status`: Maschinenstatus

---

## Feeder-Logik (Demo-Szenario)

### Feeder wird leer
1. Die Simulation verbraucht automatisch Komponenten aus den Feedern
2. Bei **< 200 Stück**: Info-Meldung "Feeder Low Level - Please Refill!"
3. Bei **0 Stück**: Kritischer Alarm → Maschine geht in **Error**-Status

### Feeder manuell befüllen
1. In UAExpert den leeren Feeder finden (z.B. `Feeder04Count`)
2. Rechtsklick → Write → Neuen Wert eingeben (z.B. `5000`)
3. **Automatische Wiederherstellung**: Wenn alle Feeder > 0 sind, wechselt die Maschine automatisch zurück auf **Running**

---

## Fehler simulieren und quittieren

### Fehler simulieren
**Methode 1 - Über OPC-UA Methode:**
1. In UAExpert unter `PickAndPlace` → `SimulateError` finden
2. Rechtsklick → "Call" → Ausführen
3. Ein zufälliger Fehler wird generiert (z.B. "Feeder Jammed", "Nozzle Clogged")

**Methode 2 - EmergencyStop:**
1. `EmergencyStop` Methode aufrufen
2. Maschine geht sofort in Error-Status

### Fehler quittieren
1. In UAExpert die Methode `AcknowledgeAlarms` aufrufen
2. Alle aktiven Alarme werden gelöscht
3. Maschine startet automatisch wieder (Status: Running)

**Alternativ:** `StartMachine` Methode aufrufen - löscht ebenfalls alle Fehler.

---

## Verfügbare OPC-UA Methoden
| Methode | Beschreibung |
|---------|--------------|
| `StartMachine()` | Startet die Maschine, löscht alle Fehler |
| `StopMachine()` | Stoppt die Maschine kontrolliert |
| `SimulateError()` | Generiert einen zufälligen Fehler |
| `AcknowledgeAlarms()` | Quittiert alle Alarme, startet Maschine |
| `EnterMaintenance()` | Wechselt in Wartungsmodus |
| `EnterSetup()` | Wechselt in Setup-Modus |
| `EmergencyStop()` | Not-Aus, sofortiger Error-Status |

---

## Grafana Dashboard Features

### Echtzeit-Panels
- **Machine Status**: Aktueller Zustand (Running, Error, etc.)
- **Cycle Time & Placement Rate**: Prozess-Performance
- **Feeder Counts**: Live-Zählerstände aller 4 Feeder
- **Order Progress**: Fortschritt der aktuellen PCB-Produktion

### Aggregierte Statistiken
- **Per-Minute Statistics**: Benutzt `machine_stats_minute` Continuous Aggregate
- **Hourly Trends**: Benutzt `machine_stats_hourly` für Langzeit-Analyse

### Alarm-Anzeige
- **Recent Alarms**: Zeigt die letzten Alarm-Meldungen
- Fehler-Alarme werden rot angezeigt
- Info-Meldungen (z.B. Feeder Low) bleiben auch bei Running sichtbar

---

## Projektstruktur
```
├── opcua_server/          # OPC-UA Simulations-Server
│   ├── main.py            # Server-Logik mit DeviationTracker
│   ├── Dockerfile
│   └── requirements.txt
├── opcua_mqtt_agent/      # OPC-UA → MQTT Connector
├── hydration_agent/       # MQTT → Kafka mit Redis-Anreicherung
├── kafka_db_agent/        # Kafka → TimescaleDB Writer
├── grafana/
│   ├── dashboards/        # Dashboard JSON
│   └── provisioning/      # Auto-Konfiguration
├── database/
│   └── init.sql           # TimescaleDB Schema + Continuous Aggregates
├── mosquitto/             # MQTT Broker Konfiguration
├── docker-compose.yaml    # Gesamte Infrastruktur
├── README.md              # Diese Datei
└── DOCUMENTATION.md       # Technische Dokumentation
```

---

## Technische Highlights

### Alarm-System (laut PDF-Anforderungen)
- **>10% Abweichung**: Sofortiger Alarm
- **>2% Abweichung über 3 Zyklen**: Trend-Alarm
- Implementiert in `DeviationTracker` Klasse

### Continuous Aggregates (TimescaleDB)
- `machine_stats_minute`: 1-Minuten Buckets, refresht alle 30 Sekunden
- `machine_stats_hourly`: 1-Stunden Buckets, refresht alle 30 Minuten

### Auto-Recovery
- Wenn alle Feeder wieder befüllt sind (>0), startet die Maschine automatisch

---

## Troubleshooting

### Container starten nicht
```bash
docker-compose down -v
docker-compose up --build -d
```

### Keine Daten im Dashboard
- Warten Sie 1-2 Minuten nach dem Start
- Prüfen Sie die Logs: `docker-compose logs -f`

### UAExpert kann nicht verbinden
- Prüfen Sie ob der Container läuft: `docker-compose ps`
- Firewall-Regeln für Port 4840 prüfen

---

## Dokumentation
Siehe [DOCUMENTATION.md](DOCUMENTATION.md) für detaillierte technische Dokumentation.
