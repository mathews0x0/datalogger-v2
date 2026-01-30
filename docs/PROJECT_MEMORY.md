# Motorcycle Datalogger Project — Complete Consolidated Memory

**Last Updated:** 2025-12-25

## 1. Project Vision & Goals (PM Summary)

**Primary Goal:**
Help riders improve track performance lap-by-lap.

- Provide **offline analysis first**; live feedback later (Layer 4).
- **Always-learning, persistent system:** continuously improves "Theoretical Best Lap" across sessions.

**System Principles:**

- **Persistent Learning:** Always updates best lap and sector records across sessions.
- **Stable Sectors:** Rider-facing sector divisions must not change. Fixed 7 sectors for non-kart tracks.
- **Trustable Feedback:** Data must be correct and interpretable; live feedback is deferred.
- **Offline Utility:** Riders can improve without live indicators, by analyzing data post-session.
- **Durability:** Hardware must survive vibration, power cuts, dust, and temperature extremes.
- **Ease-of-Use:** Minimal on-device buttons; future Buddy App/WebApp provides additional controls.

---

## 2. Timeline of Development & Milestones

### 2025-12-09

- **Project outline & build plan** for Raspberry Pi-based datalogger.
- Core features: GPS, IMU, BMP/BME pressure sensor, OLED display, 2 buttons, 2 LEDs.
- Decided on headless Raspberry Pi 4 system.

### 2025-12-12

- Local project path defined: `/home/pi/projects/datalogger`.

### 2025-12-15

- **Hardware redesign finalized.**
- Wire color coding standardized (See Hardware Section).
- UART mapping corrected (Purple = Pi RX).

### 2025-12-16

- **Coding standards:** Full class refactoring, unbuffered logging.

### 2025-12-17 to 2025-12-18

- **System bring-up tests:** GPS Fix verify, LED behavior check, Data sanity checks.

### 2025-12-19

- **Deployment Planning:** NEO-6M vs M8N. Mounting locations (Underseat vs Tail).

### 2025-12-20

- **System Vision Clarified:** Continuous learning, persistent JSON database.
- **Sector Logic:** Fixed 7 sectors decided. Live feedback deferred.

### 2025-12-21

- **Sector Freeze & Persistent Learning Implemented (Phase 2):**
  - Tracks standardized to 7 sectors.
  - Split points auto-generated from _Fastest Lap_ of learning session.
  - Track JSON stores: Sectors + Best Sector Records + Best Real Lap + Theoretical Best.
  - **Theoretical Best Lap** = sum of best sector times.
  - System fully functional: Log -> Generate -> Analyze.

### 2025-12-22

- **Cleanup & Consolidation (Phase 2.5):**
  - Removed legacy artifacts (`src/modules`, `src/logger`, `src/output`).
  - Created **Consolidated Installer** (`install_services.sh`) covering Dependencies + Hardware + Services.
  - Created Remote Cleanup Script for Pi synchronization.

### 2025-12-22 (Evening)

- **GPS Hardware Upgrade (NEO-M8N) - COMPLETE:**
  - **Phase A/B:** Validated 10Hz @ 115200 Baud using UBX commands.
  - **Phase D (Integration):**
    - Implemented `GPS_UBX_OPTIMIZATION` flag in `config.py`.
    - Updated `GPSModule` to auto-detect baud (115200 fallback to 9600) and auto-upgrade to 10Hz.
    - **Bottleneck Solved:** Fixed 4Hz logging limit by refactoring `poll_latest` to return **batches** of fixes instead of squashing them. System now logs full 10Hz stream.
  - **Visualization:** Created `scripts/plot_gps.py` for verifying traces.

### 2025-12-23 (Late Night)

- **Theoretical Best Lap (Persistence) - COMPLETE:**
  - **New Artifact:** `tracks/<track_id>_tbl.json`.
  - **Logic:** `TBLManager` updates TBL after every session.
  - **Validation:** `tests/test_tbl_persistence.py` passed.

### 2025-12-24

