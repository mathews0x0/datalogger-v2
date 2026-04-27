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
*   **UI**: Standard HTML5, CSS3 (Custom variables, Flexbox/Grid).
*   **Architecture**: **Direct-to-Cloud (IoT)**.
    *   The UI polls the Cloud API (`/api/devices`) for heartbeats.
    *   Local network discovery/IP scanning has been decommissioned.
*   **Maps**: [Leaflet.js](https://leafletjs.com/) for track visualization.
*   **Charts**: Custom SVG-based telemetry traces and [Chart.js](https://www.chartjs.org/) for interactive plots.
*   **Target**: Browser-first web app served directly from `server/ui/`.

### **Infrastructure**
*   **Host**: **Host.co.in** self-managed VPS (Ubuntu).
*   **Server Model**: Non-managed infrastructure. RaceSense owns OS-level setup, PostgreSQL, Nginx, systemd, SSL, backups, and deploy automation directly.
*   **Reverse Proxy**: **Nginx**.
    *   **Secured**: SSL termination via Certbot.
    *   **IoT Ready**: Explicitly proxies the `Authorization` header to the backend to support device tokens.
*   **Process Manager**: **Systemd** (managing `racesense.service` and `racesense-worker.service`).
*   **DNS**: Production DNS points the public RaceSense domain to the Host.co.in server before Nginx/Gunicorn routing takes over.

### **Hardware & Firmware (RS-Core)**
*   **MCU**: ESP32-S3 (Dual-core 240MHz).
*   **OS**: MicroPython v1.22.
*   **Key Drivers**: BMI323 (IMU), Neo-M8N (GPS), SPI SD Card.
*   **Display Baseline**: TFT-only rider-facing UI in the active firmware; legacy OLED support has been retired from the current codebase.
*   **High-Speed Uplink**: Custom uploader using **Raw SSL Sockets** and **Persistent Connections** for high-throughput (64KB chunks) telemetry sync.
*   **Documentation**: See [hardware_firmware.md](file:///Users/mj/Documents/datalogger-v2/docs/hardware_firmware.md) for pinouts and flashing guides.

---

## 📜 Critical Scripts & Tools

### **1. Deployment & Sync**
*   [`deploy.sh`](file:///Users/mj/Documents/datalogger-v2/deploy.sh): The "Master" deployment script.
    *   `./deploy.sh upgrade`: Incremental sync (rsync), dependency install, PostgreSQL migration, and service restart.
    *   `./deploy.sh nuke`: Wipes the remote `/var/www/racesense` directory, restores DB/env, and rebuilds the `venv`.
*   [`sync_cloud.sh`](file:///Users/mj/Documents/datalogger-v2/sync_cloud.sh): A faster, rsync-only alternative for pushing code changes without a full rebuild.

### **2. Local Development**
*   [`start.sh`](file:///Users/mj/Documents/datalogger-v2/start.sh): Kills any processes on port 6969, loads `env/development.env`, and starts both the **Backend** and the **Worker** locally.
*   [`reboot_racesense.sh`](file:///Users/mj/Documents/datalogger-v2/reboot_racesense.sh): Handy script to remotely restart Nginx and Gunicorn services if the server becomes unresponsive.

### **3. Database Hacks**
*   [`patch_production_db.py`](file:///Users/mj/Documents/datalogger-v2/patch_production_db.py): Use this when structural changes (like adding `UNIQUE` constraints across multiple columns) aren't easily handled by Alembic. It performs a "Copy -> Drop -> Recreate -> Restore" cycle.

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
- `SECRET_KEY`: Flask session security.
- `JWT_SECRET_KEY`: JWT signing key.
- `FLASK_ENV`: Set to `production` or `development`.
- `DATABASE_URL`: Required in every environment. Must point to PostgreSQL.
- `TEST_DATABASE_URL`: Used by the test suite when loading `env/test.env` or when injected directly by CI/local test runs.

---

## ⚠️ Precautionary Guidelines (DO NOT BREAK)

### **1. Database Silo Uniqueness**
In the `sessions` and `tracks` tables, constraints are set as `UNIQUE(session_id, user_id)`. Never change this to just `UNIQUE(session_id)`, as different users may have overlapping track IDs or session folder names.

### **2. The Instance Folder**
The `server/instance/data` folder contains all raw telemetry and analyzed JSONs. **Never run `rm -rf` on this folder** without a full backup, as these files are the primary source of truth for the platform (even more than the DB).

### **3. Worker Concurrency**
The `worker.py` script is designed to run a single job at a time per user to avoid unnecessary I/O pressure while the web server is active. PostgreSQL removes SQLite locking concerns, but this queue behavior still protects CPU and disk contention.

### **4. Local vs Production IPs**
The networking code in `devices.py` (Scanning) uses a proxy logic. While developing locally, it scans `192.168.*`. In production, this feature is disabled via the `@local_only` decorator to prevent the server from scanning its internal VPC network.

---

## 🏥 Quick Troubleshooting
- **Logs**: `ssh server "journalctl -u racesense -f"`
- **Worker Hangs**: `ssh server "ps aux | grep worker.py"` and check `worker.log`.
- **Nginx Error**: `ssh server "nginx -t"` to check for syntax errors after a manual config change.
