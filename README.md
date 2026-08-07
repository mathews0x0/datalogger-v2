# Datalogger V2

A lightweight GPS datalogger system with ESP32 firmware and a web-based companion app.

## Project Structure

```
dataloggerV2/
├── firmware/          # Native ESP-IDF firmware (multi-target)
│   ├── main/          # Application entry point
│   ├── components/    # BSP, sensors, storage, networking, and UI
│   ├── tests/         # Host-side firmware contract tests
│   └── display_test_harness/
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

### 2. Build Firmware
```bash
cd firmware
idf.py build
```

The primary production target is the Waveshare ESP32-P4 4.3-inch board. The
same native project also contains the target abstraction used by the compact
2.8-inch custom boards; select the ESP-IDF target with `idf.py set-target`.

## Cloud IoT API (Direct-to-Cloud)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/device/ping` | POST | Heartbeat endpoint (15s interval). Validates device activity. |
| `/api/upload` | POST | Streamed CSV upload for logging data. |
| `/api/devices` | GET | (Frontend) Pulls latest device heartbeats to show "Connected" status. |