- **Data Persistence & Workflow Automation (Layer 3.5+):**
  - **Local Development:** Decoupled analysis logic from Pi hardware, enabling full Windows/Local testing.
  - **Theoretical Best Lap (TBL):** Implemented persistent `tracks/<id>_tbl.json` that updates incrementally.
  - **Session Export:** Auto-generation of `sessions/<id>.json` (UI-ready) after every session.
  - **Automated Workflow:**
    - Replaced manual steps with `SessionProcessor` orchestrator.
    - **"Unknown Track" Handling:** System now auto-detects unknown locations, infers geometry, generates track JSON/Map, and processes the session instantly without user intervention.

### 2025-12-25

- **Track Generation v2 - Production Ready:**

  - **Folder-per-Track Architecture:**
    - Implemented immutable track storage: `tracks/<track_id>/track.json` (frozen geometry)
    - Split mutable data: `tracks/<track_id>/tbl.json` (theoretical best lap records)
    - Auto-generated track maps: `tracks/<track_id>/track_map.png`
  - **Enhanced Loop Detection:**
    - **Heading-Verified Closure:** Start/finish line detection now validates heading consistency (±60°) to avoid false positives on figure-8 tracks or crossovers
    - **Pit Area Skipping:** Skips first 300 samples (30s) to avoid incorrectly identifying pit exit/entry as start line
    - **Extended Buffer:** Increased to 600 frames (60s) to ensure full lap closures are detected
  - **Reference Lap Selection:**
    - **Median Distance Filtering:** Calculates median lap distance and filters out outliers (±20%) to exclude short out-laps and long in-laps
    - Ensures track geometry is based only on clean flying laps
  - **Geometry Refinement:**
    - **5-point Moving Average Smoothing:** Removes GPS jitter and data artifacts
    - **Forced Loop Closure:** Mathematically closes the track loop for visualization
    - Track sectors recalculated on smoothed geometry for perfect alignment
  - **Visualization Improvements:**
    - Cleaner sector markers (vertical bars instead of dots)
    - Automatic loop closure in visualization
    - Suppressed overlapping start/finish labels
  - **Data Privacy:**
    - Created `scripts/anonymize_location.py` to offset GPS coordinates
    - Preserves track geometry while obscuring real location
    - Automatic backup of original data before anonymization
  - **Testing & Validation:**
    - Validated with real session data (3 laps, ~600m track)
    - Created augmented test dataset (Out lap + 5 flying laps + In lap)
    - Confirmed accurate lap detection (6/7 laps) and clean track maps
  - **Validation:** Verified pipeline with complex mocks (Kari Motor Speedway, CoASTT, Sepang).

- **Phase 3.1a - UI-Ready Filesystem Architecture:**

  - **Single output/ Boundary:**
    - Centralized all generated artifacts under `output/` directory for clean UI ingestion
    - Structure: `output/{learning/, tracks/, sessions/, registry.json}`
    - Provides authoritative filesystem boundary for UI/API layer
  - **Sequential Track Naming:**
    - Tracks now use human-readable sequential IDs: `track_1`, `track_2`, `track_3`
    - Replaced timestamp-based naming (`auto_20251225_1300`)
    - `RegistryManager` maintains track ID → human name mapping in `registry.json`
  - **Track-Aware Session Naming:**
    - Sessions explicitly linked to parent track: `track_N_session_M.json`
    - Enables filesystem-based queries (e.g., `glob("track_2_session_*.json")`)
    - Sequential numbering per track (track_2_session_1, track_2_session_2, etc.)
  - **Registry for UI:**
    - New `output/registry.json` provides track metadata and sequential number tracking
    - Eliminates need to scan/parse all track folders for discovery
  - **Migration:**
    - Created `scripts/migrate_to_output_structure.py` - non-destructive migration tool
    - Automatically renames legacy tracks and generates registry
  - **Code Changes:**
    - `src/config.py` - OUTPUT_ROOT centralization
    - `src/analysis/core/registry_manager.py` - New module for registry management
    - `src/analysis/core/track_generator.py` - Registry integration
    - `src/analysis/core/session_processor.py` - Sequential track ID generation
    - `src/analysis/core/session_exporter.py` - Track-aware session naming
  - **Testing:**
    - Validated sequential track creation (track_2)
    - Confirmed track-aware session naming (track_2_session_1.json, track_2_session_2.json)
    - Verified registry auto-updates on track creation
    - Tested track reuse (multiple sessions on same track)

