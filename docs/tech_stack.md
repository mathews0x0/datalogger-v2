# 🛠️ RaceSense Technical Documentation

This document provides a deep dive into the technology stack, deployment processes, and critical safety guidelines for the RaceSense (Datalogger V2) platform.

---

## 🏗️ Technology Stack

### **Backend (Python 3.9+)**
*   **Framework**: [Flask](https://flask.palletsprojects.com/) (Application Factory pattern).
*   **Database**: **PostgreSQL** in all environments, with [SQLAlchemy](https://www.sqlalchemy.org/) ORM.
*   **Migrations**: [Flask-Migrate](https://flask-migrate.readthedocs.io/) (Alembic).
*   **Authentication**: **Dual-Auth System**.
    *   **Users**: [Flask-JWT-Extended](https://flask-jwt-extended.readthedocs.io/) via Secure HttpOnly Cookies.
    *   **Devices**: Secure **Bearer Tokens** (`rsk_...`) passed in the `Authorization` header.
*   **WSGI Server**: [Gunicorn](https://gunicorn.org/) (Production) / Flask Dev Server (Local).
*   **Worker**: Custom `worker.py` script for asynchronous session analysis.

### **Frontend (Modern Vanilla JS)**
*   **UI**: Static HTML5/CSS3 plus a large vanilla-JS single-page app served from `server/ui/`.
*   **Architecture**: Browser-first SPA with view switching inside `server/ui/app.js`.
*   **Rendering**: Custom DOM/SVG/canvas rendering for telemetry, charts, and playback. There is no React/Vite/Webpack build pipeline in the current repo.
*   **Direct-to-Cloud + Local Ops**:
    *   The UI polls backend APIs for heartbeats and sync/device state.
    *   Local-network device operations still exist (`/api/device/scan`, `/api/device/check`, `/api/device/configure`, `/api/device/update-ota`), but are server-side gated with `@local_only`.
*   **Target**: Browser-first web app served directly by Flask from `server/ui/`.

### **Infrastructure**
*   **Host**: **Host.co.in** self-managed VPS (Ubuntu).
*   **Server Model**: Non-managed infrastructure. RaceSense owns OS-level setup, PostgreSQL, Nginx, systemd, SSL, backups, and deploy automation directly.
*   **Reverse Proxy**: **Nginx**.
    *   **Secured**: SSL termination via Certbot.
    *   **IoT Ready**: Explicitly proxies the `Authorization` header to the backend to support device tokens.
*   **Process Manager**: **Systemd** (managing `racesense.service` and `racesense-worker.service`).
*   **DNS**: Production DNS points the public RaceSense domain to the Host.co.in server before Nginx/Gunicorn routing takes over.

### **Hardware & Firmware (RS-Core)**
*   **MCU (Dual-Target)**: 
    *   **ESP32-S3**: RS-Core V4.2 PCB (Dual-core Xtensa 240MHz, 16MB Flash, 8MB Octal PSRAM).
    *   **ESP32-P4**: Waveshare 4.3" MIPI-DSI (Dual-core RISC-V 400MHz, 16MB Flash, 32MB PSRAM).
*   **OS / Framework**: **Native C/C++ on ESP-IDF v5.3 / FreeRTOS SMP** (migrated from legacy MicroPython v1.22 for deterministic real-time sampling).
*   **Core Allocation**: Core 0 strictly reserved for hard real-time telemetry (100Hz BMI323 IMU + 10Hz Neo-M8N GPS). Core 1 assigned to LVGL rendering, SD card buffer draining, and Wi-Fi 6/SSL networking.
*   **Display & UI**: LVGL 8.4 responsive UI engine supporting 12 modular rider screens across both 2.8" SPI ILI9341 (320x240) and 4.3" MIPI-DSI ST7701 (800x480) panels with zero code changes.
*   **High-Speed Uplink**: Consolidated native HTTPS uploader (`network.c`) utilizing persistent SSL sessions, adaptive buffering, and resumable transfers (`X-Upload-Offset`).
*   **Documentation**: See [hardware_firmware.md](file:///Users/mj/Documents/datalogger-v2/docs/hardware_firmware.md) for dual-target pinouts, architecture details, and flashing instructions.

---

## 📜 Critical Scripts & Tools

### **1. Deployment & Sync**
*   [`deploy.sh`](file:///Users/mj/Documents/datalogger-v2/deploy.sh): The "Master" deployment script.
    *   `./deploy.sh upgrade`: Incremental sync (rsync), dependency install, PostgreSQL migration, and service restart.
    *   `./deploy.sh nuke`: Wipes the remote `/var/www/racesense` directory, restores DB/env, and rebuilds the `venv`.
*   [`sync_cloud.sh`](file:///Users/mj/Documents/datalogger-v2/sync_cloud.sh): A faster, rsync-only alternative for pushing code changes without a full rebuild.

### **2. Local Development**
*   [`start.sh`](file:///Users/mj/Documents/datalogger-v2/start.sh): Kills any processes on port `6969`, loads `env/development.env`, ensures local PostgreSQL exists, runs migrations, starts `worker.py`, then starts the Flask app.
*   [`deploy/ensure_local_postgres.sh`](file:///Users/mj/Documents/datalogger-v2/deploy/ensure_local_postgres.sh): Creates the expected local PostgreSQL database if missing.
*   [`reboot_racesense.sh`](file:///Users/mj/Documents/datalogger-v2/reboot_racesense.sh): Handy script to remotely restart Nginx and Gunicorn services if the server becomes unresponsive.

---

## ⚙️ Server Configuration

### **Systemd Service Paths**
*   **App Service**: `/etc/systemd/system/racesense.service`
*   **Worker Service**: `/etc/systemd/system/racesense-worker.service`
*   **Config Source**: [deploy/](file:///Users/mj/Documents/datalogger-v2/deploy/) directory in the repo.

### **Environment Files**
Environment-specific files live in `env/`:
- `env/development.env`: local development runtime
- `env/test.env`: test database and test-only settings
- `env/production.env`: server runtime config, stored on production at `/var/www/racesense/env/production.env`

Key variables:
- `JWT_SECRET_KEY`: JWT signing key.
- `FLASK_ENV`: Set to `production` or `development`.
- `DATABASE_URL`: Required in every environment. Must point to PostgreSQL.
- `TEST_DATABASE_URL`: Used by the test suite when loading `env/test.env` or when injected directly by CI/local test runs.

---

## ⚠️ Precautionary Guidelines (DO NOT BREAK)

### **1. Database Silo Uniqueness**
In the `sessions` and `tracks` tables, constraints are set as `UNIQUE(session_id, user_id)`. Never change this to just `UNIQUE(session_id)`, as different users may have overlapping track IDs or session folder names.

### **2. User Data Storage**
User data is persisted under `server/data/users/<user_id>/...` via helpers in `server/api/config.py`. This includes raw learning CSVs, processed session JSON, playback artifacts, tracks, and user media. **Never run `rm -rf` on `server/data/users`** without a full backup, as these files remain a primary source of truth alongside the DB.

### **3. Worker Concurrency**
The current `worker.py` process polls the `jobs` table and executes one queued job at a time per worker process. In the standard local setup there is one worker process, so analysis is effectively serialized. PostgreSQL removes the old SQLite locking pressure, but queue serialization still protects CPU and disk contention.

### **4. Local vs Production Device Ops**
Device scan/check/configure/update endpoints are still present for LAN workflows, but sensitive local-network actions are protected with the `@local_only` decorator in `server/api/decorators.py`. Any future local-only developer harness should follow the same minimum rule and ideally avoid registering dev routes in production entirely.

---

## 🏥 Quick Troubleshooting
- **Logs**: `ssh server "journalctl -u racesense -f"`
- **Worker Hangs**: `ssh server "ps aux | grep worker.py"` and check `worker.log`.
- **Nginx Error**: `ssh server "nginx -t"` to check for syntax errors after a manual config change.
