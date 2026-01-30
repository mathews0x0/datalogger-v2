# Full System Walkthrough & State of the Platform

**Date:** Dec 25, 2025
**Version:** 3.7 (Phase 3.1b - Identity Immutability)

## 1. System Overview

The Motorcycle Data Logger is an offline, embedded telemetry system designed to run on a Raspberry Pi Zero W. It captures high-frequency sensor data (GPS, IMU) and performs on-device analysis to provide riders with performance metrics without requiring detailed post-processing on a PC.

**What it solves:**

- Automated data capture without user interaction.
- Immediate "at the track" insights (Lap times, Sector splits, theoretical bests).
- Clean separation of "Map Making" vs "Racing" data.

**What it does NOT solve (yet):**

- Real-time dashboard display (OLED is for status only).
- AI-driven coaching or "human-like" advice (Layer 4).

## 2. Operating Modes

The system operates in two mutually exclusive modes to ensure data integrity.

### Learning Mode

- **Purpose:** Map a new circuit.
- **Behavior:** Logs raw telemetry to `src/learning/`.
- **Switching:** Default mode on fresh install. Switch via socket cmd: `SET_MODE LEARNING`.
- **Why:** prevents incomplete/exploration laps from polluting the rider's personal best database.

### Active Mode

- **Purpose:** Record race/practice sessions on a known track.
- **Behavior:** Logs raw telemetry to `src/output/`.
- **Switching:** Switch via socket cmd: `SET_MODE ACTIVE`.
- **Why:** Ensures all files in `output/` are valid candidates for analysis and comparison.

**Safeguards:** When switching modes, the logger strictly flushes buffers, closes the current file, and opens a new file in the target directory immediately.

## 3. Data Lifecycle

| Stage             | Input             | Process                            | Output           | Location                   |
| :---------------- | :---------------- | :--------------------------------- | :--------------- | :------------------------- |
| **1. Capture**    | Sensors (GPS/IMU) | `CSVLogger` buffers & writes       | Raw CSV          | `output/learning/`         |
| **2. Generation** | Learning CSV      | `TrackGenerator` extracts geometry | Track Folder     | `output/tracks/<track_N>/` |
|                   |                   |                                    | - track.json     | (Immutable geometry)       |
|                   |                   |                                    | - tbl.json       | (Theoretical best lap)     |
|                   |                   |                                    | - track_map.png  | (Visual confirmation)      |
|                   |                   |                                    | - registry.json  | (Track metadata)           |
| **3. Ingestion**  | Active CSV        | `TrackManager` identifies track    | `Session` Object | _In-Memory_                |
| **4. Analysis**   | `Session` Object  | `LapDetector` & `StatsEngine`      | Session JSON     | `output/sessions/`         |
|                   |                   |                                    |                  | `track_N_session_M.json`   |
| **5. Insight**    | Valid Laps        | `Comparator` (Ghost Engine)        | Delta Arrays     | _Terminal / Text Report_   |

## 4. Layer-by-Layer Breakdown

### Layer 1: Truth Capture (Frozen)

- **Responsibility:** Hardware abstraction, timing, and raw logging.
- **Key Components:** `SensorManager`, `CSVLogger`, `GPSModule`.
- **Output:** 10Hz CSV files with deduplicated 1Hz GPS.

### Layer 2: Structural Understanding (Frozen)

- **Responsibility:** Making sense of raw data.
- **Key Components:**
  - `TrackManager`: Auto-detects track based on GPS proximity to `start_line` in `tracks/*.json`.
  - `LapDetector`: Crossing detection with debouncing.
  - `Resampler`: Normalizes time-based data to distance-based arrays (10m steps).

### Layer 3: Comparative Primitives (Frozen)

- **Responsibility:** Mathematical comparison of laps.
- **Key Components:**
  - `StatsEngine`: Identifies Best Lap and calculates Sector Times.
  - `Comparator`: Ghost Engine. Aligns two laps by distance and calculates `delta_time` and `delta_speed` at every step.

## 5. Analysis Capabilities (Current)

### Lap Detection

- **Logic:** Haversine distance < Track Radius (20m).
- **Constraint:** Must assume a closed loop. Crossing heading is checked to prevent "wrong way" triggers.

### Sector Segmentation

- **Logic:** Tracks defined in JSON can have `sectors` (list of lat/lon points).
- **Output:** Splits lap into S1, S2, S3...
- **Assumption:** Sectors must be crossed in order.

### Ghost Analysis (Delta)

- **Comparable:** Last Lap vs Best Lap (Session Best).
- **Resolution:** Every 10 meters.
- **Outputs:**
  - **Time Delta:** "0.5s ahead" (Negative is good).
  - **Speed Delta:** "5km/h faster" (Positive is good).

### Sensor Analysis (Phase 7.3)

- **IMU Calibration:** Auto-detects Z-axis gravity vector on session load.
- **Rider Metrics:**
  - **Stability (%):** Inverse of Jerk. High score = Smooth ride.
  - **Lateral Load (%):** Cornering intensity relative to session peak.
- **Output:** Saved in `session.json` and visible in Companion App.

### Lap Drill-Down Analysis (Phase 7.4)

- **Visual Dashboard:** Interactive grid per lap containing:
  - **Rider Dynamics Map:** Visualization of Acceleration (Green), Braking (Red), and Lateral Forces (Glow/Road) to reveal rider inputs.
  - **Speed Profile Map:** Heatmap (Green=Fast, Red=Slow) to identify corner speeds.
- **Detailed Inspection:**
  - **Modal View:** Click-to-expand maps for full-screen analysis.
  - **G-Force Trace:** Toggles in the Dynamics view, synchronized with map markers and sector boundaries.
