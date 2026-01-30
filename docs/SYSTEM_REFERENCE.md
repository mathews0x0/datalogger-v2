# Pi Datalogger System Reference

**Version:** 3.6 (Phase Realignment)
**Last Updated:** 2025-12-22

This document is the **Single Source of Truth** for the Pi Datalogger project. It must be updated whenever architecture or hardware understanding changes. If you are an AI assistant, **read this first**.

## Project Phase Status (Canonical)

| Phase  | Name                         | Status             | Definition                                        |
| :----- | :--------------------------- | :----------------- | :------------------------------------------------ |
| **1**  | **Truth Capture**            | ✅ **FROZEN**      | Reliable raw telemetry. No changes allowed.       |
| **2**  | **Structural Understanding** | ✅ **FROZEN**      | Learning/Ident, Track JSON gen.                   |
| **3**  | **Comparative Primitives**   | ✅ **FROZEN**      | Best Lap, 7-Sector fixed model.                   |
| **7**  | **Rider Performance**        | ✅ **ACTIVE**      | Visual Clarity, Spatial Understanding, Telemetry. |
| **8**  | **Diagnostics**              | 🟡 **ACTIVE**      | System Stability, Watchdogs, Power tolerance.     |
| **9**  | **Live Feedback**            | 🟢 **IMPLEMENTED** | Real-time LEDs, TBL-relative performance.         |
| **10** | **Coaching**                 | ⛔ **BLOCKED**     | Rider insights, high-level advice.                |

---

## 1. Hardware Architecture

**Platform:** Raspberry Pi 4 (Headless)

### GPIO Pin Mapping (BCM)

| GPIO   | Physical | Direction | Usage              | Note                 |
| :----- | :------- | :-------- | :----------------- | :------------------- |
| **27** | 13       | IN        | **Power Button**   | Pull-Up 10k          |
| **17** | 11       | IN        | **Toggle Button**  | Pull-Up 10k          |
| **26** | 37       | IN        | **Aux Button**     | Pull-Up 10k          |
| **22** | 15       | OUT       | **Power LED**      | Red (System Managed) |
| **21** | 40       | OUT       | **Status LED**     | Blue (App Managed)   |
| **25** | 22       | OUT       | **Aux LED 2**      | Custom               |
| **20** | 38       | OUT       | **Aux LED 3**      | Custom               |
| **18** | 12       | PWM       | **NeoPixel Strip** | 220Ω Resistor Reqd   |
| **2**  | 3        | I2C       | **SDA**            | OLED / IMU           |
| **3**  | 5        | I2C       | **SCL**            | OLED / IMU           |

### Sensors (I2C-1)

- **OLED (0x3C):** SH1106 driver. Managed by `src.drivers.oled_control` (Async/Threaded).
- **BMP280 (0x76):** Pressure/Temp.
- **MPU9250 (0x68):** IMU (Accel/Gyro).

### Sensors (Serial)

- **GPS:** `/dev/serial0` (**115200 baud**). **NEO-M8N** chip.
- **Config:**
  - Standard: 1Hz @ 9600.
  - **Optimized:** 10Hz @ 115200 (enabled by `GPS_UBX_OPTIMIZATION=True`).
  - **Parsing:** Reads `GPRMC` and `GPGGA` (Filtered).

---

## 2. Software Architecture (v3.4)

The application uses a modular, service-based design.

**Entry Point:** `src/main.py`

### Directory Structure

- `src/drivers/`: **Low-level hardware wrappers.**
- `src/services/`: **Business Logic & Managers.**
  - `csv_logger.py`: Handles dual-mode logging (`learning/` vs `output/`).
- `src/core/`: **Pure Logic/Data.**
- `src/analysis/`: **Offline Analysis Engine.**
  - `generate_track.py`: Creates Track JSONs from Learning Data.
  - `run_analysis.py`: CLI for generating reports.

### Analysis Layers

1.  **Layer 1 (Capture):** Raw CSV Logging.
2.  **Layer 2 (Structure):** `TrackManager` & `LapDetector`.
3.  **Layer 3 (Comparison):** `StatsEngine` & `Comparator` (Ghost Delta).
4.  **Layer 3.5 (Persistence):**
    - **Sector Freeze:** All tracks have **7 Fixed Sectors**.
    - **Synthesis:** System stores "Best Ever" sector times in `tracks/*.json` to calculate **Theoretical Best Lap**.

---

## 3. Deployment & Operations

### Services

The system runs via **Systemd** (User: `root`).

- **Main App:** `datalogger.service` -> Execs `python3 -u -m src.main`
- **Buttons:** `gpio_buttons.service` -> Execs `python3 -u src/scripts/gpio_buttons.py`
- **Note:** The `-u` flag is mandatory for unbuffered logging.

### Installation / Update

Run the **Consolidated Installer** in the project root:

```bash
cd /home/pi/projects/datalogger
sudo ./install_services.sh
```

This script handles:

1.  **Dependencies:** `apt` and `pip` packages.
2.  **Hardware Config:** Enabling I2C/UART, disabling `gpsd`.
3.  **Services:** Installing and restarting systemd units.

### Maintenance Commands

- **View Logs (Real-time):**
  ```bash
  journalctl -u datalogger -u gpio_buttons -f
  ```
- **Restart App:**
  ```bash
  sudo systemctl restart datalogger
  ```

---

## 4. Development Rules

1.  **Never hardcode pins:** Always use `src.core.pinmap`.
2.  **No blocking I/O:** OLED updates must use the `queue` system.
3.  **Unbuffered Output:** Always run python with `-u` in services to ensure logs are visible.

## 5. Canonical Artifacts (Data Persistence)

The system maintains a rigid file structure for data persistence. These files are the single source of truth for analysis and UI.

1.  **Track Definitions:** `tracks/<track_id>.json`

    - **Purpose:** Detailed geometry, sectors, and metadata for a known circuit.
    - **Source:** Manually created or Auto-Generated by `TrackGenerator`.
    - **Immutability:** Geometry is fixed; metadata is mutable.

2.  **Theoretical Best Lap (TBL):** `tracks/<track_id>_tbl.json`

    - **Purpose:** Persistent record of the "Perfect Lap" (sum of best sectors) + Best Real Lap reference.
    - **Update Logic:** Updated incrementally by `TBLManager` after _every_ valid session.
    - **Use Case:** The "Ghost" used for delta comparisons in future sessions.

3.  **Session Summaries:** `sessions/<session_id>.json`
    - **Purpose:** Self-contained, portable summary of a specific session for UI consumption.
    - **Content:** Laps, Sector Times, Deltas, Weather, and Links to Track/TBL.
    - **Generation:** Created by `SessionExporter` after analysis.

## 6. Project Roles & Workflow

- **Product Manager (Vision/Hardware):** ChatGPT (via User). Consult for overall design, hardware selection, and high-level feature requests.
- **Senior Developer (Implementation):** Antigravity (Me). Responsible for code architecture, refactoring, stability, and systemd integration.
- **Protocol:** When faced with a design ambiguity (e.g., "Should we add a new sensor?"), prompt the user to consult the PM.