- **Phase 3.1b - Identity Immutability Architecture:**

  - **Core Principle:**
    - **Identity (Immutable):** `track_id` is numeric (1, 2, 3...) and NEVER changes
    - **Display (Mutable):** `track_name` and `folder_name` can change via rename
    - Separation allows human-friendly naming without breaking references
  - **Track Structure:**
    - `track_id`: Numeric, immutable identity for all internal references
    - `track_name`: Human-readable string (e.g., "Kari Motor Speedway")
    - `folder_name`: Sanitized version of track_name for filesystem (e.g., "kari_motor_speedway")
    - Folder name always synchronized with track name
  - **Registry Format:**
    ```json
    {
      "next_id": 2,
      "tracks": [
        {
          "track_id": 1,
          "track_name": "Kari Motor Speedway",
          "folder_name": "kari_motor_speedway",
          "created": "2025-12-25T13:31:41",
          "last_updated": "2025-12-25T13:36:07"
        }
      ]
    }
    ```
  - **Rename Utility:**
    - Created `scripts/rename_track.py` for safe track renaming
    - Atomic operations with rollback on failure
    - Renames folder, all session files, updates track.json and registry
    - Maintains track_id immutability throughout
    - Features: dry-run mode, collision detection, idempotent
  - **Code Refactoring:**
    - `src/analysis/core/registry_manager.py`: Added numeric ID support, sanitize_name(), folder lookup
    - `src/analysis/core/track_generator.py`: Uses numeric track_id, folder_name from sanitized name
    - `src/analysis/core/session_processor.py`: Generates numeric IDs via registry
    - `src/analysis/core/session_exporter.py`: Looks up folder_name for session naming
    - `src/analysis/core/tbl_manager.py`: Uses folder_name for file paths via registry lookup
    - All modules updated to use `track_id` (int) instead of `id` (str)
  - **Filesystem Behavior:**
    - Before rename: `output/tracks/track_1/`, sessions: `track_1_session_1.json`
    - After rename: `output/tracks/kari_motor_speedway/`, sessions: `kari_motor_speedway_session_1.json`
    - Internal track_id: 1 (unchanged in all JSON files)
  - **Testing:**
    - Generated track with numeric ID (track_id: 1, folder: "track_1/")
    - Renamed track_1 → "Kari Motor Speedway" (folder: "kari_motor_speedway/")
    - Verified folder rename, session file rename, track.json update, registry update
    - Confirmed track_id immutability (stays 1 throughout)
    - Tested dry-run mode and collision detection
  - **Benefits:**
    - Human-friendly debugging (SSH into Pi, see "kari_motor_speedway/" not "track_20251225_1300/")
    - Zero broken references on rename (track_id never changes)
    - Clean UI presentation (show "Kari Motor Speedway", not "track_1")
    - Filesystem organization flexibility (rename anytime without data loss)

- **Phase 3.2a - Companion App MVP (Completed Dec 25):**
  - **Architecture:**
    - Flask API Server (`src/api/server.py`) serving a Single Page Application (PWA).
    - No internet required; designed to run on Pi's WiFi hotspot.
    - Dark-themed, responsive UI using Vanilla CSS/JS (no heavy frameworks).
  - **Features Implemented:**
    - **Dashboard:** At-a-glance stats (Total Tracks, Sessions, Recent Activity).
    - **Tracks Management:** View track maps, stats (TBL, sectors), and Rename tracks (Modal UI).
    - **Session Analysis:** Detailed lap tables, delta times, and sector breakdowns.
    - **Processing:** UI button to manually trigger `run_analysis.py` on raw CSVs.
  - **Technical Achievements:**
    - **Dual-Schema Support:** API transparently handles legacy session files (old `aggregates` format vs new `summary` format).
    - **Zero-Config:** Auto-discovers tracks and sessions from `output/` directory.
    - **Robustness:** Error boundaries prevent UI crashes on malformed data; "Connecting..." state recovery.
    - **UX:** Replaced native prompts with custom modals for a polished feel.

---

## 3. Hardware Summary

### Components & Wiring