- **Metric Breakdown:**
  - **Sector Table:** Compares current lap splits against the Session's Theoretical Best Lap (TBL).
  - **IMU Badge:** Indicates confidence level of the sensor data used for the map.

## 6. Folder & Artifact Map

```text
project_root/
├── src/
│   ├── analysis/          # Engine code (Layers 2 & 3)
│   │   ├── core/          # TrackManager, Models
│   │   ├── processing/    # Stats, Laps, Resampling
│   │   └── run_analysis.py # Main CLI Tool
│   ├── drivers/           # Hardware Drivers (GPS, OLED, IMU)
│   ├── services/          # Apps Logic (Logger, Feedback)
│   ├── core/              # Config & State
│   ├── api/               # Companion App Server
│   │   ├── static/        # PWA (HTML/CSS/JS)
│   │   └── server.py      # Flask API
│   └── main.py            # Entry Point
├── learning/              # [Data] Raw Logs from Learning Mode
├── output/                # [Data] Raw Logs from Active Mode
├── tracks/                # [Ref] JSON Definitions (Kari, etc.)
├── scripts/               # Maintenance Scripts
├── docs/                  # Documentation
└── install_services.sh    # Master Installer
```

## 7. How to Run the System

### A. Network Boot Selector (Hardware Switch)

The system runs a determinstic network selection script at boot.

- **Client Mode (Default):** Power on **normally**.

  - Result: Connects to Home/Paddock Wi-Fi (if configured).
  - OLED Display: `READY (CLIENT)`

- **Hotspot Mode (Fail-Safe):** Power on while **holding the Grey Button**.
  - Hold for ~10-15s until the Green LED stops flashing.
  - Result: Forces Critical Hotspot (`DataloggerAP`).
  - OLED Display: `READY (HOTSPOT)`

Use Hotspot mode if you are at a new track or cannot connect via Wi-Fi.

### B. Companion App (Web Dashboard)

The system runs a web server for data analysis on **Port 5000**.

1.  **Connect** to the Pi (via Hotspot `192.168.4.1` or Client Mode IP).
2.  **Open Browser** on your phone/laptop.
3.  **Navigate to:** `http://<PI_IP>:5000` (e.g., `http://192.168.4.1:5000`).
4.  **Usage:**
    - **Learning Tab:** Upload/Process raw CSV logs.
    - **Tracks Tab:** View generated tracks and session history.
    - **Session Detail:** View Lap Timing, G-Force, and Map Analysis.

### C. Learn a New Track

1.  **Boot:** System starts in Learning Mode (default).
2.  **Ride:** Complete 2-3 laps.
3.  **Process:**
    - Use the Companion App "Process" button for 1-click analysis.

### D. Data Management (Export & Sharing)

**1. Renaming Sessions:**

- Click the **Pencil Icon (✎)** next to the session title.
- Give it a meaningful name (e.g., "Qualifying - Soft Tires").
- The name is updated instantly.

**2. Downloading Data (Backup):**

- Click **"Export ZIP"** in the session detail view.
- A ZIP file containing the Session JSON and a summary README will download to your device.

**3. Sharing Reports:**

- Click **"Print Report"**.
- The view will strip all buttons and navigation.
- Use your browser's "Save as PDF" to create a clean, shareable document.

## 8. Known Limitations & Risks

- **GPS Noise:** 1Hz GPS is low resolution. Start line crossing relies on interpolation.
- **Point-to-Point:** System currently assumes closed-loop circuits only.
- **Short Laps:** Laps < 10s are auto-discarded (hardcoded safety filter).
- **Mode Awareness:** If user forgets to `SET_MODE ACTIVE`, race data ends up in `learning/`. (Low risk: analysis script works on files from either folder).

## 8. Track Management

### Identity vs. Display Architecture

**Core Principle:**

- `track_id`: Numeric (1, 2, 3...), immutable - used for all internal references
- `track_name` and `folder_name`: Mutable - can be renamed without breaking references

**Renaming Tracks:**

```bash
py scripts/rename_track.py --track_id 1 --new_name "Kari Motor Speedway"
```

**What Changes:** Folder, session files, track.json name, registry  
**What Stays:** track_id (all references remain valid)

**Safety:** Dry-run mode, atomic operations, rollback on failure, collision detection

## 9. Explicit Non-Goals

- **Real-time Dashboard:** We are not building a GUI for the rider while riding.
- **Cloud Sync:** No cloud database. All data stays on SD card.
- **AI "Magic":** No neural networks or black-box predictions. All "insights" must be mathematically provable (deltas).

## 10. Phase 12: Companion App Enhancements (Deployed)

### 10.1 System Control & Feedback

- **Start/Stop Logging:** Manual control buttons in the UI header.
- **Recording Indicator:** A red blinking dot appears in the header when logging is active.
- **Status Polling:** The UI updates the status every 2 seconds.

### 10.2 Advanced File Management (Learning Mode)

- **Locking:** Click the Lock icon (🔓/🔒) to prevent accidental deletion of important files.
- **Bulk Delete:** Select multiple files and click the Trash icon to delete them (Locked files are safe).
- **Raw Data View:** Click the Eye icon (👁️) to view the first 100 lines of a CSV, color-coded for readability.
- **Path Visualization:** Click the Map icon (🗺️) to see the GPS path shape instantly.

### 10.3 Maintenance & Diagnostics

- **Tailscale Integration:** Run `bash setup_tailscale.sh` to enable remote VPN access.
- **Service Control:** Restart specific services (API, Logger) from **Settings > Service Maintenance**.
- **Diagnostics Tab:** Run interactive hardware tests for GPS, IMU, I2C, and LEDs.

---

_End of System Walkthrough_
