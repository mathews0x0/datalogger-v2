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

## ESP32 Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Device status, storage, active track |
| `/list` | GET | List logged sessions |
| `/download/<file>` | GET | Download session CSV |
| `/track/set` | POST | Push track metadata |
| `/track/status` | GET | Current track state |