| Component        | Connection                                    | Wire Color                   | Notes                            |
| :--------------- | :-------------------------------------------- | :--------------------------- | :------------------------------- |
| **GPS (UART)**   | Purple=Pi RX (GPIO15)<br>White=Pi TX (GPIO14) | Purple/White                 | **NEO-M8N** (115200 Baud / 10Hz) |
| **IMU**          | I2C (SCL=GPIO3, SDA=GPIO2)                    | Yellow (SCL)<br>Orange (SDA) | MPU9250                          |
| **BMP/BME**      | I2C (Shared)                                  | Yellow/Orange                | Pressure/Temp                    |
| **OLED**         | I2C (Shared)                                  | Yellow/Orange                | Status Display (SH1106)          |
| **Toggle Btn**   | GPIO17                                        | Grey                         | Start/Stop Logging (Debounced)   |
| **Shutdown Btn** | GPIO27                                        | Brown                        | Safe Output                      |
| **Logger LED**   | GPIO23                                        | Green                        | ON = Logging                     |
| **Ready LED**    | GPIO22                                        | Blue                         | System Ready                     |
| **Power/GND**    | 5V/GND                                        | Red/Black                    | Standard Supply                  |

### Physical Placement

- **Underseat:** Pi, IMU, BMP (Protected from elements).
- **Tail:** GPS (Clear view of sky).
- **Handlebar:** Buttons (Accessible).

---

## 4. Software & System Architecture

### Layers

| Layer                      | Status      | Function                                         |
| :------------------------- | :---------- | :----------------------------------------------- |
| **Layer 1: Truth Capture** | ✅ Complete | Reliable raw telemetry logging (10Hz GPS).       |
| **Layer 2: Structure**     | ✅ Complete | Track JSON generation, auto-ID, lap detection.   |
| **Layer 3: Comparatives**  | ✅ Complete | Best lap, sector segmentation, delta math.       |
| **Layer 3.5: Persistence** | ✅ Complete | Theoretical Best Lap, Persistent Sector Records. |
| **Phase 9: Feedback**      | 🟡 Active   | Live LEDs, real-time signaling.                  |

### Canonical Artifacts

1.  **Primary:** `tracks/<track_id>.json` (Mutable, Authoritative).
    - Contains Fixed Geometry (Sectors).
    - Contains Mutable Records (Best Times).
2.  **Secondary:** CSV Logs (`learning/` and `output/`).
3.  **Scripts:**
    - `generate_track.py` (Track Gen)
    - `run_analysis.py` (Analysis)
    - `plot_gps.py` (Visualization)

---

## 5. Key Product Decisions

| Topic             | Original Idea       | Final Decision         | Reason                         |
| :---------------- | :------------------ | :--------------------- | :----------------------------- |
| **GPS Rate**      | 1Hz (Standard)      | **10Hz (UBX Opt)**     | Detailed corner analysis.      |
| **Sector Count**  | Dynamic per session | **Fixed 7** (Non-kart) | Preserve rider mental mapping. |
| **Learning**      | Session-only        | **Continuous**         | Total performance picture.     |
| **Best Lap**      | Real Best only      | **Theoretical Best**   | Show true potential.           |
| **Live Feedback** | Phase 1             | **Deferred**           | Reliability first.             |
| **UI**            | Touchscreen?        | **Headless + Buttons** | Durability & Simplicity.       |

---

## 6. Phase 3 Roadmap: Software Robustness & UX

**Status:** Resuming after GPS Upgrade.

### 3.1 Persistent JSON & Logging Robustness

- **Goal:** Ensure data is never lost or corrupted.
- **Tasks:** Atomic JSON writes, corruption recovery, verifying Learning/Active isolation.

### 3.2 Buddy App / WebApp MVP

- **Goal:** Remote control and easier analysis viewing.
- **Features:** Remote Start/Stop, Trigger Analysis, View Best Laps/Sectors.

### 3.3 Data Validation & Test Scripts

- **Goal:** Trustable metrics.
- **Tasks:** Automated regression testing (Session -> Generate -> Analyze), verifying sector time accuracy.

### 3.4 Preparation for Future Layer 4

- **Goal:** Ready the math for live feedback.
- **Tasks:** Define delta thresholds in config, simulate LED output logic.
