# Monorepo Migration Plan: Pi Datalogger Product

**Date:** 2026-01-24
**Objective:** Restructure the codebase into a monorepo to support multiple hardware targets (Pi, ESP32) and deployment modes (Standalone, Cloud-Connected) while preserving the current "All-in-Pi" functionality.

---

## 1. Target Architecture

### Directory Structure

```text
datalogger-product/          # Root Directory (Renamed from datalogger-on-pi)
├── firmware/
│   ├── esp32/               # [NEW] MicroPython Dumb Logger
│   │   ├── main.py
│   │   └── ...
│   └── pi/                  # [MOVED] Python Logger Service
│       ├── src/logger/      # Only the logging logic (sensors -> CSV)
│       └── ...
│
├── core-analysis/           # [EXTRACTED] Shared Python Library ("The Brain")
│   ├── track_learning/      # Track generation algo
│   ├── lap_detection/       # Lap timing algo
│   ├── processing/          # Session processing pipeline
│   └── setup.py             # Pip installable package
│
├── cloud-backend/           # [NEW] Flask App for Cloud Processing
│   ├── api/
│   └── ...                  # Imports core-analysis
│
├── apps/
│   └── web-companion/       # [MOVED] The Frontend UI (Currently src/api/static)
│       # Shared by Pi Standalone and Cloud
│
└── products/                # Deployment Configurations
    ├── pi-standalone/       # [CURRENT] "Classic" Mode
    │   ├── deploy.sh        # Installs firmware/pi + core-analysis + Local API
    │   └── services/        # Systemd files for full stack
    │
    └── pi-dumb/             # [NEW] "Cloud Mode" Mode
        ├── deploy.sh        # Installs firmware/pi ONLY
        └── services/        # Systemd files for logger only
```

---

## 2. Deployment Scenarios

### Scenario A: Pi Standalone (Classic)
**Use Case:** User buys "Pro Bundle", wants zero cloud reliance.
**Architecture:**
- **Host:** Raspberry Pi
- **Running:** `firmware/pi` (Logger) + `core-analysis` (Local Lib) + `apps/web-companion` (Local Server)
- **Data Flow:** Sensors -> CSV -> Local Python Script -> Local `output/` -> Local Web UI

### Scenario B: Pi Dumb Logger (Cloud Mode)
**Use Case:** User buys "Standard" Pi hardware, relies on Cloud.
**Architecture:**
- **Host:** Raspberry Pi
- **Running:** `firmware/pi` (Logger only) + `cloud-uploader` (Script)
- **Data Flow:** Sensors -> CSV -> Upload to Cloud -> **Cloud Analysis** -> App

### Scenario C: ESP32 Dumb Logger
**Use Case:** Mass market product.
**Architecture:**
- **Host:** ESP32
- **Running:** `firmware/esp32` (MicroPython)
- **Data Flow:** Sensors -> CSV (SD Card) -> Upload to Cloud -> **Cloud Analysis** -> App

---

## 3. Migration Roadmap

### Phase 1: Preparation (Safe State)
1.  **Stop Services:** Ensure no active logging or API server is running.
2.  **Backup:** Create a full zip archive of current directory.
3.  **Audit:** Verify all uncommitted changes.

### Phase 2: Restructure (The Move)
*Action Log ID: MIGR-001*
1.  Create root folders: `firmware`, `core-analysis`, `products`, `apps`.
2.  **Move** `src/analysis` -> `core-analysis/datalogger_core` (Rename package).
3.  **Move** `src/api/static` -> `apps/web-companion`.
4.  **Move** remaining `src/` (Logger, Hardware) -> `firmware/pi/src`.
5.  **Move** `docs/` -> `docs/` (Root level).

### Phase 3: Refactor Imports (The Fix)
*Action Log ID: MIGR-002*
1.  **Pi Firmware:** Update imports to remove analysis dependencies.
    - Change `from src.analysis import ...` to `import datalogger_core`.
2.  **Core Analysis:** Make it a standalone pip package.
    - Create `setup.py`.
    - Fix internal relative imports.
3.  **Web App:** Point Flask server to new template/static locations.

### Phase 4: Local Verification (Standalone Mode)
*Action Log ID: MIGR-003*
1.  Install `core-analysis` in editable mode (`pip install -e core-analysis`).
2.  Run Pi Logger from new location.
3.  Run API Server from new location.
4.  Verify "Classic" functionality works exactly as before.

### Phase 5: Documentation Update
1.  Update `SYSTEMD_SETUP.md` with new paths.
2.  Update `PROJECT_PHASES.md` with "Phase 13: Monorepo Architecture".
3.  Update `README.md` in root to explain the new structure.

---

## 4. Rollback Plan

**Trigger:** If Phase 4 fails and cannot be fixed within 2 hours.

**Procedure:**
1.  Delete the fragmented directory structure.
2.  Unzip the Phase 1 Backup.
3.  Restore systemd services to point to original paths.
4.  Restart services.

---

## 5. Artifacts to Create

1.  `MIGRATION_LOG.md`: A live document tracking every `mv` command.
2.  `setup.sh`: A new developer setup script to install the monorepo deps.
3.  `deploy_pi_standalone.sh`: Script to configure a Pi for Classic mode.

---

## 6. Project Renaming

**Current:** `datalogger-on-pi`
**Proposed:** `open-datalogger` or `track-telemetry-OS`
**Recommendation:** Keep folder name generic `datalogger-product` for now to avoid breaking IDE workspaces/recent file lists, but update `README` title.

---

**Next Step:** Approve detailed plan to begin Phase 1 (Backup & Stop Services).
