# Datalogger V2

A lightweight GPS datalogger system with ESP32 firmware and a web-based companion app.

## Project Structure

```
dataloggerV2/
├── firmware/          # ESP32 MicroPython firmware
│   ├── main.py        # Main entry point
│   ├── lib/           # Modules (GPS, WiFi, LED, Session, Track)
│   └── deploy.sh      # Deployment script
├── server/            # Backend + UI
│   ├── api/           # Flask REST API
│   ├── core/          # Analysis engine
│   ├── ui/            # Web companion app
│   └── run.py         # Server launcher
├── data/              # Data storage
│   ├── learning/      # Raw GPS logs
│   ├── sessions/      # Processed sessions
│   ├── tracks/        # Track definitions
│   └── metadata/      # Registry, track metadata
└── scripts/           # Maintenance scripts
```

## Quick Start

### 1. Start Server
```bash
cd server
python run.py
```
Server runs at http://localhost:5000

### 2. Deploy Firmware
```bash
cd firmware
./deploy.sh --sync
```

## Cloud IoT API (Direct-to-Cloud)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/device/ping` | POST | Heartbeat endpoint (15s interval). Validates device activity. |
| `/api/upload` | POST | Streamed CSV upload for logging data. |
| `/api/devices` | GET | (Frontend) Pulls latest device heartbeats to show "Connected" status. |

