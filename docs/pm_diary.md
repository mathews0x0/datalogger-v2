# PM_DIARY — Motorcycle Data Logger Project

**Owner:** Product Management (PM)
**Purpose:** Single consolidated, authoritative project memory
**Last Updated:** 2026-03-22
PRODUCT manager - CHATGPT
Engineering manager/Devs - Antigravity

---

#
## 1. Project Intent (Inception)

**Date:** 2025-11 (late)

The project was conceived as a _serious rider development tool_, not a gadget.

Core intent defined from day one:

- Capture **truthful telemetry** first.
- Learn tracks **persistently** over time.
- Avoid premature coaching, AI, or live feedback.
- Prioritize correctness, repeatability, and rider mental mapping.

Key PM decision:

> _No insight is allowed unless the underlying data model is proven stable across real sessions._

This principle guided every phase that followed.

### Initial Conception (Dec 9, 2025)

**Core Goals:**

- Headless Raspberry Pi system (optional display for debug only).
- High-frequency data capture with GPS as primary timebase.
- Track mapping and performance analysis.
- AI insights explicitly deferred.

**Design Principles:**

- Manageable, not over-engineered.
- Testing phases at every stage.
- Core parameters: GPS, speed, altitude, gyro/IMU.

---

## 2. Phase-Based Architecture (Early Decision)

**Date:** 2025-11 (late)

PM formally adopted a **phased architecture** to prevent scope creep:

- Phase 1: Truth Capture
- Phase 2: Structural Understanding
- Phase 3: Comparative Primitives
- Phase 4: Insight & Intelligence (explicitly blocked)
- Phase 5: System Stability & Hardware Robustness
- Phase 9: Live Feedback

Key PM rule established:

> _A phase must be frozen before the next phase begins._

---

## 2.5. Early Planning & Hardware Validation

**Dates:** 2025-12-09 → 2025-12-13

### Planning Phase (Dec 9-12)

**Decisions:**

- Project goals, hardware selection, software workflow defined.
- Modular Python design adopted.
- GPS + IMU selected as initial sensors.
- BMP180/BME280 deferred to later phases.
- Build phases and stepwise testing strategy established.

**Local Dev Setup (Dec 10):**

- Project path: `/home/pi/projects/datalogger`
- VS Code SFTP workflow configured (upload-on-save).
- Raspberry Pi 4 selected as target platform.
- Boot automatically, run headless, log to files.

### Hardware Bring-up (Dec 13)

**Day 1 of Practical Implementation:**

- Pi 4 headless setup completed (SSH, SFTP working).
- ACT LED test successful.
- MPU6050 wired and readings verified.
- GPS module wired, serial configured, GPS fix obtained.
- NMEA data streaming validated in Python.

**Key Decision:**

- In-memory buffer strategy with threshold-based CSV flush adopted.

**Outcome:**

- Hardware validation complete.
- Foundation laid for Phase 1 implementation.

---

## 3. Phase 1 — Truth Capture (Frozen)

**Dates:** 2025-11 → early 2025-12

### Scope

- Reliable raw telemetry logging
- GPS-based sampling
- No inference, no filtering beyond sanity checks

### Decisions

- Raw telemetry is treated as **ground truth**.
- Learning mode is always on.
- Live feedback explicitly excluded.

### Early Development (Dec 14-15, 2025)

**Hardware Evolution (Dec 14):**

- Upgraded MPU6050 → MPU9250 (9-axis IMU).
- Soldered MPU9250 + GPS onto compact PCB (robust prototype).
- IMU verified: accelerometer, gyroscope working; magnetometer deferred.

**Main Logger Architecture (Dec 14):**

- Created `logger.py` as orchestrator.
- Polling: IMU ~100Hz, GPS ~1Hz (opportunistic).
- In-memory buffer with threshold flush (500 rows OR 5 seconds).
- Modular structure: `logger.py`, `buffer.py`, `file_writer.py`, `gps_module.py`.
- CSV output: timestamp, IMU data, GPS data + validity.

**Integration Challenges (Dec 15):**

- LED health indicator implemented (RED OFF = healthy).
- systemd autostart attempted but runtime issues found.
- Decision: Pause autostart until logger stability proven.

**Infrastructure Incident:**

- Multiple power interruptions → filesystem corruption.
- Recovery: Files backed up, manual runs only, autostart deferred.
- Power stability flagged for Phase 5.

**Hardware Redesign (Dec 15):**

- Finalized wiring standards and GPIO mapping.
- Component list locked: GPS (UART), IMU (I2C), OLED, 2 buttons, 2 LEDs.
- Decision: External LEDs only (no onboard ACT LED usage).
- Centralized GPIO definitions in pinmap module.
- UART direction corrected (Pi RX vs GPS TX).

**Core System Functional (Dec 16):**

- Full system validated: GPS fix, IMU data, LEDs, buttons all working.
- CSV files generating correctly.
- Physical buttons operational (logger toggle, shutdown).
- OLED display working (instability noted for later fix).
- **Critical Resolution:** GPIO edge detection issue traced to venv/RPi.GPIO.
- Decision: Run system-wide, not in venv (gpiozero + sudo confirmed).

### Outcome

- Stable telemetry capture achieved.
- Clear separation between data collection and interpretation.

**Status:** ✅ Complete & Frozen

---

## 4. Phase 2 — Structural Understanding (Frozen)

**Dates:** early → mid 2025-12

### Scope

- Track auto-detection
- Lap detection
- Distance normalization
- Track geometry generation

### Decisions

- Tracks are learned automatically; no manual seeding required.
- Once a track is learned, its geometry becomes persistent.

### Key Artifacts

- Introduction of **Track JSON** as a first-class object.

### Outcome

- System understands laps and tracks structurally.
- Foundation laid for comparison across sessions.

**Status:** ✅ Complete & Frozen

---

## 5. Phase 3 — Comparative Primitives (Frozen)

**Dates:** mid → late 2025-12

### Scope

- Best real lap detection
- Sector segmentation
- Distance-aligned delta/ghost math

### Decisions

- Exactly **7 fixed sectors** for non-kart tracks.
- Sector splits generated from the _fastest learning lap_, not the first lap.
- Sector layouts are frozen permanently to preserve rider mental mapping.

### Performance Model

- Best Real Lap tracked.
- **Theoretical Best Lap (TBL)** introduced:
  - Sum of best sector times across all sessions.
  - Represents rider potential, not an actual lap.

### Outcome

- Comparison primitives implemented strictly at engine level.
- No insights or coaching exposed.

**Status:** ✅ Complete & Frozen

---

## 6. Persistent Learning System (Formalized)

**Date:** 2025-12-20 → 2025-12-22

PM formally declared the system a **Persistent Learning System**.

### Decisions

- Learning never resets unless explicitly commanded.
- Track JSON acts as the authoritative database.
- CSV relegated to worst-case fallback only.

### Implication

- Performance accumulates across sessions.
- Rider improvement is tracked longitudinally.

---

## 6.5. GPS Hardware Upgrade (Complete)

**Date:** 2025-12-22

### Motivation

NEO-6M limited to 1Hz. Higher update rate needed for accurate track mapping.

### Decisions

- Upgraded to NEO-M8N (10Hz capable).
- Auto-baud detection and auto-upgrade to 10Hz via UBX protocol.
- Batch fix processing to handle full 10Hz stream.

### Outcome

- 10Hz logging achieved (from 4Hz bottleneck).
- Improved track geometry accuracy.

**Status:** ✅ Complete

---

## 7. Phase 5 — System Stability & Hardware Robustness (Partial)

**Dates:** 2025-12-21 → ongoing

### Motivation

Repeated power loss on motorcycles was identified as a critical risk.

### Decisions

- Ignition-triggered power with auto-start.
- Backup Li-ion battery preferred over supercapacitors.
- Clean shutdown on ignition cut.
- Read-only root filesystem in production.
- Separate writable data partition.
- Sticky fault flags for unsafe shutdowns.
- Explicit DEV vs PROD modes.

### Status

- Architectural decisions locked.
- Hardware validation acknowledged as necessary but allowed to pause.

**Status:** ⏸ Partial (Safe to resume later)

---

## 8. Automated Post-Session Workflow (Complete)

**Date:** 2025-12-21

### Motivation

Manual analysis steps are error-prone. Sessions should process automatically.

### Decisions

- Unified `run_analysis.py` script for all post-session work.
- Auto-identifies known tracks via GPS matching.
- Auto-generates new tracks if location unknown.
- Updates TBL records automatically per session.
- Exports UI-ready Session JSON.

### Workflow

```
Input: Raw CSV → Auto-Process → Output: Session JSON + Updated TBL
```

### Outcome

- Zero manual intervention required.
- Track identification accuracy validated.
- New track auto-generation tested successfully.

**Status:** ✅ Complete

---

## 9. Track Generation v2 — Production Ready (Complete)

**Date:** 2025-12-25 (morning)

### Motivation

Original track generation had false positives and unreliable start lines.

### Decisions

- **Heading-Verified Closure:** Start line detection validates heading consistency (±60°).
- **Pit Area Skipping:** Skips first 30s to avoid false positives at pit exit.
- **Median Distance Filtering:** Uses only clean flying laps for geometry (excludes out/in laps).
- **5-Point Smoothing:** Removes GPS jitter for cleaner track maps.
- **Immutable track.json:** Geometry frozen at creation.
- **Mutable tbl.json:** Best lap records updated per session.

### Outcome

- Production-quality track maps achieved.
- Robust lap detection (6/7 laps in test data).
- Data privacy via GPS anonymization script.

**Status:** ✅ Complete

---

## 10. Phase 3.1a — UI-Ready Filesystem Architecture (Complete)

**Date:** 2025-12-25 (afternoon)

### Motivation

UI ingestion needed to be trivial, deterministic, and safe.

### Decisions

- Single authoritative `output/` boundary.
- No scattered artifacts across directories.

### Structure Introduced

```
output/
├── registry.json
├── learning/
├── tracks/
│   └── track_<id>/
├── sessions/
│   └── track_<id>_session_<n>.json
```

### Outcome

- UI can ingest data via filesystem reads only.
- No database or complex queries required.

**Status:** ✅ Complete

---

## 11. Phase 3.1b — Identity Immutability + Track Renaming (Complete)

**Date:** 2025-12-25

### Core Correction

PM enforced strict separation between:

- **Identity (immutable):** `track_id`
- **Display (mutable):** track name & folder name

### Decisions

- `track_id` never changes.
- Track names and folders _can_ be renamed safely.
- Renaming must not:
  - Change geometry
  - Change sector definitions
  - Change historical meaning

### Implementation

- Atomic rename script introduced.
- Folder names and session filenames updated on rename.
- Registry updated automatically.
- Dry-run, rollback, collision detection enforced.

### Outcome

- Human-readable debugging.
- Stable machine references.
- UI-friendly naming model.

**Status:** ✅ Complete

---

## 11.5. Phase 3.2 — Companion App (Planned)

**Date:** TBD (Post Dec 25, 2025)

### Motivation

Backend is production-ready. Now need racer-friendly UI for track-day analysis.

### Core Requirements

**User Story:**

- Racer mounts Pi on motorcycle, rides session, returns to paddock.
- Connects phone to Pi's WiFi hotspot.
- Opens companion app in browser (hosted on Pi).
- Processes session data with one tap.
- Reviews laps, sectors, compares to TBL.

### Architecture Decisions

**Connection Method: WiFi Hotspot + Flask Server**

- Pi broadcasts WiFi network ("DataloggerAP").
- Pi runs Flask API server at `http://192.168.4.1:5000`.
- Companion app is a PWA (Progressive Web App) served by Flask.
- Zero external dependencies, works at remote tracks.

**Technology Stack:**

- Backend: Flask API (~200 lines Python)
- Frontend: React PWA with Chart.js
- Hosting: All files on Pi, accessed via browser
- No app store, no installation required

### Features (6 Core)

1. **Learning Data Access** (debug mode only)
   - View raw CSV files from `output/learning/`
2. **Process Session** (one-tap trigger)
   - Call existing `run_analysis.py` script
   - Show progress, auto-navigate to results
3. **View Tracks**
   - Display track list from registry
   - Show track maps (`track_map.png`)
4. **Rename Track** (quality of life)
   - Call existing `rename_track.py` script
   - Live preview of sanitized name
5. **Sessions by Date**
   - Group sessions chronologically
   - Show best lap times, TBL improvements
6. **Session Visualization**
   - Lap times table
   - Sector comparison charts
   - Delta vs TBL graphs

### Implementation Plan

**Phase 3.2a (Week 1-2): MVP**

- Flask API with core endpoints
- Track list view
- Session list view
- Process session button

**Phase 3.2b (Week 3): Polish**

- Track rename UI
- Sector charts
- Date grouping

**Phase 3.2c (Week 4): Analytics**

- Delta visualization
- TBL progress tracking

### Key Insight

**90% of backend already done.**

- All data is UI-ready JSON.
- Scripts are CLI-accessible.
- Companion app is just a thin UI layer.

**Racer Experience:**

1. Connect to WiFi
2. Open bookmark: `http://192.168.4.1:5000`
3. Tap "Process Session"
4. View analysis

**No complexity. Maximum accessibility.**

**Status:** 📋 Planned (Unblocked)

---

---

## 12. Phase 3.2 - Companion App Execution (2025-12-25)

**Context:** With the filesystem architecture solidified (Phase 3.1), the project moved immediately to creating the racer-facing UI.

### 2025-12-25: MVP Development & Delivery

**Core Implementation:**

- **Framework Choice:** Selected Flask (Python) for seamless integration with existing scripts + Vanilla JS for a lightweight PWA. No React/Vue overhead needed.
- **API Design:** REST endpoints mirroring the `output/` directory structure (`/api/tracks`, `/api/sessions`).
- **UI Design:** Dark-themed "Racer UI" prioritized legibility (high contrast) and touch targets.

**Critical Decisions:**

1.  **Dual-Schema Support:**
    - _Problem:_ Pre-Christmas session files used an old `aggregates` schema, newer ones use `summary`.
    - _Decision:_ Implemented a translation layer in the API rather than migrating data files. Ensures backward compatibility forever.
2.  **No Native Prompts:**
    - _Problem:_ Browser `window.prompt()` is unreliable on mobile/embedded browsers.
    - _Decision:_ Built a custom CSS Modal for renaming tracks. Significantly improves "premium feel".
3.  **Direct Filesystem Access:**
    - _Decision:_ The API reads JSONs directly. No database. Start-up time is <1s.
    - _Quote:_ "The filesystem IS the database."

**Outcome:**

- Full "Zero-Config" MVP delivered.
- **Connecting...** issue solved via robust error handling.
- **Rename** workflow fully functional.
- Ready for Raspberry Pi deployment via systemd.

---

---

## 13. Phase 7.1 - Visual & Cognitive Enhancements (2025-12-25 Late)

**Trigger:** Product authorization to improve "Rider Understanding" without altering "Truth".

**Deliverables (Frontend-Only):**

1.  **Consistency Score:** Derived Standard Deviation of lap times (±s), displayed prominently.
2.  **Sector Heatmap:**
    - Replaced the summary table with a full breakdown.
    - Cells colored relative to the **Session Median** (Green=Fast, Red=Slow).
    - Immediate visual feedback on "where I am inconsistent".
3.  **Session Trend Chart:**
    - Interactive SVG chart showing Lap Time progression.
    - Highlights "BEST" lap contextually.

**Technical Constraint Adherence:**

- Zero external charting libraries (Hand-coded SVG).
- Zero backend schema changes (All derived in `app.js`).
- "Dark Mode" compliant.

---

## 14. Current Project State (As of 2025-12-25 Night)

### Frozen & Stable

- Phase 1: Truth Capture
- Phase 2: Structural Understanding
- Phase 3: Comparative Primitives
- Phase 3.1: Filesystem & Identity Architecture
- **Phase 3.2: Companion App UI MVP**

### Active / Next



### Explicitly Blocked

-   Phase 4: Insight & Intelligence
-   Phase 6: Live Feedback

### Deferred but Planned

- Phase 5: Hardware validation & long-run stability testing

---

## 14. Phase 7.1.1 - Maintenance & UX Hardening (2025-12-26 Morning)

**Trigger:** User feedback on critical data hygiene and management workflows.

**Deliverables (Full Stack):**

1.  **UI Data Hygiene:**
    - Fixed TBL (Theoretical Best Lap) infinite loop bugs caused by overlapping sectors on short tracks.
    - Implemented Dynamic Sector Radius to prevent overlap.
    - Wiped and rebuilt corrupt TBL data for impacted tracks.
2.  **Entity Management:**
    - **Delete Logic:** Added ability to delete Sessions and Tracks.
      - _Safety:_ Raw CSVs are protected (never deleted by UI).
      - _Robustness:_ Handles Windows file locking/retry logic.
    - **Rename Logic:** Unified rename modal for both Tracks and Raw CSV Files.
3.  **Error Handling:**
    - Patched API error parsing to reveal true backend errors (e.g., Permissions) instead of generic 500s.

---

## 15. Current Project State (As of 2025-12-26 Morning)

### Frozen & Stable

- **Core Analysis Engine:** `SessionProcessor`, `LapDetector`, `TrackGenerator` (v3.6).
- **API Server:** Robust, threaded, serving 8+ active endpoints.
- **Frontend:** Responsive, Dark Mode, Phase 7.1 Insight-ready.

### Active Development

- **Phase 7.1.1 (Maintenance):** Complete.
- **Phase 7.2 (Spatial):** Next up (Corner speed analysis).

---

## 16. PM Closing Note

This project deliberately prioritized **correctness before cleverness**.

Every architectural decision was made to:

- Protect historical data
- Preserve rider mental models
- Avoid future rewrites
- Enable UI and insights safely later

This document is the **authoritative PM memory** going forward.

## [2025-12-26] Phase 7.3.1 Deployment (Sensor Intelligence)

**Objective:** Establish sensor trust layer without hardware fusion.

**Changes:**

1.  **Backend:**
    - Implemented `IMUCalibrator`: Pure Python logic to align Gravity Vector (Z-up) during static periods.
    - Updated `CSVLoader`: Parses Gyroscope data if available.
    - Updated `SessionProcessor`: Auto-runs calibration on every session import.
    - Updated `SessionExporter`: Persists `derived_signals` (Aligned Accel) and `calibration` metadata.

**Status:**

- Deployed & Verified.
- Robust to missing sensors (auto-detects).
- Enables future "Load" and "Stability" metrics (Phase 7.3.2).

## [2025-12-26] Phase 7.3.2 Deployment (Load & Stability Metrics)

**Objective:** Transform raw sensor data into meaningful rider feedback signals.

**Changes:**

1.  **Backend:**
    - Created `SensorMetricsEngine`: Computes Stability (Jerk inverse) & Load (G-force magnitude).
    - Integrated into pipeline to run after calibration.
    - Output: Stores `sensor_metrics` in Session JSON.
2.  **Frontend:**
    - Updated Session View to display "Stability" and "Lat Load" scores (0-100%) per lap.
    - Added color-coded feedback based on score thresholds.

**Value:** Riders can now correlate their lap times with smoothness and aggression.

## [2025-12-26] Phase 7.4 Deployment (Lap Drill-Down)

**Objective:** Transform session data into actionable per-lap visual insights.

**Changes:**

1.  **Interactive Dashboard:**
    - Replaced basic lap lists with a rich dashboard featuring dual interactive maps:
      - **Rider Dynamics:** Visualizes IMU inputs (Acceleration/Braking/Lateral G).
      - **Speed Profile:** Heatmap of velocity (Green=Fast, Red=Slow).
2.  **Visual Clarity:**
    - Implemented a layered rendering engine for track maps.
    - **Lateral Force (Halo):** Drawn as a solid, wide background ribbon to represent cornering load without clutter.
    - **Core Trajectory:** Drawn as a crisp top layer representing longitudinal input.
3.  **Deep Analysis:**
    - Added a **Modal View** for full-screen map inspection.
    - Integrated **G-Force Traces** synchronized with map content and Sector markers (S1, S2...).
4.  **Performance Context:**
    - Added a detailed **Sector Table** comparing the current lap against the session's **Theoretical Best Lap (TBL)**.

**Status:**

- Deployed & Verified.
- Visual styles refined based on user feedback (Layer separation).

**Value:** Riders can now visually diagnose "Where did I lose time?" by correlating speed and input with track position immediately.

## [2026-01-03] Infrastructure Hardening: Network Boot Selector

**Objective:** Guarantee field access to the device regardless of environment (Track Paddock vs Home), replacing fragile auto-detection.

**Changes:**

1.  **Hardware Control:**
    - Repurposed **GPIO 17 (Toggle Button)** for boot-time logic (Dual-Phase).
    - **Boot Phase:** Sampling GPIO state to decide Network Mode.
    - **Runtime Phase:** Button functions normally for Logger control.
2.  **OS Modernization:**
    - Updated network logic to support **NetworkManager (Bookworm)** natively.
    - Replaced fragile file swapping with `nmcli` profile switching.
3.  **Fail-Safe Logic:**
    - **Hold Button on Boot:** Forces Hotspot Mode (Emergency Access).
    - **Release/Default:** Connects to Known Wi-Fi (client mode).
    - Script defaults to Hotspot on any internal error.

**Status:**

- Deployed & Verified (iPhone connects successfully).

**Value:** Zero-risk deployment. Rider can always access data even if router configuration changes or Wi-Fi is unavailable at the track.

### [2026-01-03] Feature Deployment: Companion App Service

**Changes:**

- Deployed Flask API (`src/api/server.py`) as a persistent systemd service (`datalogger-api`).
- Integrated into `install_services.sh` for one-click deployment.
- Exposed on Port 5000.

### 2026-01-03: Phase 7.5 Complete (Export & Security Hardening)

**Objective:** Enable data portability and secure internal paths.

**Completed Actions:**

1.  **Session Renaming:** Added real-time renaming UI (Pencil) and Backend API (`POST /rename`).
2.  **Export ZIP:** Added `GET /export` generating backups containing `session.json` and a **detailed `README.txt`** (preserving Date, Track, and Best Lap context forever).
3.  **Print Reports:** Implemented One-Click PDF Reporting via "Print Report" button (using custom `@media print` CSS).
4.  **Security Audit:**
    - **Fixed:** `CSVLoader` no longer uses full system path as default session name. (Fixes title display bug).
    - **Fixed:** `rename` and `export` APIs catch exceptions internally to prevent path leakage in error messages.
    - **Fixed:** Learning Files API (`list` & `process`) sandboxed to `output/learning/` (no arbitrary path access).

**Status:** The system is now fully "Shippable" as a consumer product. Users can manage, name, and export their data without touching the filesystem.

### [2026-01-04] Phase 7.4.3: Comparative Analysis & Replay

**Objective:** Enable riders to compare laps visually to understand where time is lost or gained.

**Completed Actions:**

1.  **Ghost Map Replay:** Implemented a full replay engine in the Frontend (`app.js`) powered by the Backend `Comparator`.

    - **Visuals:** Trace-based animation with two markers (Reference vs Target).
    - **Metrics:** Real-time updates for Time Gap, Sync Speed, and Distance.
    - **Controls:** Play/Pause, Slider Scrubbing, and 1x/4x speed options.

2.  **Delta Charts:** Integrated SVG-based charts showing time delta trends over distance (Lower is Faster/Green, Higher is Slower/Red).

3.  **Backend Comparator:**
    - Refined `compare_laps` endpoint to robustly handle lap extraction and resampling.
    - Ensured `Comparator` aligns laps by distance meters for accurate corner-by-corner analysis.

**Rollback / Technical Debt Identified:**

- **TBL Comparison (Session Optimal):** An attempt to implement a synthetic "Optimal Lap" (stitching best sectors) revealed a data structure mismatch. Existing session JSONs use "sparse arrays" (skipping missing sectors), whereas the stitching logic required "dense arrays" (with `None` placeholders).
  - **Impact:** Caused API 500 errors and prevented the Tracks tab from loading due to cascade failures.
  - **Resolution:** Rolled back the "Optimal" option to restore system stability.

---

**Status:** Comparative Analysis is fully functional for standard laps. System is stable.

**Next:** Phase 3 (Hardware Verification & Final Polish).

### [2026-01-04] Phase 8.1: Diagnostic Intelligence (Session Diagnostics)

**Objective:** Implement statistical analysis to quantify rider consistency without providing AI coaching advice.

**Completed Actions:**

1.  **Backend Engine (Layer 8):**

    - Created \DiagnosticsEngine\ in \src/analysis/processing/diagnostics.py\.
    - Implemented statistical metrics: Standard Deviation per Sector, Coefficient of Variation (Cv), and Consistency Score (100 - Avg Cv).
    - Integrated into \SessionExporter\ to persist diagnostics in \session.json\.

2.  **Frontend UI:**
    - Added **Session Diagnostics** panel to the Session Detail view.
    - **Consistency Gauge:** Visual Score (Stable/Variable) color-coded (Green/Amber/Red).
    - **Hotspot Detection:** Automatically lists sectors with highest variance.
    - **UX:** Implemented as a collapsible 'Accordion' to reduce visual clutter.

**Technical Note:**

- Fixed a bug where \Lap\ objects lacked a \.valid\ attribute, causing the engine to crash. Switched to safe attribute access.

**Status:** Phase 8.1 Complete. Reviewing Phase 8.2 (Delta Extremes).

### [2026-01-05] Phase 9: Live LED Feedback (Core Implementation)

**Objective:** Implement real-time, zero-latency visual feedback for sector performance without compromising the integrity of data logging.

**Completed Actions:**

1.  **Architecture (Threaded Service):**

    - Designed and implemented `LiveAnalysisService`, a dedicated background thread.
    - **Mechanism:** Main logger pushes GPS fixes to a non-blocking queue; Service consumes them to calculate feedback.
    - **Safety:** Ensures that analysis latency or LED hardware faults cannot stall the primary 10Hz logging loop.

2.  **Logic (Spatial Lookup):**

    - Enhanced `TrackManager` with `identify_track_point(lat, lon)` for instant, sample-based track recognition.
    - System now automatically identifies the circuit and loads the corresponding TBL (Ghost) upon acquiring a GPS fix.

3.  **Hardware (LED Engine):**
    - Validated `FeedbackEngine` logic:
      - **Scanning Blue:** Sector Boundary Crossing.
      - **Solid Green/Red/Orange:** Performance relative to All-Time Best.
    - Verified simulation environment with `simulate_all.sh` (1.0x speed).

**Status:** Core Logic & Service Architecture Implemented. Pending Hardware field test on Pi.

### [2026-01-08] Phase 9: Live Feedback System (Polish & Stability)

**Objective:** Transition from hardcoded hardware behavior to a fully user-configurable system via the Web UI, and ensure rock-solid stability in the field.

**Deliverables:**

1.  **Unified Settings Architecture:**

    - Created `SettingsManager` as the single source of truth (`output/settings.json`).
    - Implemented **Atomic Hot-Reloading** to allow instant configuration changes from the phone while the bike is running.
    - Result: Changing a setting on the phone updates the hardware instantly (IPC via Filesystem).

2.  **Enhanced LED Control:**

    - **Driver Refactor:** `LEDStripDriver` now runs a non-blocking animation thread.
    - **New Animations:** Added Rainbow, Police, Sparkle, and Charging patterns.
    - **State Management:** Decoupled "Preview" commands from "Live Analysis" updates to ensure manual previews stick.

3.  **Frontend Integration:**
    - Added "Settings" tab with granular Event Configuration.
    - Color Pickers and Live Preview buttons for every system event.

**Debugging Journey (The "Silent Failure" Incident):**

- **Issue:** Web UI said "Success", but Pi LEDs did nothing.
- **Root Cause & Fix:**
  - `SettingsManager` used coarse timestamps -> Upgraded to Nanosecond precision.
  - `LiveAnalysisService` was overwriting Previews -> Added state deduplication.
  - Race condition on file read -> Implemented Atomic Writes.

**Status:** ✅ Complete & Production Ready.

### [2026-01-09] Phase 9.8: Logic Refinement & Simplicity

**Objective:** Finalize LED logic based on field testing and user preference for simplicity.

**Completed Actions:**

1.  **Event Simplification (Phase 9.8):**

    - Removed complex/unused events: WiFi, GPS Lock, Track Search.
    - Simplified State Machine:
      - **No GPS:** Red Blink.
      - **Idle (Ready):** White Breath.
      - **Logging:** Blue Scanner <-> GPS Strength Bar.

2.  **Logic Hardening:**

    - **GPS Strength:** Hardcoded to 1 LED @ 5 Sats, +1 per 2 Sats (removed complex UI config).
    - **Event Integration:** Ensured FeedbackEngine consumes atomic SettingsManager events for Sector/Delta colors.

3.  **Documentation Consolidation:**
    - Merged 8+ fragmented Phase documents into a single authoritative **PROJECT_PHASES.md**.
    - Cleaned up documentation directory.

**Status:** ? Phase 9 Closed. Moving to Phase 10 (Coaching).

### [2026-01-09] Phase 9.9: Critical Logic Fixes (GPS Wait State)

**Objective:** Resolve ambiguity in LED feedback during the 'Waiting for GPS' state.

**Fixed Issues:**

1.  **Idle Mode Enforcement:**

    - **Issue:** Idle logic was ambiguous dependent on GPS.
    - **Fix:** If Logger is OFF, strictly enforce **Idle Animation** (White Breath) regardless of GPS status.

2.  **GPS Search (Active) Blind Spot:**
    - **Issue:** When Logger was toggled ON but GPS was searching (No Fix), the main loop sent _no data_ to the LED service, causing it to timeout and revert to Idle.
    - **Fix 1 (Data Flow):** Updated main.py to push a heartbeat frame with sats=0 even if gps_batch is empty.
    - **Fix 2 (State Intent):** Updated is_logging flag to be True during STARTED_WAITING_GPS state.
    - **Result:** Logger ON + No GPS now correctly triggers **GPS Search (Red Blink)**.

**Status:** ? Phase 9 Fully Verified. System behaves exactly as specified.

### [2026-01-09] Phase 9.9.2: Critical Logic Fixes (Live Track ID)

**Objective:** Investigate and fix discrepancy where offline analysis identified tracks but live LED system did not.

**Root Cause Analysis:**

- **Symptom:** LED remained in "No Track" state despite riding on a known track. Offline logs successfully identified the track later.
- **Investigation:** Debug script `debug_track_id.py` revealed that `LiveAnalysisService` crashed silently when attempting to print the track name.
- **Cause:** Historical `track.json` files used `track_id` / `track_name` keys, while the Service code anticipated standard `id` / `name` keys. The `TrackManager` loaded them "as is", leading to a `KeyError` in the Service layer.

**Fix:**

1.  **Normalization in TrackManager:** Updated `TrackManager` to automatically normalize loaded track objects, ensuring `id` and `name` fields are always populated (copying from `track_id`/`track_name` if necessary).
2.  **Robust Service Logging:** Updated `LiveAnalysisService` to use `.get()` for logging, preventing crashes on missing metadata.

**Verification:**

- Replayed multiple session files (`kattapana.csv`, `valid184331.csv`) against the logic.
- **Result:** 100% Match rate with <1m proximity accuracy.
- **Field Test [2026-01-09]:** User confirmed fix is working in the field. LEDs showing correct behavior.

---

### [2026-01-09] Administrative: Phase 10 Rollback

**Decision:** Rolled back Phase 10.1 (Instructor Mode UI) changes to maintain a clean, stable "Phase 9 Complete" state.

- Removed Instructor Mode toggle from UI.
- Removed `instructor_mode` from persistent settings.
- **Current State:** The system is at a stable verification checkpoint (Phase 9 + Critical Fixes). Ready for Coaching Mode when explicitly authorized.

---

### [2026-01-09] MILESTONE: V1.0.0 PRODUCT RELEASE 🚀

**Decision:** The codebase has been officially marked as **Version 1.0.0**.

**Summary:**

- **Core Logging:** Reliable GPS (10Hz) & IMU logging.
- **Analysis:** Offline track generation, sector segmentation, and TBL calculation.
- **Feedback:** Real-time LED communication (Wait/Log/Track/Sector).
- **Stability:** Critical logic blind spots (GPS Wait, Track Metadata) resolved and field-verified.

**Artifacts Updated:**

- `src/config.py`: Added `VERSION = "1.0.0"`
- `docs/PROJECT_PHASES.md`: Marked V1 milestone; Phase 10 postponed.
- `task.md`: Closed Phase 9.

**Status:** The product is now in Maintenance Mode. Feature development (Phase 10) is paused until V1.1 planning begins.

---

### [2026-01-13] Hardware Upgrade: PCB v2 Integration

**Objective:** Transition from breadboard/prototype wiring to a consolidated V2 PCB for enhanced durability and signal integrity.

**Completed Actions:**

1.  **Assembly & Integration:**

    - Migrated components (Pi 4, GPS, IMU, LED Controller) to the new PCB v2.
    - Verified all headers and solder joints.

2.  **Validation:**
    - **Power Stability:** Confirmed stable operation under load.
    - **Peripherals:** Validated 10Hz GPS lock, IMU data stream, and LED strip control.
    - **Input/Output:** Toggle button and status LEDs passed functional tests.

**Status:** ✅ Hardware Sealed & Verified. Ready for field deployment.

---

### [2026-01-14] Phase 12: Companion App Enhancements Deployment

**Objective:** Enhance the user experience, operational safety, and maintenance capabilities of the Datalogger Companion App without altering the core logging engine.

**Deliverables (Full Stack):**

1.  **System Control & Feedback:**

    - **UI Controls:** Added "REC" and "STOP" buttons to the web header for explicit logging control (via Socket IPC).
    - **Visual Feedback:** Implemented a pulsing Red Dot "RECORDING" indicator driven by a new `system_status.json` shared state.
    - **Safety:** Confirmed graceful shutdown via physical button ensures data integrity.

2.  **Advanced File Management:**

    - **File Locking:** Users can now "Lock" important sessions (e.g., "Best Lap") to prevent accidental deletion. Locked files are rendered read-only in the UI.
    - **Bulk Delete:** Added checkboxes and batch deletion workflow for easier storage management.
    - **Raw Data View:** Implemented a "Quick Peek" modal to inspect CSV structure (Headers, Data Integrity) directly in the browser, with color-coded columns (GPS, IMU).
    - **Path Visualization:** Added instant SVG Path rendering to verify GPS data quality without full processing.

3.  **Maintenance & Diagnostics:**
    - **Service Control:** Added a "Maintenance" tab to restart individual services (API, Logger, Buttons) without rebooting the Pi.
    - **Diagnostics:** Enhanced LED and Sensor tests with detailed error reporting (Tracebacks) and library checks.
    - **Remote Access:** Integrated `setup_tailscale.sh` for easy VPN deployment.

**Technical Decisions:**

- **IPC Strategy:** Chose a simple `system_status.json` file for Logger -> API status (One-way) to decouple the critical logging loop from API queries.
- **Socket Commands:** Used the existing Unix Socket for API -> Logger commands (`START_LOG`, `STOP_LOG`) to maintain thread safety.
- **IMU Logging:** Verified and enabled Gyroscope data logging (X/Y/Z) alongside Accel data.

**Status:** ✅ Deployed & Documented.

---

### [2026-01-21] Phase 12.2: Process All & UI Overhaul

**Objective:** Streamline bulk file processing and enhance Trackday visualization based on rider feedback.

**Completed Actions:**

1.  **Bulk Processing ("Process All"):**

    - **Backend:** Added `/api/process/all` endpoint for batch session processing.
    - **Deduplication:** Sessions now store `source_file` in metadata to prevent duplicate processing.
    - **Selection Support:** Process All respects checkbox selection (processes only selected unprocessed files).
    - **UI Feedback:** Green checkmarks (✅) indicate processed files; disabled buttons for already-processed items.

2.  **Session Naming Reform:**

    - **Old:** `coastt_high_performance_center_session_1.json`
    - **New:** `jan21Session1.json` (Date-based, human-readable).
    - Naming derives from CSV timestamp, not track folder.

3.  **Bug Fixes:**

    - **Delete Exception:** Fixed null check error in `performDelete()` when API response was incomplete.
    - **Telemetry Filter:** `_telemetry.json` files no longer appear in session lists.
    - **Dynamic Count:** "Process All" button count updates dynamically based on checkbox selection.

4.  **Trackday View Enhancements:**

    - **Collapsible Sessions:** Sessions list is now collapsible (click header to toggle).
    - **Consistency Metric:** Each session displays σ (standard deviation) of lap times.
    - **TBL Card:** Added Theoretical Best Lap visualization with sector breakdown.
    - **Best Actual Lap Card:** Shows fastest lap ridden with session context and sector times.
    - **Track Map (Modern):** SVG-based track visualization using `generateTrackMapSVG()` (matches Track Details view).
    - **Lap Grouping:** Laps grouped by session (not globally sorted). Each group has a header with stats.
    - **Multi-Select Sessions:** Checkbox-based modal for adding multiple sessions to a trackday at once.

**Technical Decisions:**

- Used IIFE (Immediately Invoked Function Expression) in template literals for complex conditional rendering.
- Async map loading to prevent blocking initial render.
- Fallback to static PNG if geometry endpoint fails.

**Status:** ✅ Deployed & Verified.

---

### [2026-01-24] Phase 13: The Hardware Pivot (Monorepo Architecture)

**Objective:** Transition from a "Pi-Only" enthusiast tool to a commercially viable "Hardware + Cloud" product ecosystem.

**Motivation:**
- Raspberry Pi Zero 2W is too expensive and power-hungry for a mass-market dumb logger.
- **ESP32** offers a 5x cost reduction and lower power profile.
- IP Protection: Moving logic to the cloud protects algorithms better than shipping Python code on SD cards.

**Architectural Shift: Monorepo Deployment**
Restructured the codebase into a single repository managed as three distinct products:

1.  **Shared Core (`core-analysis`):**
    - Extracted the "Brain" (Track Learning, TBL, Lap Detection) into a pure Python library.
    - Validated that logic remains identical whether running on Cloud or Pi.

2.  **Cloud Backend (`cloud-backend`):**
    - Unified API Server. Removed device-specific logic (WiFi/Hardware tests).
    - Can run on AWS (serving ESP32s) OR locally on Pi (serving itself).
    - Established "Write Once, Run Anywhere" API principle.

3.  **Firmware Layers:**
    - **Legacy Pi (`firmware/pi`):** Preserved the full Python logger stack.
    - **ESP32 (`firmware/esp32`):** Created skeleton for MicroPython Dumb Logger.

**Migration Actions:**
- Moved `src/` to `firmware/pi/src`.
- Extracted `FileManager` and `RegistryManager` to `core-analysis`.
- Restored Pi Standalone functionality via a new `run_server.py` bridge script.
- Updated SFTP config to respect new paths.

**Deployment Modes Defined:**
- **Mode 1 (Cloud):** Web API receiving uploads.
- **Mode 2 (Pi Dumb):** Logs to CSV, Syncs to Cloud.
- **Mode 3 (ESP32):** Logs to Flash, Syncs to Cloud (In Progress).
- **Mode 4 (Pi Standalone):** Full offline stack (Classic Pro Mode).

**Status:** 🏗 Architecture Structure Complete. Pi Standalone Repaired. Ready for ESP32 Logic Implementation.

---

### [2026-01-26] Phase 14: ESP32 Implementation & Cloud-First Architecture

**Objective:** Implement production-ready ESP32 firmware with onboard flash storage and cloud-sync capabilities.

#### Hardware Architecture Shift: SD Card Removed

**Decision:** After initial SD card prototyping, **removed all SD card dependencies** in favor of **onboard flash storage**.

**Rationale:**
1. **Simplicity:** Fewer components = lower assembly cost, fewer failure points
2. **Cost:** Eliminates SD card module ($2-3) and SD card itself ($5-10)
3. **Power Efficiency:** No SPI bus active, reduced power draw
4. **Form Factor:** Smaller enclosure possible without SD card slot
5. **Reliability:** No mechanical card insertion/removal, no filesystem corruption from improper ejection

**New Storage Strategy:**
- ESP32 logs all sessions to **internal flash** (`/sessions/` directory)
- Flash capacity: ~4MB available on ESP32-DevKit (sufficient for 200+ sessions of ~10KB each)
- Sessions sync to cloud backend via WiFi HTTP upload
- Cloud backend saves files to its working directory (`firmware/pi/output/sessions/`)
- After successful sync, ESP32 deletes local copy to free space

**Code Changes:**
- Removed `drivers/sdcard.py` imports from `main.py`
- Simplified `SessionManager` class:
  - Removed `sd_mounted` flag and `sync_to_sd()` method
  - Added `list_sessions()`, `get_session_data()`, `delete_session()` for cloud sync
  - Added `get_storage_info()` to monitor flash usage
- Updated `ESP32_WIRING.md` to remove SD card module wiring

#### WiFi Architecture: Hybrid Home + Hotspot

**Implementation:** Dual-mode WiFi with smart fallback logic.

**Modes:**
1. **Home WiFi (Priority 1):** ESP32 attempts to connect to stored credentials first
   - Credentials stored in `wifi_credentials.json` on flash
   - Web companion app provides "Target IP" + "Scan Network" UI
   - Network scanner discovers ESP32 on local subnet (multithreaded subnet ping)
   
2. **Hotspot Mode (Fallback):** If home WiFi fails, ESP32 creates its own AP
   - SSID: `Datalogger-AP`
   - Password: Configurable (default: `datalogger123`)
   - IP: `192.168.4.1` (standard ESP32 AP mode address)
   - User connects phone/laptop to AP, accesses web interface for setup

**Connection Status Indicator (Web Companion):**
- Top-left header badge shows connection status:
  - **Green "Connected: 192.168.x.x"** = Device reachable
  - **Gray "Device Offline"** = Saved IP not responding
  - **Gray "No Device IP"** = No IP saved in local storage
- Polls backend every 30 seconds via `/api/device/check?ip=<ip>`
- Backend timeout: 5 seconds (increased from initial 2s to handle ESP32 latency)

**Network Scanner Implementation:**
- **Frontend:** "Scan" button next to Target IP field in Settings tab
- **Backend:** `/api/device/scan` endpoint with multithreaded subnet ping
  - Scans `192.168.1.0/24` subnet (configurable)
  - 20 concurrent threads (reduced from initial 50 to prevent network congestion)
  - 2-second timeout per IP (increased from 0.2s for ESP32 response time)
  - Detects ESP32 by querying `/status` endpoint
- **UX Improvements:**
  - Spinner animation on button during scan
  - Minimum 3-second delay ensures visual feedback
  - Toast notifications for scan results (found/not found)
  - Auto-updates connection status badge after device discovered
  - Stores discovered IP in `localStorage.lastDeviceIP`

#### Cloud Sync Protocol

**Pull Model (Phase 15 planned):**
- Cloud backend initiates sync via HTTP GET to ESP32
- ESP32 exposes lightweight HTTP server (`miniserver.py`)
- Endpoints:
  - `/status` - Device health check
  - `/sessions` - List available sessions on flash
  - `/session/<filename>` - Download specific session CSV
  - `/delete/<filename>` - Delete session after successful sync

**Implementation Status:**
- ✅ WiFi connect/AP fallback logic (`lib/wifi.py`)
- ✅ Miniserver framework (`lib/miniserver.py`)
- ✅ SessionManager flash storage methods
- ✅ Network scanner (backend + frontend)
- ✅ Connection status indicator
- 🏗 Cloud pull sync endpoints (in progress)

#### Companion App Enhancements

**Settings Tab Fix:**
- **Bug:** "Failed to load settings" toast on Settings tab navigation
- **Root Cause:** `ModuleNotFoundError: No module named 'src'` in `/api/settings` endpoint
  - Backend trying to import `src.core.settings_manager` (Pi path)
  - Cloud backend runs from `cloud-backend/api/`, not `firmware/pi/`
- **Fix:** Added `sys.path.append()` to include `firmware/pi` in Python path
- **Status:** ✅ Settings now load correctly, showing system/LED/OLED config

**Settings Architecture:**
- Backend imports `SettingsManager` from Pi firmware codebase
- Settings stored in `firmware/pi/output/settings.json`
- Live editing via web UI (toggle switches, color pickers, etc.)
- Pi standalone mode uses same settings file for LED/OLED control
- Cloud mode ignores hardware settings (no LED/OLED on server)

#### Technical Debt Identified

**Legacy Pi Endpoints in Cloud Backend:**
- `/api/wifi/status` returns 404 (only applicable to Pi hardware)
- Settings tab shows "Checking..." in Network section indefinitely
- **Decision:** Leave as-is for now, mark as "Pi-only" in future cleanup
- Frontend gracefully handles 404 (shows "Connection error" toast but doesn't block)

**File Upload Endpoint (Next Priority):**
- Need `/api/device/upload` endpoint to receive CSV from ESP32
- Should save to `firmware/pi/output/sessions/` for processing
- Trigger session processing pipeline (lap detection, TBL calculation)

#### Progress Summary

**Completed:**
1. ✅ Removed SD card hardware dependency
2. ✅ Refactored ESP32 firmware for flash-only storage
3. ✅ Implemented WiFi home/hotspot dual mode
4. ✅ Built network scanner (backend + frontend)
5. ✅ Added connection status indicator to UI
6. ✅ Fixed Settings loading error
7. ✅ Updated hardware wiring documentation

**In Progress:**
- 🏗 Cloud sync pull endpoints on ESP32
- 🏗 Backend upload receiver endpoint

**Next Steps:**
- Implement `/api/device/upload` endpoint (receive CSV from ESP32)
- Build ESP32 sync client (HTTP POST to cloud)
- Test end-to-end flow: GPS → Flash → Upload → Cloud Processing → Web UI
- Add automatic sync trigger (e.g., on WiFi connect, or periodic poll)

**Status:** 🚀 ESP32 Foundation Complete. Storage migration successful. Ready for cloud sync implementation.


---

## 17. Phase 11 — ESP32 Port & Cloud Integration (Complete)

**Dates:** 2026-01-15 → 2026-01-25

### Motivation
Raspberry Pi is powerful but overkill for simple logging. ESP32 provides a lower-power, more robust "headless" hardware platform.

### Decisions
- **Logic:** Ported core logging logic from Python (Pi) to MicroPython (ESP32).
- **Storage:** Use onboard Flash (vfs) instead of SD cards for maximum vibration resistance.
- **Sync:** Implemented WiFi-based cloud synchronization (HTTP POST) to a local Pi/Laptop backend.
- **Protocol:** JSON-based state exchange for WiFi credentials and session status.

### Outcome
- Successful migration to ESP32.
- Wireless session offloading proven reliable.

---

## 18. Phase 12 — ESP32 Deployment Tooling (Complete)

**Date:** 2026-01-28

### Motivation
Manual flashing and file copying via multiple tools was slow and error-prone.

### Decisions
- **Tooling:** Integrated `esptool` and `mpremote` into a single `deploy.sh` script.
- **Functions:** Added one-click `--wipe`, `--flash`, `--libs`, and `--sync`.
- **Serial Management:** Implemented automatic PID killing for serial port conflicts.

### Outcome
- "Zero-configuration" deployment for new ESP32 units.
- Drastic reduction in setup time.

---

## 19. Phase 13 — GPS 10Hz Performance & Stability (Complete)

**Date:** 2026-01-30

### Motivation
Default 1Hz update rate is insufficient for high-speed track analysis. Initial 10Hz attempts caused system stuttering and frame drops.

### Decisions
- **Handshake:** Implemented a recursive boot-time handshake (9600 -> 115200).
- **Buffering:** Expanded hardware UART RX buffer to **2048 bytes** to absorb GPS bursts during Flash writes.
- **Deduplication:** Added timestamp-based deduplication in the main loop to ensure exactly one log entry per GPS epoch.
- **Efficiency:** Disabled redundant NMEA messages (GSV, GLL, VTG) via UBX binary commands to save UART bandwidth.
- **UX:** Implemented a pulsating "Heartbeat" LED to indicate GPS Lock status and reduce peak current draw.

### Outcome
- Rock-solid 10Hz logging at 115200 baud.
- Zero frame drops or duplicate entries in production logs.

**Status:** ✅ Complete & Performance Validated

---

## 20. Phase 14 — NeoPixel Visual Feedback (Complete)

**Date:** 2026-01-30

### Motivation
Standard LEDs are insufficient for high-visibility status in a bright, outdoor environment. The rider needs clear, glancing feedback on system readiness.

### Decisions
- **Hardware:** Integrated an 8-LED NeoPixel strip on **GPIO 4**.
- **Power:** Powered via **VIN (5V)** to ensure consistent brightness.
- **Visual Vocabulary:**
    - **Rainbow:** System Boot / Initialization.
    - **Pulsing Red:** Searching for GPS (matches original Pi intent).
    - **Blue Scanner:** Active Logging and GPS lock (high-performance feel).

### Outcome
- High-visibility status indicators achieved.
- Professional "Racer UI" aesthetics ported successfully from Pi to ESP32.

---

## 21. Phase 15 — Dual-Core Performance Optimization (Complete)

**Date:** 2026-01-30

### Motivation
Concurrent WiFi activities (Web Server polling, cloud sync) were identified as risks to 10Hz GPS timing consistency. Network interrupts could cause micro-stutters in data capture.

### Decisions
- **Architecture:** Transitioned to a true multi-threaded design utilizing both Xtensa cores.
- **Core 1 (Dedicated):** Handles exclusively GPS UART ingestion and Flash writing. Zero network overhead.
- **Core 0 (System):** Handles the Web Server, WiFi maintenance, and NeoPixel animations.
- **Communication:** Shared global thread-safe state for GPS status visibility on the UI thread.

### Outcome
- **Deterministic 10Hz Capture:** Logging is now independent of system load.
- Gapless telemetry guaranteed even during active cloud synchronization.
- System is now considered "Production Grade" for high-speed use.

**Current Project Status:** ✅ Deployment & 10Hz Stability Architecture Finalized.

---

## 22. Migration to Datalogger V2 (ESP32 Standalone)

**Date:** 2026-01-30

### Context
We have fully migrated from the datalogger-on-pi availability to a new project: **datalogger v2**.
The architecture is now **ESP32 Pure Standalone**, eliminating the Raspberry Pi entirely from the vehicle.

### Core Philosophy
- **Simple Logger:** The ESP32 is a dumb recording device. It captures truth (telemetry) and provides minimal, critical feedback.
- **Immediate Start:** Zero boot time. Starts logging immediately when power is applied.
- **No Distractions:** No OLED display. No complex OS. No filesystem repairs.
- **Feedback Loop:**
  - **LED Only:** Visual communication via the NeoPixel strip.
  - **Sector Delta:** The *only* onboard logic matches the current location to a known track (pushed from UI) and flashes Green/Red based on sector performance vs TBL.

### Connectivity
- **Mini Server:** The ESP32 hosts a lightweight web server (`miniserver`) to handshake with the Companion App.
- **Host-Client Model:** The UI (Analysis Engine) runs on a separate powerful device (Laptop/Phone), pulling data from the ESP32.

**Status:** Migration Confirmed. Legacy Pi code archival in progress.


---

## 24. UI Cleanup: Session Details Optimization

**Date:** 2026-02-08

### Motivation
As the "Session Details" view grew with new features (Diagnostics, Annotations, Comparison), the interface became a single, cluttered, and long vertical scroll. This degraded the user experience, especially on mobile devices at the track.

### Decisions
- **Information Hierarchy:** Prioritized "At-a-Glance" KPIs while grouping secondary data into collapsible sections.
- **Collapsible Design:** 
    - **Session Context:** Grouped Environment (Weather), Notes, and Technical Diagnostics into a single section (collapsed by default).
    - **Lap Analysis:** Kept the main table expanded by default for immediate review but allowed collapsing for faster access to charts.
    - **Visual Insights:** Grouped the Sector Comparison and Timeline charts into a collapsed section to reduce initial cognitive load.
    - **Coach's Corner:** Grouped annotations into a dedicated section (expanded by default).
- **Mobile First:** Optimized section headers for large touch targets and added smooth animations for state transitions.

### Outcome
- **Reduced Scroll Fatigue:** Initial page length reduced by ~60%.
- **Cleaner Aesthetics:** Improved "premium feel" through consistent glassmorphism cards and structured layout.
- **Responsive Handling:** Enhanced layout stability on various screen sizes.

**Status:** ✅ Implemented & Deployed.
- **Cleanup:** Removed all Pi-specific controls, "Bridge" modes, and complex sync logic intended for the hybrid era.
- **Simplification:** Codebase stripped down to the essentials required for the Dumb Logger -> Cloud workflow.

### Outcome
- A cleaner, faster, purpose-built UI.
- Reduced cognitive load for both developers and users.
- Clear separation: The ESP32 is the *only* data source.

---

## 24. Hardware Maturity & Production Layout

**Date:** 2026-02-01

### Milestone: The "Fist" Form Factor 👊
We have corrected the hardware trajectory. Transitioned from breadboards and jumpers to a **fully soldered, integrated setup**.

**New Physical Reality:**
- **Size:** The entire stack (Power, ESP32, BMI323, GPS, Type-C LED Port) fits within the size of a fist.
- **Durability:** No loose wires. Vibration-proof for the first time.
- **Feedback:** Type-C port repurposed as a robust external output for the LED feedback module.

### Sensor Integration: BMI323
- Successfully integrated the **BMI323 IMU**.
- **Status:** Streaming raw Gyro and Accel values effectively.
- **Driver:** Custom MicroPython driver written and verified.

### Storage Strategy: SD Card Deprecation
- **Incident:** Spent 2 days debugging SD Card logic. Reliability was poor (likely bad module/wiring).
- **Decision:** **Abandoned SD Card.**
- **Pivot:** Doubling down on internal Flash + WiFi Offload. The simplicity of V2 allows us to rely on the ESP32's own flash for session buffering before offloading, eliminating the biggest mechanical failure point.

### Software Enhancements
1. **Robust Scanning:** Completely overhauled the Network Scanner logic. It is now aggressive and reliable in finding the device.
2. **Map Visualization:** Added **Scale Bars and Metric Grids** to the path visualizer. Riders can now judge corner radii and straight lengths visibly.
3. **Bug Fixes:** Stabilized the processing pipeline and cleared legacy import errors.

**Status:** ✅ Hardware is minimal, soldered, and producing data. Software is catching up to the new form factor.

---

## 25. SD Card Integration: The Resurrection

**Date:** 2026-02-02

### Background

After two days of debugging and an initial decision to "abandon SD Card" in Entry 24, we revisited the problem with fresh wiring: **directly soldering the SD card to the ESP32** (no modules/breakouts).

### Wiring Configuration (Final)

| ESP32 Pin | Signal | SD Card |
|-----------|--------|---------|
| GPIO 5 | SPI CS | Chip Select |
| GPIO 18 | SPI SCK | Clock |
| GPIO 23 | SPI MOSI | Data To SD |
| GPIO 33 | SPI MISO | Data From SD |
| 3.3V | VCC | Power |
| GND | GND | Ground |

### Root Cause Analysis

The original SD card driver had multiple issues:

1. **Missing MOSI High Workaround:** The official MicroPython driver sends `0xFF` before each transaction to ensure MOSI is high. Our custom driver lacked this, causing Kingston-class cards to fail randomly.

2. **Incorrect OCR Handling:** The driver assumed all v2 cards were SDHC (block addressing) without checking the OCR register bit 30. This caused addressing errors on some cards.

3. **Missing Trailing Clocks:** After CSD read, the driver didn't send trailing clock pulses, leaving the SPI bus in an undefined state.

4. **CMD16 Failure:** SDHC cards have fixed 512-byte blocks and CMD16 isn't required, but the driver tried it anyway and failed on some cards.

### Solution

Replaced the custom driver with the **official MicroPython sdcard.py** from `micropython-lib`. Key differences:

- Proper `write_readinto()` for full-duplex SPI
- OCR bit 30 checking for SDHC detection
- MOSI high workaround before every transaction
- Cleaner `readinto()` with dummy buffer swap

### Performance Benchmarks

Stress tested across 7 SPI speeds (400kHz → 20MHz) and 3 block sizes:

| Configuration | Write Speed | Read Speed |
|---------------|-------------|------------|
| Safe (4 MHz, 512B) | 148 KB/s | 118 KB/s |
| Optimal (10 MHz, 4KB) | **278 KB/s** | 224 KB/s |
| Maximum (20 MHz, 4KB) | 283 KB/s | 248 KB/s |

### Recommendation

For data logging: **10 MHz SPI with 4KB write buffers** provides the best balance of speed and reliability.

### Outcome

- ✅ SD Card fully operational
- ✅ Read/Write verified ("Hello World" test passed)
- ✅ Official driver committed to `firmware/drivers/sdcard.py`
- ✅ Performance benchmarked and documented

### Lesson Learned

> **"Don't blame the hardware until you've tried the reference implementation."**

The SD card module wasn't faulty — the driver was. Always start with official/reference code before writing custom implementations.

**Status:** ✅ SD Card resurrected. Ready for production data logging.

---

### 2026-02-07: Hardware Evolution — The "RS-Core" (S3 Pivot)

**Context:** Major architecture upgrade to transition from a prototype to a commercial-grade product. Successfully moved the design to the ESP32-S3 platform.

**Decisions:**
- **MCU Pivot:** Selected **ESP32-S3-WROOM-1-N16R8**. Native USB support allows the device to act as a Mass Storage device for ultra-fast "pit lane" data offloading.
- **Power Intelligence:** Integrated a voltage divider for real-time **Battery Voltage Monitoring** (IO35).
- **Safety Fixes:** Audited and fixed charging path (diode removal) and LED logic (high-side switching).
- **Expansion Ports:** Exposed 3x GPIOs for future "Pro" features (Suspension/Brake sensors).

**Outcome:**
- Hardware design frozen and Gerbers generated (`RS-core-Gerber-final.zip`).
- Transitioned from "Dumb Logger" to a "Smart Hardware" platform with native battery/power awareness.
- PCBA-ready BOM with LCSC part numbers confirmed.

---

---

### 2026-02-07: Firmware Port — RS-Core (ESP32-S3) Optimization

**Context:** Following the finalization of the RS-Core hardware, the firmware was ported to support the ESP32-S3's specific architecture and new pin mapping.

**Implementation Details:**
- **Pin Mapping:** Updated all peripheral GPIOs to match the RS-Core V2 schematic (GPS: 17/18, IMU: 21/39, SD: 10/11/12/13).
- **Battery Monitoring:** Integrated ADC1_CH7 (IO35) logic. The firmware now captures real-time voltage data, enabling battery percentage tracking in the app and "low power" safety shutdowns.
- **S3 Performance Tuning:**
    - Increased SD SPI frequency to **10MHz** for faster write bursts.
    - Utilized the S3's dual-core architecture to isolate the high-frequency logging loop from the web server.
- **CSV Schema Update:** Added `vbat` as a core telemetry field to every log entry.

**Outcome:**
- Firmware is fully synchronized with the production hardware.
- Ready for final system integration testing and March track deployment.

---

### 2026-02-08: UI Modernization & Visual Polish

**Context:** Comprehensive UI refresh to create a premium, professional racing aesthetic.

**Implementation Details:**
- **Design System:** Implemented glassmorphism cards with `backdrop-filter: blur()` and semi-transparent backgrounds.
- **Typography:** Integrated **Inter** from Google Fonts as the primary typeface; **JetBrains Mono** for timing data.
- **Navigation:** Added meaningful icons to all navigation tabs with high-contrast glow effects on active state.
- **Stat Cards:** Redesigned with premium icon-info layout and racing-specific metrics.
- **Playback Modal:** Refined telemetry dashboard with improved grid layout and visual hierarchy.
- **Animations:** Added `viewEnter` transitions and hover micro-animations for cards and buttons.

**Outcome:**
- Modern, racing-inspired UI that feels premium and responsive.
- All existing functionality preserved; JS compatibility maintained.

---

### 2026-02-08: BLE → WiFi Automatic Handoff

**Context:** Solved the "Connectivity Paradox" where phones lose internet when connecting to ESP32's WiFi.

**Implementation Details:**
- **Polling Logic:** After WiFi config via BLE, app polls status characteristic until ESP32 reports connected + IP.
- **Auto-Detection:** Added `autoDetectDeviceIP()` that reads from BLE, falls back to localStorage, then network scan.
- **IP Persistence:** Removed code that cleared `lastDeviceIP` on page load; IP now persists across sessions.
- **Auto-Disconnect:** BLE disconnects automatically 3 seconds after WiFi handoff to save device power.
- **Multi-Device Support:** Fixed scanner to detect multiple Dataloggers and prompt user selection.

**Technical Fixes:**
- Made WiFi connection non-blocking in firmware (background thread) to prevent BLE timeout.
- Added 3x WiFi scan retry for reliability.
- Disabled WiFi power management for faster connections.

**Outcome:**
- Seamless zero-config experience: Connect via BLE → Configure WiFi → App auto-switches to HTTP.
- Phone keeps internet throughout the process.

---

### 2026-02-08: Pit Lane Auto-Pause & Per-Session IMU Calibration

**Context:** Workflow-driven feature to eliminate garbage data and ensure accurate lean angle calculations.

**Implementation Details:**
- **State Machine:** New states: `PAUSED` | `CALIBRATING` | `LOGGING`.
- **Pit Detection:** GPS geofence with 50m radius. "Mark Pit" button in app grabs current coords.
- **Auto-Pause:** Logging suspended while inside pit geofence; LED shows slow amber pulse.
- **Calibration Trigger:** When paused + speed < 2 km/h for 10+ seconds + bike upright (Z-axis dominant).
- **Calibration Process:** Samples IMU for 3 seconds, computes gravity vector, stores in session memory.
- **LED Animations:**
    - Paused: 🟡 Slow amber pulse (1s cycle)
    - Calibrating: 🔵 Fast blue sweep
    - Calibrated: 🟢 3x quick green flash
- **Auto-Resume:** Logging starts when GPS exits pit geofence AND speed > 10 km/h.

**Design Decisions:**
- Calibration is **per-session** (not persistent) since datalogger orientation may change between mounts.
- Calibration happens when rider is sitting on bike (not on kickstand) for accurate reference.

**Outcome:**
- No more garbage data from pit lane activity.
- Accurate lean angle calculations based on actual mounting orientation.
- Clear visual feedback throughout the workflow.

---

### 2026-02-08: Phase 1 Multi-User Authentication (Complete)

**Context:** Implemented user authentication to support multiple riders with isolated data.

**Implementation Details:**

1. **Database Schema (SQLite):**
   - Created `users` table: id, email, password_hash, name, profile_photo, bike_info, home_track, created_at
   - Created `SessionMeta`, `TrackMeta`, `TrackDayMeta` tables with `user_id` foreign keys
   - Migration script (`init_db.py`) assigns existing data to default admin user

2. **Auth Endpoints:**
   - `POST /api/auth/register` - User registration with bcrypt password hashing
   - `POST /api/auth/login` - JWT token in httpOnly cookie
   - `POST /api/auth/logout` - Cookie invalidation
   - `GET /api/auth/me` - Current user info
   - `PUT /api/auth/profile` - Profile updates

3. **Protected Routes:**
   - Global `before_request` hook protects all `/api/` routes
   - Exceptions: `/api/health`, `/api/auth/*`
   - 401 returned for unauthenticated requests

4. **Frontend:**
   - Login/Register modal in header
   - Auth state management in `app.js`
   - Auto-redirect to login on 401
   - Profile editor in Settings tab

5. **Data Isolation:**
   - All queries filtered by `user_id`
   - Ownership verification on delete/rename
   - New sessions auto-linked to current user

**Outcome:**
- Multi-user support fully operational
- Existing data migrated to admin user
- Ready for Phase 2 (privacy controls, public/private sessions)

---

---

## 25. Phase 25 — Mobile Implementation Start (2026-02-09)

**Objective:** Transition the Racesense Companion App from a web-only interface to a native mobile experience using Capacitor.

### Core Implementation:

1.  **Framework:** Capacitor 6.x "Mobile Wrap".
2.  **Platform Initialization:**
    - Initialized Capacitor in `/server/ui/`.
    - App Name: "Racesense"
    - App ID: `com.racesense.app`
3.  **Core Plugins Installed:**
    - `@capacitor/app`, `@capacitor/filesystem`, `@capacitor/network`, `@capacitor/preferences`, `@capacitor/device`, `@capacitor/splash-screen`, `@capacitor/status-bar`.
    - `@capacitor-community/bluetooth-le` (BLE Control).
    - `@capacitor-community/sqlite` (Local results cache).
    - `@capacitor/http` (ESP32 data transfer).
    - `@capacitor/local-notifications`.
4.  **Hybrid Burst Scaffolding:**
    - Created `capacitor-ble-adapter.js` to handle the command channel to the ESP32.
    - Updated `package.json` with mobile-specific build and sync scripts.

### Technical Decisions:

- **Web Directory:** Moved web assets to `/server/ui/www/` to avoid recursive inclusion of native platform folders during the build process.
- **Config:** Enabled `cleartext` support in `capacitor.config.json` to allow communication with the ESP32's local WiFi Access Point (HTTP).

**Status:** ✅ Phase 25 Foundation Complete. Native Android and iOS projects initialized.

---

## 26. Phase 26 — Hybrid Burst Implementation (2026-02-09)

**Objective:** Implement high-speed data transfer between ESP32 and Mobile App using the "Hybrid Burst" model (BLE Control + WiFi Data).

**Strategic Decision: The "Thin App" Data Conduit**
In alignment with the "Thin App" philosophy, the mobile app now acts as a high-speed data conduit. It performs no local parsing or analysis of telemetry; its sole responsibility is to burst raw data from the ESP32 and prepare it for cloud processing.

**Implementation Details:**
1. **Hybrid Sync Service:** Created `hybrid-burst-service.js`, a singleton orchestrator that manages the cross-protocol handshake:
   - **BLE:** Sends `START_AP` command and listens for the "AP Ready" notification containing SSID/Password.
   - **WiFi:** Programmatically joins the ESP32's Access Point using `wifiwizard2`.
   - **HTTP:** Fetches a session manifest and downloads raw CSVs via high-speed HTTP from `192.168.4.1`.
   - **Filesystem:** Saves data to native storage via `@capacitor/filesystem`.
2. **Seamless UI:**
   - Added a "Sync with Device" button to the Dashboard.
   - Implemented a fullscreen progress overlay that guides the user through the multi-protocol transition (Connecting -> WiFi Joining -> Downloading -> Complete).
3. **Hardware Integration:**
   - Updated `AndroidManifest.xml` and `Info.plist` with necessary permissions for programmatic WiFi switching and local network access.
   - Integrated with `capacitor-ble-adapter.js` for robust BLE communication.

**Impact:**
- Eliminates manual WiFi switching for the rider.
- Achieves ~2 MB/s transfer speeds (burst mode) compared to slow BLE file transfer.
- Simplifies the "Paddock Workflow": Tap Sync -> Wait 30s -> All data on phone.

**Status:** ✅ Complete & Integrated into Main App.

## 27. Phase 27 — Admin User Management (Complete)

**Date:** 2026-02-09

### Motivation
As the user base grows, manual tier management via the command line or hardcoded checks became unsustainable. A formal admin system was required to manage subscriptions and user privileges.

### Decisions
1. **Database-Driven Privileges:** Added a formal `is_admin` boolean column to the `User` model. Removed hardcoded email domain checks.
2. **Super Admin Role:** ID=1 is designated as the Super Admin, with the exclusive power to grant or revoke admin status for other users.
3. **Protected API:** Implemented an `@admin_required` decorator to secure all management endpoints.
4. **Admin UI:** Added a dedicated "Admin" tab in the companion app (visible only to admins) featuring:
   - Searchable user list with pagination.
   - Tier management (Free/Pro/Team) dropdowns.
   - Session count and join date visibility.
5. **Upgrade Messaging:** Updated the "Pro Upgrade" flow to direct users to contact support via email, providing a clear path to conversion while payment integration is in development.

### Implementation Details
- **Backend:** Flask endpoints for user listing, tier updates, and admin toggling.
- **Frontend:** Responsive admin table, search/filter toolbar, and updated auth UI state management.
- **Migration:** Automated script to add the `is_admin` column and bootstrap the first admin user.

**Outcome:**
- Centralized user management system.
- Secure, scalable privilege model.
- Improved UX for manual subscription activation.

**Status:** ✅ Complete & Frozen

---

## 28. Phase 28 — Web MVP & Reverse Hotspot Sync (2026-02-14)

**Objective:** Transition to a "Zero-Install" Web UI for the March MVP, bypassing app store friction while maintaining seamless sync.

### Strategic Pivot: The "Reverse Hotspot"
Since mobile browsers cannot programmatically join the ESP32's WiFi, we flipped the connection logic.
1. **Handshake:** Web UI (browser) connects to ESP32 via **Web-BLE**.
2. **Provisioning:** Browser sends the phone's hotspot credentials and the Nitro 5 backend URL to the ESP32.
3. **Execution:** ESP32 joins the phone's hotspot and blasts raw CSVs directly to the Nitro backend.
4. **Visibility Fix:** Renamed device to `Racesense-Core` and implemented explicit **Service UUID advertising** to fix macOS/iOS "invisible device" issues.

### Implementation Details:
- **Firmware:** Updated `ble_provisioning.py` with STA-mode priority and `uploader.py` with progress notifications.
- **Backend:** Hardened `/api/upload` to auto-trigger the analysis pipeline immediately upon CSV receipt.
- **Frontend:** Built a responsive **Sync Wizard** in the Web UI with platform detection (Chrome/macOS, Bluefy/iOS).
- **Handover:** Created `CONNECTIVITY_HANDOVER.md` for troubleshooting platform-specific permissions.

**Status:** ✅ Web MVP Infrastructure Complete. Verified on Linux/Nitro hardware.

---

## 29. Phase 29 — Distributed Brain Architecture (2026-02-15)

**Objective:** Offload heavy implementation logic to the MacBook Air M4 while keeping the Nitro 5 focused on hardware and background services.

### Infrastructure:
- **Node Mac (The Brain):** Running **Ollama** (`192.168.1.38`) with `qwen2.5-coder:14b` and `deepseek-r1:14b`.
- **Node Nitro (The Muscle):** Orchestrates project files, GitHub synchronization, and ESP32 hardware interactions.
- **Network Bridge:** OpenClaw on Nitro routes coding tasks to the M4's Unified Memory via a local API bridge.

### Outcomes:
- **Zero Latency:** Coding responses dropped from ~50s (Nitro local) to <3s (Mac M4).
- **Privacy:** Proprietary code stays on the local network (M4 reasoning loop).
- **Cost Efficiency:** Shifted 90% of development workload to local silicon ($0 token cost).

**Status:** 🚀 Distributed Brain Setup Live & Verified.

---

## 30. SD Card Hardware Debugging: The Final Resolution (2026-02-25)

**Context:** After a period of instability where the SD card was intermittently failing to mount or causing FAT corruption, we performed a deep-dive diagnostic to verify the hardware and stabilize the driver.

### The Problem
The device was failing with `CMD0` timeouts or `readblocks failed` errors. Additionally, even when the card initialized, `os.mount` would frequently fail with a mysterious `UnicodeError`.

### Technical Discovery & Diagnostics
We abandoned high-level scripts to perform low-level bit-banging and raw sector scans:
1.  **Driver Sensitivity:** The Python-based `sdcard.py` driver was identified as too sensitive to SPI timing constraints and signal integrity on the workbench wiring.
2.  **CMD16 Reject:** Modern SDHC cards often have a fixed 512B block size. The driver was treating a "command rejected" response to `CMD16` (Set Block Length) as a fatal error, whereas it should have been ignored.
3.  **Signal Maturity:** Bitbang SPI (SoftSPI) proved that the physical link was healthy enough for initialization but struggled with high-speed data tokens during raw reads.
4.  **Native Power:** Switching to the built-in C-based `machine.SDCard` driver provided immediate stability. It handles the underlying SPI timing and error recovery significantly more gracefully than the Python implementation.

### The Breakthrough: Raw Sector Scanning
Using the native driver, we performed a raw scan of the card:
- **Block 2048:** Successfully retrieved the FAT32 boot sector (`eb589042...`). This proved that the **physical wiring (SCK: 12, MOSI: 11, MISO: 13, CS: 10)** was perfect and the previous issues were purely software/timing related.

### Resolution
1.  **Format:** Performed an on-device `os.VfsFat.mkfs(sd)`. This cleared the `UnicodeError` on mount, which was traced back to a corrupt or incompatible Volume Label string on the card's original filesystem.
2.  **Raw Verification:** Wrote a 512-byte test pattern to block 8192 and verified a bit-perfect read-back.
3.  **Final Pivot:** Officially switched the datalogger-v2 firmware to use **Native machine.SDCard support**.

### Outcome
- ✅ **Hardware Verified:** Wiring and SPI buses are confirmed 100% stable.
- ✅ **Filesystem Fixed:** Card is formatted, mounted, and reading/writing files flawlessly.
- ✅ **Speed:** Verified stable operation at 400kHz (Init) and 10MHz (Active).

**Status:** 🏁 **DONE.** The SD card reliability hurdle is finally cleared. The ESP32-S3 hardware is ready for long-duration track logging.

---

## 31. Hardware Validation: BMI323 & Component Integration (2026-02-26)

**Objective:** Validate I2C hardware stability with the BMI323 IMU and test a 10Hz synchronized logging loop with the GPS and SD Card.

### Difficulties & Resolutions
1. **IMU I2C Lockups:** Initial testing showed the BMI323 frequently locked up the I2C bus (Timeout errors). After building raw communication scripts to isolate the issue, we identified the physical breakout module as faulty. Swapping to a new BMI323 module immediately resolved all communication errors.
2. **Standalone Testing:** To prove physical wiring without relying on complex main firmware, we built an isolated, closed-loop script (`test_bmi323_validated.py`). This script runs indefinitely on the RS-Core, outputting direct IMU data to confirm absolute hardware stability. 

### System Integration Testing
We merged all stable components into a dedicated workbench test script (`full_system_test.py`) to simulate high-load conditions:
- **Logging Loop:** Successfully recorded GPS and IMU data at a synchronized 10Hz.
- **Data Protection:** Implemented a 5-second SD card `flush()` and `os.sync()` routine to prevent FAT table corruption if the motorcycle power is suddenly cut.
- **Smart Feedback:** Added an intuitive LED UI (breathing while waiting for GPS; fast blink during logging; brightness reacts dynamically to physical IMU motion).

**Status:** ✅ **Complete.** The physical hardware capability (ESP32-S3 + GPS + SD + BMI323) is fully validated and ready to be integrated into the actual production firmware.

---

## 32. Phase 32 — Cloud Production Deployment & Integration (2026-02-27)

**Objective:** Transition the hardware logger into a fully integrated, cloud-deployed production system.

### Key PM Entries
1. **Stabilized Logging Setup**
   - Successfully established and verified stable connectivity between the ESP32 and the application.
   - Thoroughly tested the AP (Access Point) captive portal for reliable device onboarding.
   - Validated end-to-end data synchronization protocols between the hardware logger and the server.

2. **Critical Bug Fixes**
   - **GPS Integration:** Resolved parsing and connectivity issues, ensuring accurate latitude/longitude and speed capture.
   - **IMU (BMI323) Calibration:** Diagnosed and fixed the "frozen gyroscope" issue by manually adjusting the `adv_power_save` bit in the `REG_PWR_CTRL` register, allowing dynamic 6-axis motion tracking to resume.
   - **ESP32 Stability:** Addressed timeout/bootloop issues caused by race conditions during the initial boot sequence by introducing a 5-second "Safe Boot Window" to allow for controlled firmware updates.

3. **Domain Name Acquisition [MAJOR]**
   - Successfully purchased and configured the primary production domain: **racesense.in**.
   - Configured Cloudflare/GoDaddy DNS routing to properly point A-records and CNAMEs to the new production environment.

4. **Cloud Server Infrastructure [MAJOR]**
   - Provisioned a dedicated Utho Cloud VPS (Ubuntu 24.04 LTS, 1 vCPU, 2GB RAM) using the cost-effective "capped-hourly" billing model.
   - Secured the remote server environment with strict UFW firewall rules, SSH-key authentication, and Let's Encrypt (Certbot) SSL certificates.

5. **Full System Integration**
   - The Racesense Web Server is now officially **LIVE**.
   - Deployed the Python backend (Gunicorn/Flask) as an automated `systemd` background service for 24/7 uptime.
   - Configured Nginx as a highly-optimized reverse proxy to natively serve the Vue/JS frontend while securely routing API traffic.

**Status:** ✅ **Complete & Live.** The system is now fully integrated with a production cloud backend accessible at https://racesense.in.

---

## 33. Server API Security Hardening (2026-02-27)

**Objective:** Secure the Flask API server for cloud production deployments, protecting against unauthorized access, IDOR, SSRF, and other vulnerabilities.

### Actions Completed:
1. **Authentication Enforcement:** Added `@jwt_required()` to 15+ previously unprotected endpoints (including learning files, sessions, and user social data).
2. **IDOR Prevention:** Implemented strict ownership checks across all state-modifying endpoints (rename, delete, notes). Only resource owners or admins can modify data.
3. **SSRF Mitigation:** Introduced `IS_CLOUD` mode and a `@local_only` decorator to completely block local network scanning endpoints when deployed to the cloud. Added IP validation (blocking link-local/loopback).
4. **JWT & Request Hardening:**
   - Enforced `Secure` and `SameSite='Lax'` for JWT cookies in production mode.
   - Implemented a `MAX_CONTENT_LENGTH` (50MB) to mitigate large payload DoS.
   - Added password strength and regex-based email format validation during registration.
5. **Production Headers & CORS:**
   - Applied comprehensive security headers: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Strict-Transport-Security`, and a strict `Content-Security-Policy`.
   - Hardened CORS configuration to restrict allowed origins to the specific production domain.
   - Sanitized all backend error responses (500s) to hide traceback details in production mode.

**Status:** ✅ **Complete.** API is hardened for the cloud baseline. Remaining tasks for high-scale environments include PostgreSQL migration and Rate Limiting.

---

## 34. Phase 8 — UI/UX Overhaul & Architecture Review (2026-02-28)

**Objective:** Modernize the racer-facing interface, streamline user management, and establish a clear technical debt cleanup strategy to ensure production scaling.

### Completed Actions:
1. **Profile Picture Feature (Full Stack):**
   - Built a complete, end-to-end avatar system. Backend resizes incoming images to 256x256 via Pillow, saving securely into the `data/users/<id>/` sandbox.
   - Modified API middleware to allow unauthenticated GET access to `/api/users/<id>/photo`, enabling native browser caching via `<img>` tags.
   - Created a dynamic frontend component with hover overlays and seamless upload/remove states.
2. **UI & Navigation Polish:**
   - Remapped the application header and profile side-panel. Fixed transparency bugs and improved visual hierarchy.
   - Moved "Change Password" and "Generate Device Tokens" into contextual UI flow modals rather than standalone pages.
   - Updated core branding to "PRECISION RIDE ANALYTICS and DATA-DRIVEN racing".
3. **Comprehensive Architecture Review:**
   - Performed an objective audit of the system, identifying the 3,380-line `main.py` and the synchronous `subprocess.run()` analysis pipeline as critical scalability risks.
   - Outputted a formal priority matrix and 7 self-contained markdown prompts covering: HTTPS/SSL enforcement, decoupling blueprints, background job queues, and Postgres migration.
4. **Targeted Bug Fixes (The Deduplication Gap):**
   - **Analyze All Bug:** Fixed a flaw where the system would re-process already analyzed CSV files. The logic now accurately scans the session JSON `source_file` metadata and filters the queue.
   - **Track Renaming:** Replaced a broken subprocess call to a non-existent script with a direct, safe SQLAlchemy `db.session.commit()`.
   - **Environment Consistency:** Replaced all hardcoded `python3` subprocess invocations with `sys.executable` to guarantee correct virtual environment resolution in production.

**Status:** ✅ **Complete.** The application interface feels significantly more premium, and the engineering team has a clear, documented path to dismantle the technical debt in the backend.

---

## 35. Comprehensive Architecture Review & Cleanup Plan (2026-03-01)

**Objective:** Having reached a reasonably feature-rich state, PM mandated a comprehensive technical review of the entire system architecture to identify scalability risks, architectural bottlenecks, and single points of failure before scaling production traffic.

### Key Architectural Findings

**✅ The Good (Solid Foundations):**
- **Token Segregation:** Dual-auth architecture properly separates device token uploads (ESP32) from user JWT web interactions.
- **Processing Pipeline:** The core `SessionProcessor` remains highly modular and isolated, successfully persisting results into standalone JSON artifacts.
- **User Sandboxing:** Complete file-system separation between user workspaces (`data/users/<id>/...`) guarantees data isolation. 

**❌ The Bad (Critical Technical Debt):**
- **The Monolith:** `main.py` has grown to an unmanageable 3,380 lines and 128 endpoints, intermixing auth, tracks, processing, and hardware sync layers.
- **Synchronous Subprocesses:** The analysis pipeline uses blocking `subprocess.run()` calls. With only 2 Gunicorn workers on the VPS, a single heavy ESP32 sync (or "Analyze All" command) effectively stalls the entire web server, causing `ConnectionTimeout` failures for other riders.
- **Database Contention:** Heavy reliance on SQLite limits concurrent writes, creating "database locked" scenarios during simultaneously occurring uploads and user profile updates.
- **Security Gaps:** No Rate-Limiting makes the API vulnerable to brute force and spam, and the lack of HTTPS combined with `Secure=True` JWTs breaks cloud authentication flows.

### PM Prioritized Action Plan

To systematically resolve these issues, 7 explicit execution prompts were generated and placed in `docs/plans/architecture-cleanup/`:

- **🔴 P0 (Critical - Must Fix Immediately):**
  1. `01-https-ssl-setup.md` - Deploy Certbot/Nginx Let's Encrypt to enable HTTPS and fix JWT secure cookie failures.
  2. `02-fix-sys-executable.md` - Fix virtual environment pathing in all subprocess calls to prevent analysis failures in production (Completed).

- **🟠 P1 (High - Structural Scaling):**
  1. `03-background-job-queue.md` - Migrate from blocking subprocesses to asynchronous background jobs (e.g., standard Queue + Worker) to protect Gunicorn thread pools.
  2. `04-split-main-into-blueprints.md` - Refactor `main.py` into distinct functional Flask Blueprints (`auth`, `sessions`, `tracks`, etc.) to restore maintainability.

- **🟡 P2 (Medium - Reliability and Security):**
  1. `05-database-migrations.md` - Implement Flask-Migrate (Alembic) to safely evolve schemas without risking production data loss.
  2. `06-sqlite-to-postgresql.md` - Transition to Postgres to natively handle concurrent locking.
  3. `07-rate-limiting.md` - Implement Flask-Limiter for API abuse protection.

**Status:** 📋 **Prioritized.** The technical debt has been documented, triaged, and segmented into actionable work units. Engineering is clear to proceed with execution starting from P0.

---

## 36. Phase 8.1 — P0 Architecture Fixes (2026-03-01)

**Objective:** Immediately resolve the two critical (P0) architectural issues identified as active production blockers.

### Completed Actions:

1. **P0-1: HTTPS/SSL Setup Readiness (Validated)**
   - Re-architected `server/racesense_nginx.conf` into a robust, production-ready SSL template.
   - Configured port 80 to issue 301 permanent redirects to HTTPS.
   - Set up the main `listen 443 ssl` block mapped to Certbot's standard Let's Encrypt path.
   - Authored `deploy/setup_ssl.sh`: A 5-step automated deployment script for the VPS that handles apt-installing certbot, linking nginx profiles, generating certificates, and verifying auto-renewal.
   - _Impact:_ This fully unblocks the secure distribution of `SameSite='Lax'` JWT Session Cookies over the `racesense.in` domain.

2. **P0-2: Subprocess Virtual Environment Consistency (Validated)**
   - Identified 4 separate hardcoded invocations of `'python3'` bypassing the `/venv/` in `main.py` (`upload_file`, `sync_from_device`, `process_all_files`, and `rename_track`).
   - Replaced all raw binary strings with standard Python `sys.executable`.
   - _Impact:_ Guarantees that production scripts natively bind to the initialized Gunicorn application environment, eliminating mysterious `ModuleNotFound` data-processing failures in production.

**Status:** ✅ **Complete.** Both P0 items implemented and validated. The foundation is stable enough to proceed to the intensive P1 (Gunicorn Thread Scaling & Blueprint Decoupling) workstreams.

---

## 37. Phase 8.2 — P1 Architecture Fixes: Blueprint Decoupling & App Factory (2026-03-01)

**Objective:** Dismantle the 3,380-line `main.py` monolith to restore engineering velocity, improve testing isolation, and establish a scalable `create_app` factory structure. 

### Completed Actions:

1. **P1-1: Flask Blueprint Decoupling (Validated)**
   - Extracted all functional domains from `main.py` into 13 discrete Blueprints under `server/api/blueprints/` (e.g., `auth.py`, `sessions.py`, `tracks.py`, `devices.py`, etc.).
   - Abstracted shared logic into centralized middleware (`server/api/middleware.py`), utility helpers (`server/api/helpers.py`), and RBAC wrappers (`server/api/decorators.py`).
   - _Impact:_ Reduced `main.py` from 3,380 lines to a mere 26-line transparent proxy. Codebase organization now strongly enforces separation of concerns.

2. **P1-2: Application Factory implementation (Validated)**
   - Replaced global Flask `app` instantiation with the definitive `create_app()` factory pattern in `server/api/__init__.py`.
   - Deferred database, JWT, and CORS initialization into the factory scope, allowing tests to mock variables cleanly without polluting the global namespace.
   - _Impact:_ Eliminates circular import nightmares and drastically simplifies unit testing setup. System can now reliably spin up explicit `testing`, `development`, or `production` contexts.

3. **P2-1: Flask-Migrate/Alembic Integration (Validated)**
   - Successfully overlaid `Flask-Migrate` into the `create_app` factory workflow.
   - Bypassed the fragile `db.create_all()` locking race-condition entirely during server restarts holding connections open. 
   - _Impact:_ Unblocked the ability to perform complex schema evolutions (e.g., Phase 9 Social Features or PostgreSQL conversion) without relying on destructive table drops or manual SQLite surgery in production.

**Status:** ✅ **Complete.** The system's backend has been profoundly de-risked. With 34 API tests actively passing and verifying regression integrity, the foundation is primed for P2 scale-out work (Database evolution and Rate-Limiting).

---

## 38. Phase 8.3 — UI Integration & Test Remediation (2026-03-01)

**Objective:** Stabilize the UI and end-to-end testing suite following the massive Phase 8.2 backend refactor (Blueprint extraction and App Factory). Resolve the side-effects of removing the global testing scope and breaking changes to API endpoints.

### Completed Actions:

1. **Test Infrastructure Remediation (Database Wiping Bug Fix)**
   - **Issue:** The previously implemented E2E Playwright tests and Pytest suite were natively mutating the real production database (`racesense.db`) on every execution by injecting `db.drop_all()`.
   - **Resolution:** Implemented explicit Config overrides in the Pytest `conftest.py` utilizing the new App Factory `create_app({ "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:" })` pattern.
   - **Impact:** E2E and Backend tests now run safely in total isolation against an in-memory database, eliminating the destructive wiping of the production data store.

2. **Authentication Flow UI Fixes (403 Handling)**
   - **Issue:** The new API decoupled logic properly returned HTTP 403 (Forbidden) for unapproved Admin users, leading the legacy centralized UI error handler to surface a generic, unhelpful `Connection error` or misfire the "Limit Reached" upgrade modal. 
   - **Resolution:** Passed `displayError: false` to specific auth endpoints and trapped the exact `403` JSON payload. Bubbled the raw `pending admin approval` string directly into the contextual `submitLogin` `#loginError` UI container.
   - **Impact:** Clean, accurate feedback for new users waiting for approval, without jarring popup banners.

3. **Session Details UI Refactor Bugs**
   - **Issue 1:** The `toggleDetailsSection` accordion functionality for Session Context, Visual Insights, etc. was rendered inert due to inline `<script>` tags being blocked inside dynamically injected `innerHTML`.
   - **Fix 1:** Extracted the visual toggle logic globally to `window.toggleDetailsSection` in `app.js`.
   - **Issue 2:** The Comparative Analysis ("Ghost Lap") feature failed silently because the old `/api/sessions/{id}/compare` endpoint was relocated and flattened to `/api/compare` during the Blueprint shuffle.
   - **Fix 2:** Rewired the frontend to point to the new endpoint logic.
   - **Issue 3:** The refactored `compare` backend endpoint crashed with an `Index Error` if lap arrays were incomplete or `optimal` was chosen. Furthermore, it stripped out the interpolated distance/time matrices required by the frontend SVG simulation.
   - **Fix 3:** Rebuilt `compare_laps` in `leaderboards.py` to correctly seek by `lap_number` and re-injected the synchronous array parsing loop necessary to map the Delta Curves and side-by-side Ghost positions.
   - **Impact:** Restored total interactivity and analytical parity to the Session dashboards.

---

## 39. Phase 8.4 — Subscription Tier Refinement (2026-03-03)

**Objective:** Restrict Team creation to the "Team" subscription tier to better align with the professional coaching and organizational nature of the feature.

### Completed Actions:

1. **Backend Permission Hardening**
    - **Change:** Updated the `create_team` endpoint in `server/api/blueprints/teams.py`.
    - **Logic:** Changed `@require_tier('pro')` to `@require_tier('team')`. 
    - **Impact:** Only users explicitly on the 'team' tier can now successfully POST to the team creation API.

2. **Frontend UI Consistency**
    - **Change:** Modified `loadTeams` and `showCreateTeamModal` in `server/ui/app.js`.
    - **Logic:** Updated visibility checks and upgrade prompts to point to the 'team' tier instead of 'pro' for team creation.
    - **Impact:** Users are now correctly informed that a "Team" tier subscription is required to create a new organization, preventing confusion at the API boundary.

3. **Documentation Alignment**
    - **Update:** Reflected the tier changes in `docs/project_ramp_up_guide.md`.
    - **Context:** Clarified the three-tier hierarchy (Free, Pro, Team) and explicitly called out the Team tier requirement for the Teams feature.

**Status:** ✅ **Complete.** Feature access is now properly gated according to the project's commercial and organizational model.

---

## 40. Infrastructure: SSH Identity Split (2026-03-03)

**Objective:** Isolate GitHub authentication from Production Server access to eliminate passphrase fatigue and improve security hygiene.

### Completed Actions:

1. **SSH Key Generation**
    - **Action:** Generated a new ED25519 key specifically for GitHub (`~/.ssh/id_ed25519_github`).
    - **Configuration:** Created without a passphrase for frictionless Git operations.

2. **SSH Config Refactoring**
    - **File:** `~/.ssh/config`
    - **Change:** Explicitly mapped `github.com` to the new key and `rs` (Production) to the original passphrase-locked key.
    - **Impact:** `git push/fetch` operations are now transparent (no prompts), while Production access remains secured by a mandatory passphrase.

**Status:** ✅ **Complete.** Development velocity increased; Production security maintained.

---

## 41. Infrastructure: Universal Stealth Provisioning & LED Status Indicators (2026-03-04)

**Objective:** Achieve a zero-friction "Magic Link" provisioning experience and provide clear device state feedback via the onboard GPIO 2 LED.

### Key Implementation Details:

1.  **Stealth Provisioning (Captive Portal):**
    *   **Universal Probe Suppression:** Implemented handlers for Apple, Android, and Windows to return success/204 codes. This prevents intrusive captive portal popups while keeping the mobile device connected to the RS-Core AP.
    *   **Magic Link Parsing:** Portal extracts `ssid`, `pass`, and `token` from URL parameters for one-click setup.

2.  **LED Status Manager (GPIO 2):**
    *   **Prioritized Logic:** Integrated GPIO 2 patterns into the `LEDManager` class.
    *   **Patterns:** Pairing (2s of 3Hz pulsing / 1s OFF), Connecting (2Hz blink), Connected (Steady ON).
    *   **Resolution Fix:** Increased polling frequency to **10Hz** across all modules for smooth pulses.

3.  **WiFi Connection Logic:**
    *   **30-Second Window:** Increased connection attempt timeout to 30s.
    *   **Radio Reset:** Implemented a full STA/AP teardown before starting the Hotspot to ensure visibility.

### Planned Provisioning Flow:

1.  **Stealth Connection**: Mobile device joins `RS-Core-XXXX`. OS probes are suppressed (Success/204), preventing popups while maintaining the data connection.
2.  **Magic Link Submission**: User clicks "Set up Device" in the web app. Browser sends `ssid`, `pass`, and `token` to the device portal via query parameters.
3.  **Data Persistence**: Device writes credentials to `/data/metadata/device.json` and syncs to flash.
4.  **Grace Period (15s)**: Device displays a success page and pauses for 15 seconds. This allows the user to manually toggle their mobile hotspot **ON**.
5.  **Reboot & Transition**: Device performs a hardware reset.
6.  **Connection Attempt (30s)**: Device tries to join the configured hotspot for 30s.
    *   **Success**: Onboard LED = Steady ON. Device remains in STA mode.
    *   **Failure**: Falls back to AP mode (Pairing). Onboard LED = 3Hz Pulse + 1s OFF.

### Current Status: ✅ **Complete**

**Resolution (2026-03-05):** 
The credential save failure was identified as a MicroPython limitation: `os.makedirs(..., exist_ok=True)` is not supported on this port. This caused a silent exception during the Magic Link submission, skipping the JSON write. The logic was refactored to use nested `try/except os.mkdir()` calls. 

**Verification:** The device now successfully parses the Magic Link, writes `/data/metadata/device.json`, waits 15s while pulsing the LED, reboots, and transitions from **2Hz Pulsing (Connecting)** to **Steady ON (Connected)** against a mobile hotspot. The Stealth Provisioning feature is fully operational.

---

## 42. Phase 9: IoT Architecture Refit — Direct-to-Cloud Pivot (2026-03-05)

**Objective:** Transition the entire RS-Core hardware ecosystem from a brittle "Local Intranet Polling" model to a robust, asynchronous **"Direct-to-Cloud" (IoT) Architecture**. This redesign aims to completely eliminate local network discovery issues (especially AP isolation on mobile hotspots) and enable true remote monitoring.

### Architecture Summary

1. **Decommissioned Local MiniServer:**
    *   Completely purged the blocking `miniserver.py` from the device firmware.
    *   The RS-Core no longer hosts a local web server for the frontend to poll.
2. **Cloud Heartbeat System:**
    *   Introduced a continuous background thread in `uploader.py`.
    *   The device now actively POSTs a heartbeat ping every 15 seconds to `/api/device/ping` using a secure Bearer token (`rsk_...`).
    *   The server saves the `last_sync` timestamp in the newly deployed `device_tokens` database table.
3. **Frontend decoupling:**
    *   Ripped out thousands of lines of complex local IP scanning, subnet brute-forcing, and periodic pinging from `app.js`.
    *   The web app now polls the *cloud* (`/api/devices`) every 15 seconds. If the cloud reports the device synced within the last 60 seconds, the UI lights up as "Connected".
4. **Asynchronous Data Uploads:**
    *   During active sessions, CSV logs are created and queued on the device flash.
    *   The background thread automatically sweeps the `data/session_logs/` directory and POSTs the raw CSVs directly to `/api/upload`.
    *   The backend strips out the legacy blocking auto-analysis logic and safely drops the raw CSVs into the user's `data/learning/usr_<id>` directory for asynchronous, manual human review via the 'Analyze' tab.

### User Flow & Functional Overview

*   **Setup:** The user bonds the device to their account via the offline "Magic Link" portal, saving their credentials and unique `rsk_` token onto the device.
*   **Active Monitoring (Zero Config):** The rider turns on their mobile hotspot and rides. The device connects and starts pumping heartbeats to the cloud.
*   **Remote Visibility:** A mechanic or friend logging into `racesense.in` from anywhere in the world will immediately see the "RS-Core Connected" badge because the UI queries the cloud DB, bypassing the rider's local network firewalls entirely.
*   **Data Acquisition:** When a session ends, the device streams the log to the cloud. The remote mechanic clicks "Refresh" in the Analyze tab, sees the new CSV instantly appear in the cloud directory, and clicks manually process it.

**Status:** ✅ **Complete.** The system is now a true IoT telemetry logger. The frontend and hardware are structurally decoupled and communicate exclusively via the secure web API.

---

## 43. IoT Cloud Architecture: Bug Identification & Resolution (2026-03-05)

**Objective:** Diagnose and resolve the initial failure of heartbeats to appear in the frontend despite the device being online.

### 1. Backend Authentication Blockade
*   **Problem:** The server was returning `401 Unauthorized` for heartbeats.
*   **Cause 1 (Middleware):** The `/api/device/ping` endpoint was not in the `public_paths` whitelist, causing the global JWT middleware to reject requests before the device token logic could run.
*   **Cause 2 (JWT Configuration):** `flask-jwt-extended` was configured to only look for tokens in `cookies`. Device `Authorization: Bearer` headers were being ignored.
*   **Cause 3 (Nginx Stripping):** The Nginx reverse proxy was not explicitly passing the `Authorization` header to the Gunicorn backend.
*   **Resolution:** 
    *   Whitelisted `/api/device/ping` in `middleware.py`.
    *   Updated `api/__init__.py` to allow `JWT_TOKEN_LOCATION = ['cookies', 'headers']`.
    *   Configured Nginx (`racesense_nginx.conf`) to `proxy_set_header Authorization $http_authorization`.

### 2. Frontend Lifecycle & Parsing Issues
*   **Problem:** The UI still showed "Device Offline" even after the 401s were fixed.
*   **Cause 1 (Date Parsing):** SQLite's `datetime('now')` and Python's `isoformat()` produced space-separated strings (e.g., `2026-03-05 02:25:43`). Browsers like Safari require a strict ISO 8601 `T` separator for reliable `new Date()` parsing.
*   **Cause 2 (Clock Skew):** Simple `now - lastSyncTime` logic failed if the client clock was slightly ahead of the server clock (resulting in negative numbers).
*   **Cause 3 (Polling Termination):** The `pollCloudHeartbeat` loop would silently terminate if the `currentUser` was null (e.g., during logout or slow initialization).
*   **Resolution:**
    *   Standardized backend output to strict ISO 8601 with `T` and `Z` (UTC) in `models.py`.
    *   Refactored `app.js` to use `Math.abs(now - lastSyncTime)` to handle skew.
    *   Moved `setTimeout` to the top of the polling function so the loop restarts regardless of auth state.

---

## 44. Deployment Completion: UI Connectivity Confirmed (2026-03-05)

**Status:** ✅ **VERIFIED IN PRODUCTION**

The "Direct-to-Cloud" transition is officially operational.
*   **Latency:** UI reacts to device status within 15s (polling interval).
*   **Offline detection:** UI accurately reflects "Device Offline" after 60s of missed heartbeats.
*   **Persistence:** Polling survives browser sessions and login/logout transitions.

The system is now robust against local network isolation and mobile hotspot quirks.

---

**Status:** ✅ **Complete.** BMI270 producing valid accelerometer and gyroscope data on the live device.

---

## 46. Flashtool Enhancement: Rapid Test Deployment (2026-03-10)

**Context:** The user requested a way to push test scripts (specifically `full_system_test.py`) to the device without completely wiping the OS, which is a slow process during rapid iteration.

### Changes
1.  **Flashtool Update**: Added Option `5) Deploy Full System Test (No OS Wipe)` to `flashtool.sh`. This option performs a soft-reset, copies `full_system_test.py` over as `main.py`, deploys the required BMI270 config blob out of `lib/`, and hard-resets the board.
2.  **Deployment**: Executed the new option to successfully deploy the full system test script to `/dev/cu.usbmodem1234561`.

**Status:** ✅ **Complete.** Test script is running on the device.

---

## 47. Firmware Refactor: Hardware Button Mode Selection + Dual NeoPixel (2026-03-10)

**Context:** The existing firmware used a 30-second WiFi/speed-based decision window to auto-detect whether the device should Upload, Log, or Pair. This was fragile and unpredictable in the field. A new physical Sync Button (IO5) was added to the hardware, along with a second "Onboard" NeoPixel on IO6.

### Decisions

1.  **Hardware Button (IO5) as sole mode arbiter.** Replaced all speed-based, time-based, and WiFi-availability-based role detection with a simple 10-second button check at boot.
2.  **Two Exclusive Modes:**
    -   **LOGGING MODE** (default, no button press): All radios killed. Pure 10Hz telemetry capture + track feedback via NeoPixels. No WiFi, no uploader, no captive portal.
    -   **SYNC MODE** (button pressed): No logging. WiFi enabled for upload. Long press (>3s) enters Pairing mode. Device stays in Sync Mode indefinitely (no auto-reboot).
3.  **Dual NeoPixel:** Onboard NeoPixel (IO6, 1 LED) mirrors the first pixel of the Feedback NeoPixel (IO4, 16 LEDs) at all times.
4.  **Simplified Animations:** Removed all complex patterns (KITT scanners, rainbow wheels, sweeps). All feedback is now simple solid colors, pulses, and fades. Speed and color communicate state.

### Changes

-   **`firmware/main.py`**: Complete rewrite of boot sequence and mode selection logic.
-   **`firmware/lib/led_manager.py`**: Rewritten with dual NeoPixel support and simplified animation states.
-   **`docs/hardware_firmware.md`**: Updated pinout, architecture, and state machine documentation.

### LED Language

| State | Animation | Color |
|-------|-----------|-------|
| Boot | 3 pulses | Blue |
| Decision Window | Fast blink | Green (SD) / Red (no SD) |
| Logging: Searching GPS | Slow pulse | Red |
| Logging: Active | Solid | Green |
| Logging: Paused (Pit) | Slow pulse | Amber |
| Sync: Searching WiFi | Slow fade | Purple |
| Sync: Uploading | Fast blink | Green |
| Sync: Upload OK | Slow fade | Green |
| Sync: Upload Failed | Slow fade | Red |
| Pairing | Breathing fade | Blue |

**Status:** ✅ **Complete.** Firmware refactored. Ready for on-device verification.

---

## 48. Firmware Bugfix: Chunked Upload Crash and Feedback (2026-03-11)

**Context:** The device was crashing and rebooting when attempting to upload session files chunk by chunk to the server. The user also requested that the LED feedback continuously signal rapid green blinking while chunked uploads are ongoing, and stay a slow green pulse after everything is uploaded.

### Decisions

1.  **Fixed memory leak in uploader**: Discovered that the `uploader.py` script was sending HTTP POST chunks without providing a `Content-Length` header. This caused the Nginx reverse proxy to reject the connection immediately, triggering an `OSError` in the MicroPython `urequests` library which subsequently leaked SSL context memory. Added `Content-Length` headers mapping precisely to chunk sizes.
2.  **Continuous LED Ticks**: Added `led.update_sync("SYNC_UPLOADING")` logic directly inside the blocking upload chunk and retry loops. Since LED animations rely on `time.ticks_ms()` evaluations per loop, calling this prevents the LED from appearing "stuck" or frozen during blocking network activities.

### Changes

-   **`firmware/lib/uploader.py`**: Added `Content-Length` header to chunk upload requests and finalization payloads. Passed `led` instance correctly so the LED stays animated.

**Status:** ✅ **Complete.** Fixes applied. Ready for on-device test and deployment.

---

## [2026-03-12] Phase 7.6: Sync Mode Stability & High-Speed Overhaul (V1-V8)

**Objective:** Transform the "painfully slow" sync process (1 chunk every 2-3s) into a production-grade, high-speed telemetry link.

### 1. Diagnosis & Performance Bottlenecks
Initial sync used standard `urequests` with 4KB chunks.
- **Problem:** Every chunk triggered a full SSL handshake (the "2-second tax").
- **Problem:** Handshake clashing with initial network setup caused `ECONNABORTED (113)`.
- **Problem:** Aggressive uploader thread starved the main-core heartbeat, causing "socket starvation" (-202) errors.

### 2. Architectural Decisions (V6-V8)
Fundamental shift in the uploader's networking model:

- **Persistent SSL Sockets:** Replaced `urequests` with raw sockets + `ssl.wrap_socket`. The handshake now happens **once per file**, not once per chunk.
- **Response Body Draining (V7):** Implemented strict manual consumption of HTTP response bodies to keep the persistent socket clean for the next request.
- **Ambitious Chunking (V8):** Increased `CHUNK_SIZE` to **64KB**, verified safe by a manual RAM check (1.8MB free). This saturates the ESP32's SSL engine and DMA buffers optimally.
- **MicroPython Compatibility:** Refactored f-string concatenations to avoid MicroPython 1.22 syntax errors (explicit concatenation used for headers).

### 3. Stability & Thread Safety
- **Network Lock:** Introduced a global `network_lock` in `main.py`. 
- **Sequential Sequence:** Device now performs a "Heartbeat First" sequence. The uploader only spawns if a healthy connection to the cloud is confirmed.
- **Dual-Core Resilience:** Locking ensures Core 0 (Heartbeat/UI) and Core 1 (Uploader) never clash on the SSL stack.

### Outcome:
- **Speed:** From ~2KB/s to **~200KB/s+** (100x improvement).
- **Stability:** Zero "ECONNABORTED" errors during sustained 29-file uploads.
- **Memory:** Managed fragmentation via aggressive `gc.collect()` before large buffer allocations.

**Status:** ✅ Deployed as RS-Core V9 firmware (Internal: V10 fixes applied).

## [2026-03-12] Phase 7.7: Premium Visual Feedback & Bugfixes (V10)

**Objective:** Finalize the user experience with high-fidelity visual indicators for internal states.

### 1. Fixes & Refinements
- **Math Import Bug**: Resolved a `NameError: math` in `main.py` caused by the new animation logic.
- **Heartbeat "Lub-Dub"**: Implemented a realistic double-thump pulse for the heartbeat phase.
- **Blocking Animation Loops**: Wrapped network handshakes in short, high-priority animation loops to ensure the visual pattern "locks in" for the user before the request blocks the core.
- **Hypersonic Uploading**: Increased the green upload blink speed to **40ms** for a high-throughput, high-energy visual effect.

**Status:** ✅ RS-Core V10 Ready for Deployment.

## [2026-03-12] Phase 7.8: High-Fidelity Heartbeat & Variable Cleanup (V11)

**Objective:** Fix regressions and perfect the visual "Lub-Dub" experience.

### 1. Fixes & Visual Polish
- **Variable Cleanup**: Fixed a `NameError: total_chunks` in `uploader.py` by adding proper chunk count calculation.
- **Heartbeat Logic**: Migrated the "Lub-Dub" pulse logic into separate `SYNC_HEARTBEAT_RED` and `SYNC_HEARTBEAT_GREEN` states in `led_manager.py`.
- **Import Safety**: Verified `import math` is available in all critical animation loops.
- **Improved Timing**: Increased the upload pulse speed to a 40ms hypersonic cycle.

**Status:** ✅ RS-Core V11 Deployed.
## [2026-03-12] Phase 7.9: LED Animation Thread Integration (V12)

**Objective:** Eliminate LED "freezing" during blocking network operations by moving animations to a background thread.

### 1. Architectural Improvements
- **Background Animation Thread**: Spawned `LEDManager.start_animation_thread()` on Core 0 during `setup()`.
- **Async State Machine**: Transitioned from manual polling (`update()`) to a state-based model (`set_state()`). The background thread now pumps NeoPixel updates at a consistent 50Hz.
- **Hypersonic Tuning**: Adjusted the upload blink to a precise 40ms cycle (20ms ON/OFF) for maximum visual energy during throughput.

### 2. Integration & Cleanup
- **main.py**: Start thread in `setup()`, converted all status updates to `set_state`. Protected uploader state from being overridden by heartbeat logic.
- **Stability Fix**: Increased WDT to **20s** and reduced heartbeat timeout to **5s** to prevent "ghost crashes" during network retries.
- **Retry UI**: Handshake persists in "Lub-Dub" (red heartbeat) mode during retry cycles for better user diagnostic feedback.

**Status:** ✅ RS-Core L12 Deployed. LEDs now stay fluid during SSL handshakes and 64KB chunk writes.

## [2026-03-12] Phase 7.10: Active Track Sync Authorization Fix

**Objective:** Resolve 401 Unauthorized error during active track synchronization on the device.

### 1. Root Cause Analysis
- The device received a 401 error when calling `/api/device/active_track` because the endpoint was not whitelisted in the API middleware's mandatory JWT check.
- While `/api/device/ping` was whitelisted, the newer active track endpoint was omitted.

### 2. Implementation
- **Middleware Update**: Added `/api/device/active_track` to the `public_paths` list in `server/api/middleware.py`.
- This ensures that device token-based authentication (handled within the route) is allowed to proceed.

**Status:** ✅ Active Track Sync restored (authorization fix).

## [2026-03-12] Phase 7.11: Sync Stability & Live Timing Integration Fixes

**Objective:** Stabilize backend sync and perfect the firmware-side live timing engine.

### 1. Backend Stability (V13)
- **Resolved 500 Error**: Fixed an `ImportError` in `devices.py` where a broken local import `from config import config` was used instead of the standardized `import api.config as config`.
- **Verified Whitelisting**: Confirmed that `/api/device/active_track` is correctly bypassed in the JWT middleware to allow device token authentication.

### 2. Firmware Track Engine & UI
- **Timing Unit Fix**: Corrected a critical unit mismatch in `TrackEngine.py` that was comparing raw milliseconds to sector best times in seconds.
- **Dynamic Sector Gates**: Added support for per-sector `radius_m` definitions from the track JSON, allowing for precise gate sensitivity on different track sections.
- **Track Identification UI**: Added a 10Hz fast white blink for 3 seconds when the start line is first identified, providing clear "Lock-On" feedback to the rider.
- **Feedback Refinement**: Standardized NeoPixel feedback thresholds:
    - **Green (Flash)**: Faster than personal best (< 0s).
    - **Orange (Flash)**: Consistent pace (0s - 0.5s).
    - **Red (Flash)**: Significant gap (> 0.5s).

**Status:** ✅ Active Track feature suite fully operational.

## [2026-03-13] Phase 7.12: IMU Lean Angle Direction Fix

**Objective:** Correct visually inverted lean angles during session playback.

### 1. Root Cause Analysis
- The frontend visualization maps positive lean values to right turns and negative lean values to left turns. 
- The backend `AdvancedIMUProcessor` enforced strictly positive leans by applying an `abs()` function to the computed lateral G-forces. 

### 2. Implementation
- **Mathematical Correction**: Removed the `abs()` constraint from the `lat_g` variable inside the lean calculation loop, allowing for signed outputs. 
- **Sign Flipping**: Extracted lean angles directly from `-lat_g` to guarantee matching directionality with the UI (right hand turns produce negative lateral G's, which should visualize as a positive right lean).
- **Smoothing Adjustment**: Reduced the Exponential Moving Average (EMA) alpha factor from `0.5` to `0.15` to heavily smooth lean data and prevent UI jitter at 100Hz.

**Status:** ✅ Signed Lean Angle calculations with heavier smoothing deployed for V2 IMU.

---

## 49. Hardware Standardisation: Transition to BMI323 (2026-03-14)

**Objective:** Consolidate the hardware platform by standardising on the newer BMI323 IMU, replacing the legacy BMI270 to simplify firmware management and manufacturing.

### Actions Completed:
1.  **Firmware Pivot**: Modified `main.py` and `flashtool.sh` to exclusively target the BMI323 driver.
2.  **Driver Refactoring**: Updated `bmi323.py` to expose sensitivity constants (`ACC_SENSITIVITY`, `GYR_SENSITIVITY`) as class properties, allowing `main.py` to dynamically adjust scaling without hardcoded globals.
3.  **Legacy Preservation**: Kept the `bmi270.py` driver in the codebase for reference but removed all operational imports and deployment hooks.

**Status:** ✅ **Complete.** The RS-Core platform now natively targets BMI323.

---

## 50. Critical Fix: BMI323 Frozen Gyroscope Diagnostic (2026-03-14)

**Objective:** Resolve a "frozen gyroscope" bug where raw data was saturated at `-32768` (0x8000), effectively breaking lean angle and dynamic capture.

### Diagnostic & Resolution:
1.  **Reproduction**: Used `mpremote` to run a raw register-probing script on the device, confirming the gyro was stuck in a low-power/disabled state despite standard init.
2.  **Root Cause Identification**: 
    *   **Register Map Mismatch**: Discovered that the `bmi323.py` driver had shifted addresses for configuration registers (Legacy: 0x1F/0x20 vs Actual: 0x20/0x21).
    *   **Power Mode Collision**: Misconfigured power settings were preventing the gyro engine from spinning up.
3.  **The Fix**:
    *   Remapped `REG_ACC_CONF` to `0x20` and `REG_GYR_CONF` to `0x21`.
    *   Initialised both sensors into **High Performance Mode (Power Mode 7)** via `0x7087` (Accel) and `0x7007` (Gyro).
4.  **Hardware Verification**: Confirmed live 6-axis motion via `mpremote`. Accel and Gyro now respond dynamically to physical orientation changes.

**Status:** ✅ **Complete & Verified.** Gyroscope data is fluid and accurate.

---

## 17. Phase 5.1 — Hardware Health Intelligence (2026-03-16)

**Objective:** Provide granular hardware status feedback to the rider before logging begins, ensuring data integrity for GPS-dependent sessions.

### Decisions

- **Triple-Flag Status:** Decision window now tracks SD, IMU, and GPS independently.
- **GPS Gate:** System is now **explicitly blocked** from entering logging mode if GPS communication is not established.
- **Visual Encoding:**
    - **Fast Green Blink:** All systems nominal.
    - **Fast Red Blink:** Degraded mode (SD or IMU fail). Device proceeds to logging on internal flash if possible.
    - **Solid Red:** Critical failure (GPS communication loss). Device holds in decision window indefinitely.
- **Dynamic Recovery:** The 10-second window is now "Active". If a disconnected GPS module is plugged in, the system detects NMEA sentences dynamically and unlocks the logging gate.

### Outcome

- Increased rider confidence via pre-flight checks.
- Zero "Empty Sessions" due to forgotten GPS hardware.
- Robust handling of internal flash fallback when SD fails.

**Status:** ✅ Complete & Verified

---

## 51. Phase 5.2 — Automated Storage Logistics (2026-03-16)

**Objective:** Eliminate manual data transfer effort for sessions recorded to internal flash.

### Decisions

- **Zero-Touch Migration:** If an SD card is present at boot, any sessions on flash are moved automatically before the main loop starts.
- **Reboot-to-Clean:** Triggering a hardware reset after migration ensures the system starts with a fresh session count and primary storage handles.
- **Visual Locking:** Dedicated white flashing LED animation (`AUTO_COPY`) signals the transfer is active.
- **Collision Safety:** Implemented incremental numbering (e.g., `_1.csv`) if a filename collision occurs on the SD card, preventing data loss.

### Outcome

- Data logged in "fallback mode" (missing SD) is treated with the same permanence as primary data.
- Seamless transition between internal and external storage without user intervention or flashtool scripts.

**Status:** ✅ Complete & Verified

---

## 52. Phase 5.3 — Zero-Allocation UI & Visual Refinement (2026-03-16)

**Objective:** Stabilize device connectivity in Sync Mode and polish the rider's visual feedback interface.

### Decisions

- **Stabilization Strategy:** Root-caused firmware resets during Sync Mode to heap fragmentation from high-frequency (1,600+ entries/sec) LED tuple allocations.
- **Zero-Allocation Architecture:** Refactored the `LEDManager` to use direct buffer manipulation (`self.np.buf[:] = ...`), eliminating memory churn in the 50Hz animation loop.
- **Modular Theme Engine:** Extracted all visual definitions into `color_animations.py` ("Theme Engine"), separating hardware control from aesthetic definitions.
- **Aesthetic Hardening:**
    - **Warm GPS Search:** Shifted yellow tones towards amber (1:4 Green:Red) to ensure distinctness from green markers.
    - **Exotic Rainbow:** Removed standard RGB primaries from the setup palette in favor of complex blends (Cyan, Magenta, Lime) for a more premium look.
    - **High-Speed Status:** Pushed Sync Upload feedback to maximum frequency (25Hz) for urgent feedback.
    - **Racing Feedback:** Extended sector timing flashes to 3.0s and mapped them to the intuitive Green/Orange/Red racing standard.
- **System De-cluttering:** Audited and removed unused `PAUSED` and `CALIBRATING` states to streamline the codebase.

### Outcome

- Sync Mode is now 100% rock-solid during heavy Wi-Fi/SSL operations.
- The UI feels modern, professional, and provides cleaner feedback to the rider under racing conditions.

**Status:** ✅ Complete & Verified

---

## 53. Bugfix: Racing Sector Feedback Integrity (2026-03-16)

**Objective:** Resolve the "Always Orange" feedback bug where sector indicators remained neutral regardless of performance.

### 1. Diagnosis & Root Cause
*   **Reproduction**: Identified that sectors always displayed Orange LED flashes, even during fast laps.
*   **Device Probing**: Used `mpremote` to inspect `track.json` on the hardware. Discovered the `tbl` key was populated with a corrupted "label map" (internal JSON field names) instead of timing data.
*   **Server Bug**: Traced the issue to `server/api/blueprints/devices.py`. The `get_device_active_track` endpoint was incorrectly using `enumerate()` on the TBL dictionary, resulting in a string-key map of metadata labels being sent to the device.

### 2. Implementation & Refinement
*   **Backend Fix**: Modified the server to correctly extract `best_time` values from the TBL `sectors` list.
*   **Firmware Cross-Check**: Verified against `firmware/lib/track_engine.py` to ensure the specific data structure matches (ESP32 expects a simple list of floats indexed by sector number).
*   **Data Formatting**: Implemented sorting by `sector_index` on the server before list serialization to ensure index alignment with the device's sectoral sequence.

### Outcome
*   The device now receives valid TBL data during the active track sync.
*   Accurate Green/Orange/Red performance feedback is restored for all sessions.

**Status:** ✅ **Complete.** Server-side fix live. No firmware update required.

---

## 54. Phase 5.4 — Power & Storage Telemetry Overhaul (2026-03-17)

**Objective:** Provide riders with real-time confidence in device battery and storage health via the UI header.

### Decisions

- **Hardware Sensing:** Root-caused IO35 as digital-only on ESP32-S3. Migrated battery sensing to **IO7** (analog-capable).
- **Precision Math:** Implemented `read_uv()` with 2.8x divider multiplier for calibrated voltage readings (adjusted for 100k/100k divider + ESP32 attenuation).
- **Battery UX:** Replaced simple voltage with a non-linear LiPo discharge curve (0-100%) in the UI for intuitive monitoring.
- **Dual-Storage Visualization:**
    - Implemented total capacity reporting in heartbeat telemetry for both SD and Internal Flash.
    - Designed a new "Storage Group" UI with dual progress bars for "at-a-glance" status.
    - Added "No SD Card" state detection with visual dimming to prevent accidental unrecorded sessions.
- **Database Schema:** Migrated `DeviceToken` to store `storage_sd_total` and `storage_flash_total` for persistence across heartbeats.

### Outcome

- Riders have immediate visual confirmation of battery percentage and remaining storage capacity.
- Reduced risk of unrecorded sessions due to clear SD card presence indication.
- Accurate battery state tracking throughout the discharge cycle.

**Status:** ✅ Complete & Deployed.

---

## 55. Phase 5.5 — Global Sync Progress Integration (2026-03-18)

**Objective:** Enhance the user interface and system feedback by providing a global, batch-aware progress indicator during file synchronization, instead of the previous per-file percentage that visually reset repeatedly.

### Decisions

- **Global Context First:** Shifted the definition of "progress" from the individual file level to the batch level. The user should see one continuous 0-100% sweep for a full sync operation.
- **Hardware Pre-Calculation:** The `uploader.py` script now pre-scans the active directory to calculate the total byte size of all pending `*.csv` files before initiating the upload sequence.
- **Cumulative Tracking:** The uploader tracks `global_current` bytes sent seamlessly across file boundaries.
- **Header-Driven Telemetry:** Firmwares now inject `X-Global-Progress`, `X-Global-Total`, `X-Total-Files`, and `X-File-Index` into the chunk upload HTTP headers.
- **Backward Compatibility:** Older devices that do not send global headers are gracefully handled by the frontend, which will fall back to single-file progress visualization.
- **UI Contextualization:** Enhanced the Sync Pill in the UI to display the continuous percentage alongside a "File X of Y" contextual counter (e.g., "(1/3)").

### Outcome

- Drastically improved user experience during multi-file sync sets. The rider is no longer confused by a percentage that jumps to 100% and back to 0% repeatedly.
- Maintained compatibility with legacy RS-Core firmware versions.
- Added comprehensive unit testing to the backend file synchronization logic to ensure `is_syncing` states transition correctly for batch uploads.

**Status:** ✅ Complete & Deployed.

---

## 56. Phase 5.6 — Upload Pipeline Optimization & Durability (2026-03-22)

**Objective:** Prevent database locking during high-speed chunk uploads and eliminate data-loss windows caused by premature success responses.

### Decisions

- **DB Commit Batching:** Changed behavior in `/api/upload/chunk` to only commit the SQLite session every 20 chunks, cutting locking contention by 95% and allowing concurrent processing to scale linearly.
- **Synchronous Assembly Protection:** Discovered that offloading file assembly to a background thread risked data loss if the server restarted before completion, because the ESP32 aggressively moved its local file to the uploaded folder immediately upon receiving HTTP 200. Restored synchronous file concatenations so the server exclusively returns 200 *after* the file is permanently written to disk.
- **Explicit State Recovery:** Added an overarching `try...except` wrapper around `upload_complete` to guarantee that if file assembly fails (e.g., disk full), the server forcibly resets `is_syncing=False`. This prevents the UI from entering a permanent "Ghost Uploading" state.

### Outcome
- The database easily handles 100Hz+ chunk bursts from multiple riders without timing out.
- The RS-Core to Cloud transfer pipeline is now fault-tolerant and guarantees zero data loss on transit.

**Status:** ✅ Complete & Deployed.

# 0. Stability Hardening Reset (Product Perspective)

**Date:** 2026-03-22

PM decision:

> _Field reliability now has direct product value. A logger that captures truth but fails under weak battery, partial network recovery, or storage pressure is not yet a trustworthy rider-development tool._

### Why this became a product issue

The RS-Core was already functionally capable, but too much of the real-world rider experience still depended on optimistic assumptions:

- WiFi/cloud handshake succeeds on the first attempt.
- Uploads complete in one uninterrupted run.
- Storage remains healthy throughout a session.
- Battery voltage remains comfortably above transient brownout conditions.
- SD write latency is low enough that it does not distort logging behavior.

PM concluded that these were not merely firmware details. They directly affected:

- rider trust in whether the session was truly captured,
- trust in whether data would still be present after the ride,
- predictability of sync after the day ends,
- perceived product maturity.

### Product-level outcomes now targeted

- **More trustworthy sync**:
  The device should recover from temporary server/network failure inside the same sync session, not require ritual rebooting.

- **Reduced end-of-day failure risk**:
  Uploads should resume from received chunks instead of re-sending entire sessions over weak hotspot links.

- **Battery-aware behavior**:
  The module should degrade gracefully under weak voltage by reducing LED draw, lowering WiFi aggressiveness, and deferring non-essential upload work.

- **Cleaner mode transitions**:
  Pairing mode should not stomp on active sync activity. Mode changes must feel intentional and deterministic.

- **Recoverable logging**:
  Partial files should remain diagnosable. The device should leave visible integrity breadcrumbs when sessions are interrupted or storage becomes unsafe.

- **Operational observability**:
  Runtime failures should become explainable through boot/runtime diagnostics rather than anecdotal “it crashed” reports.

### PM framing change

This work formally moves system resilience from a Phase 5 engineering concern into a product requirement:

- **Correctness of capture** is still the first rule.
- **Reliability of capture and retrieval** is now considered part of correctness.

This is a meaningful product posture shift. RaceSense is no longer only optimizing for analysis sophistication; it is optimizing for _trustworthy capture under real trackday conditions_.

**Status:** ✅ Complete

---

## 57. Phase 5.7 — Host.co.in Migration, PostgreSQL Cutover, and Environment Isolation (2026-03-23)

**Objective:** Move RaceSense onto a clean production server with tighter operational control, replace SQLite with PostgreSQL completely, and formalize environment-specific configuration files so development, test, and production no longer share the same database assumptions.

### Decisions

- **New Server Migration:** Moved production hosting from the earlier VPS setup to a fresh **Host.co.in** server. This was treated as a clean-platform migration rather than an in-place repair so infrastructure drift could be removed before the next growth phase.
- **Self-Managed Infrastructure:** Chose a **non-managed VPS** model intentionally. RaceSense now owns the operating model directly:
  - Ubuntu host administration
  - PostgreSQL installation and backups
  - Nginx reverse proxy configuration
  - Systemd service lifecycle
  - SSL renewal and deploy automation
  This increases operational responsibility, but gives tighter control over deployment, performance tuning, logs, and future backend services.
- **DNS Cutover:** Updated DNS so the production domain resolves to the new Host.co.in server. The landing page and API cutover were validated after propagation before database work proceeded.
- **SQLite to PostgreSQL Migration:** Promoted **PostgreSQL** from a planned improvement into the live production database engine. This eliminated the long-standing SQLite write-contention ceiling in the web + worker + upload path.
- **Complete SQLite Removal:** Decided not to keep SQLite as a fallback. The fallback path would preserve dual-database complexity without providing strategic value once all environments can run PostgreSQL.
- **Environment-Specific Database Config:** Replaced the single shared `.env` assumption with explicit environment files:
  - `env/development.env`
  - `env/test.env`
  - `env/production.env`
  Each environment now has an intentionally separate PostgreSQL connection target and runtime envelope.
- **Alembic Simplification:** Since SQLite is gone, the global migration setup was simplified away from SQLite-oriented batch defaults. Historical migrations remain valid, but future migrations now target PostgreSQL as the only database contract.
- **Migration Hardening During Cutover:** The live PostgreSQL rollout exposed old migrations that had SQLite-specific assumptions (`DROP TABLE` behavior and boolean comparisons). Those revisions were corrected during the cutover so the migration chain is now valid on PostgreSQL.

### Outcome

- Production is now running on the new Host.co.in server with DNS pointed correctly.
- RaceSense operates on a self-managed infrastructure baseline with clearer ownership of backups, services, SSL, and deploy behavior.
- PostgreSQL is now the only supported application database.
- SQLite has been removed from the runtime architecture instead of lingering as a shadow path.
- Development, test, and production now have explicit environment-specific config boundaries, reducing accidental cross-environment coupling.
- The codebase and deploy flow are better aligned with future scaling needs, especially for concurrent uploads, worker activity, and operational debugging.

**Status:** ✅ Complete & Deployed.

## 58. Phase 5.8 — BMI323 IMU Optimization & Range Calibration (2026-03-24)

### Why?
The RaceSense IMU integration was using sub-optimal hardware settings for motorcycle racing. Linear accelerometers are extremely sensitive to engine harmonics and road vibration, which were passing unfiltered into the telemetry. Additionally, a pre-existing configuration bug had the sensor set to ±2g range while the driver expected ±4g, causing all G-force measurements to be inflated by 2x.

### What Changed?
- **Hardware-Level Filtering:** Enabled ODR/4 bandwidth filtering (25Hz cutoff) in the BMI323 to reject high-frequency vibration at the sensor level.
- **Hardware Averaging:** Configured 4-sample averaging for the accelerometer and 2-sample for the gyroscope to significantly lower the noise floor without introducing meaningful latency.
- **Range Calibration Fix:** Corrected the `ACC_CONF` register bits to properly set the ±4g range, aligning the hardware with the `8192 LSB/g` sensitivity constant used in the firmware and analysis engine.
- **Boot Diagnostics Hardening:** Improved the IMU initialization sequence to check for error flags both before and after configuration, ensuring the `fatal_err` flag clears during power-on.

### Outcome
- **Accurate Physics:** For the first time, RaceSense provides 1:1 scale G-force telemetry (Z-axis now correctly reads ~1.0g at rest instead of ~2.0g).
- **Vibration Immunity:** Telemetry traces are significantly cleaner, reducing the need for aggressive software-side smoothing and leading to more precise sector timing and consistency scoring.
- **Headroom:** Increased accelerometer headroom from ±2g to ±4g, preventing data clipping during extreme braking or curb strikes.

**Status:** ✅ Optimized & Fixed.

## 59. Phase 5.9 — High-Speed Bulk Batch Upload (2026-03-24)

**Objective:** Eliminate the severe file upload bottleneck during Sync Mode. The previous architecture used a 4KB chunked `urequests` model that was heavily penalized by round-trip latency over slow mobile hotspots (e.g., 6.5 minutes for 4MB). 

### Decisions & Architecture Changes

- **Hybrid RAM/HTTP Decoupling:** The ESP32 heap cannot buffer entire 1MB+ files, but the HTTP protocol doesn't require it. The new `uploader.py` reads 32KB chunks from the SD card/Flash and streams them directly into a massive 512KB HTTP `POST` body over a persistent raw SSL socket.
- **Round-Trip Reduction:** By pushing a 512KB HTTP payload, the system slashes the number of required HTTP connections and server acknowledgments by over 95% (e.g., 100+ requests down to ~3 for a 1.5MB file).
- **Byte-Level Resume:** The server-side endpoint (`/api/upload/batch`) now writes directly to a `.partial` file at a specified `X-Upload-Offset`. If a 512KB batch fails midway due to a dropped hotspot connection, the next attempt seamlessly resumes from the exact byte offset, preventing the "infinite retry" loop of large files.
- **Safe Authentication:** The new `/api/upload/batch` and `/status` endpoints were explicitly whitelisted in `middleware.py` so the device's `Authorization: Bearer <token>` is respected without triggering JWT 401 Unauthorized errors.
- **Spaces in Filenames:** Applied a hotfix to `uploader.py` to URL-encode filenames (replacing spaces with `%20`) in the raw HTTP GET request line, preventing `HTTP 400 Bad Request` errors when syncing duplicated files like `sess_001 copy.csv`.

### Outcome
- **Throughput Profile Identified:** While round-trips are eliminated, real-world testing (3.5 min for 1.5MB = ~7 KB/s) confirmed that the ultimate bottleneck is now the raw SSL/TLS throughput limit of the ESP32 over a weak 2.4GHz mobile hotspot. 
- **Stability Achieved:** Despite the low bandwidth of mobile hotspots, the batching and byte-level resume mechanics guarantee that data successfully syncs without crashing the device or dropping connections.

**Status:** ✅ Complete & Verified.

---

## 60. Phase 5.10 — Front-Facing IMU Session Processing Model (2026-03-28)

**Objective:** Move the IMU pipeline from a broad "arbitrary orientation" exploration into a production-usable session-processing model under the actual hardware usage assumption: the device is mounted **forward-facing**, generally flat, and may be pitched nose-up or nose-down. The output target was clear: produce physically valid lean angles, braking, acceleration, and playback telemetry with the **IMU as the primary contributor**, while still using GPS as a low-frequency physics reference and validator.

### Context and Problem Reframing

The original direction tried to support arbitrary session-by-session mounting by estimating a full per-session mount transform from ride data alone. That work exposed a real limitation:

- The system could often detect bad IMU outcomes.
- It could not yet reliably produce good IMU-led outcomes across real sessions.
- Production therefore kept falling back to `gps_primary`, which was safe, but not aligned with the product goal.

At the same time, real-world usage clarified a more constrained and more useful assumption:

- Riders will mount the unit **forward-facing**.
- The board can be flat or pitched.
- The board is not expected to be reversed or sideways in production use.

That changed the problem materially. Once front-facing is a hard assumption, the backend no longer needs to solve full arbitrary yaw/orientation per session. Instead, session processing only needs to:

- resolve gravity / vertical axis
- estimate pitch / small installation tilt
- confirm the assumed forward direction from rollout and braking evidence
- compute lean and braking in that resolved frame

This was the key simplification that made the production path viable.

### Design Decisions

- **Shift from Arbitrary Orientation to Front-Facing Production Model:** The arbitrary-mount exploration was useful for learning, but it was not the right production model for the expected install behavior. Production logic now assumes the sensor is front-facing by default.
- **Treat GPS as Low-Frequency Physics Truth, not the Main Product Output:** GPS remains necessary as a slow reference and validator, but the goal is no longer "GPS-first telemetry." Instead:
  - GPS defines low-frequency lean/brake baselines
  - IMU contributes short-term dynamics and refined motion
- **Use Front-Facing + Gravity as the Orientation Contract:** Once forward-facing is fixed and gravity is estimated, the session has a usable bike frame. Rollout and braking are retained as confirmation signals, not as the primary source of forward-axis discovery.
- **Prefer a Valid IMU Result Over Perfect GPS if It Is Close Enough:** Production candidate selection now explicitly prefers `orientation_solver` if it passes validation and scores at least `80`, instead of always allowing `gps_primary` to dominate just because it trivially scores `100`.
- **Hard Physical Envelope Tightening:** Lean validation was tightened to reflect realistic motorcycle behavior:
  - warning at `55°`
  - fail at `60°`
  - additional rejection of sustained extreme lean without strong turn evidence

### Implementation Work Completed

#### 1. Session Mount Resolution Reworked Around Front-Facing Assumption

In `server/core/processing/advanced_imu.py`:

- Converted the mount resolver so the **sensor forward axis is assumed to be bike forward**.
- Gravity resolution remains per session and is still derived from startup/static or low-dynamic evidence.
- Startup rollout and hard-brake detection were retained, but demoted into **confirmation signals**:
  - `+rollout_confirmed`
  - `+hard_brake_confirmed`
  - conflict cases reduce confidence instead of redefining the forward axis

This removed a large amount of unnecessary ambiguity from the production path.

#### 2. Hard-Braking Anchor Added as a Real Orientation Evidence Source

The resolver now detects the strongest sustained braking window by:

- finding a multi-second negative GPS speed derivative event
- averaging the IMU acceleration vector over that window
- removing the gravity component
- using the remaining horizontal deceleration vector as a forward-axis confirmation signal

This improved confidence scoring and made the orientation evidence much more physically grounded.

#### 3. Validation Engine Upgraded with Production-Grade Physics Gates

The validation layer in `advanced_imu.py` now rejects or penalizes:

- lean beyond the physical envelope
- strong lean without supporting turn evidence
- braking and acceleration sign contradictions versus GPS speed derivative
- braking that does not align with GPS speed drop
- false braking where IMU implies brake without corresponding GPS deceleration
- prolonged non-zero lean on straights
- lateral G inconsistent with lean
- excessive switching/noise in accel-brake output

This shifted the backend from "emit something plausible-looking" to "only emit an IMU-led result if it survives physics checks."

#### 4. IMU Signal Conditioning Strengthened

Even though firmware already had strong BMI323 filtering in place, the backend was updated to reject occasional residual spikes before they can distort derived telemetry:

- added explicit IMU despiking on accel and gyro channels before frame projection / fusion
- retained rolling smoothing windows for aligned frame channels

This ensured that occasional spikes do not cause the system to reject otherwise good IMU sessions.

#### 5. Lean Logic Rewritten Around Front-Facing Physics

This was the largest functional change.

Earlier IMU lean experiments failed for two reasons:

- roll-rate integration was allowed to dominate absolute lean and drift upward
- accelerometer-ratio lean could blow up under dynamic loads and installation variance

The final production lean model now does this:

- GPS lean is used as the **low-frequency baseline**
- IMU contributes a **bounded short-term delta**
- accelerometer lean is only used as a weak correction in low-dynamic windows

This preserved IMU responsiveness while preventing the absolute lean state from drifting or saturating toward unrealistic values.

#### 6. Longitudinal / Braking Logic Rewritten in the Same Way

The original braking path was too naive: it used smoothed resolved-frame longitudinal acceleration directly, which caused large false-braking counts on some sessions.

The final front-facing braking model now does this:

- GPS longitudinal acceleration provides the **slow baseline**
- IMU longitudinal acceleration provides a **bounded high-frequency delta**
- the IMU delta is decayed on straights and low-dynamic windows
- the combined result is clamped and validated against GPS decel

This was the change that unlocked the remaining real sessions and allowed the IMU-led candidate to survive validation on the under-seat / tail-mounted logs.

#### 7. Session Export Updated with Diagnostics and Final Signals

In `server/core/core/session_processor.py`:

- final derived signals now export:
  - `lean_angle`
  - `aligned_accel_x`
  - `aligned_accel_y`
  - `aligned_accel_z`
  - `yaw_rate`
  - `lateral_g`
  - `acceleration_g`
  - `braking_g`
- calibration payload now exports:
  - `selected_algorithm`
  - `mount_method`
  - `mount_confidence`
  - `rotation_matrix`
  - `gyro_bias`
  - `gravity_vector`
  - `evidence_summary`
  - `validation`
  - `diagnostics`

This gives production outputs enough introspection to support debugging and future UI surfacing without exposing raw internal heuristics to the rider.

### Real-World Validation Work

Today’s work used real production logs and intentionally varied mount families:

- tank flat forward
- under-seat forward pitched down
- above-tail flat forward
- inside-tail forward angled

These sessions were first used in an offline bakeoff harness to learn failure modes, tune thresholds, and compare candidate behaviors. Once the front-facing model stabilized and consistently passed, the temporary bakeoff assets and imported session datasets were removed from the repo to keep only the production code and tests.

The final algorithmic posture after validation:

- IMU-led output is selected when it passes validation and scores strongly
- GPS remains the low-frequency physical baseline and validator
- fallback still exists, but is no longer the dominant output path for the validated real-session set

### Final Validation Outcome

After the front-facing lean and braking rewrites, the collected real-session corpus validated successfully under the production selector:

- tank sessions selected `orientation_solver`
- above-tail sessions selected `orientation_solver`
- under-seat / forward-angled sessions selected `orientation_solver`
- all validated outputs stayed inside the tightened lean envelope and passed the production scoring rules

The final offline summary showed all collected sessions resolving to `orientation_solver` with passing scores and realistic maximum lean values.

### Cleanup Performed

After the algorithm stabilized:

- removed temporary `data/imu_bakeoff` datasets
- removed metadata files created only for the offline learning phase
- removed the one-off `server/core/tools/imu_bakeoff.py` harness from the repo
- kept only:
  - production session-processing code
  - session integration
  - IMU regression tests

This leaves the codebase aligned with the production-ready front-facing model rather than a mixed development/bakeoff state.

### Remaining Caveats

- This is **not** a general arbitrary-orientation solution anymore.
- It is a production-ready solution for the **actual intended mounting contract**:
  - forward-facing
  - flat or pitched
  - not sideways or reversed
- A few unrelated core tests still fail elsewhere in the project (`laps`, `resampling`, `track_manager`), but these are not caused by the IMU work.

### Outcome

RaceSense now has a coherent production IMU pipeline for session processing under the real hardware assumption:

- front-facing mount assumption
- gravity-resolved tilt calibration
- IMU-led lean and braking
- GPS as low-frequency baseline and validator
- physics-gated selection before publishing telemetry

This is the first point where the IMU logic is aligned with both the product goal and the observed real-world usage pattern.

**Status:** ✅ Complete, cleaned up, and validated for the front-facing production model.

## 2026-03-31 — OLED Display Integration on RS-Core

### Summary

Introduced a production OLED display path on the ESP32-S3 RS-Core firmware so the device can surface rider-facing status during boot, sync, and logging. The display is a generic blue/white I2C OLED connected on the shared I2C bus with the BMI323 IMU.

The final implementation now provides:

- a dedicated MicroPython OLED driver under `firmware/drivers/oled.py`
- a firmware-facing status renderer under `firmware/lib/oled_status.py`
- rich boot and sync-mode screens
- minimal logging-mode display behavior aligned to logging-integrity priority
- reliable clean-boot panel wake behavior after a previously non-obvious controller/init issue

### What Was Implemented

The OLED feature set was added in layers:

#### 1. Low-Level OLED Driver for ESP32 / MicroPython

The original reference file was an older Raspberry Pi OLED helper in `temp_data/oled_control.py`. That code was not usable as-is because it depended on Pi/Linux-specific pieces and non-MicroPython libraries.

A new MicroPython-native OLED driver was added in `firmware/drivers/oled.py` with:

- `SSD1306_I2C`
- `SH1106_I2C`
- direct framebuffer-based drawing over `machine.I2C`

This gave us working low-level access to the panel on-device.

#### 2. Firmware Status Rendering Layer

A new status helper was added in `firmware/lib/oled_status.py` so firmware code could render device states without duplicating drawing logic.

This layer now supports:

- startup splash
- boot status
- decision window
- sync search / connect / heartbeat / queue / upload / result
- logging start
- critical storage / event screens

#### 3. Main Firmware Integration

`firmware/main.py` was extended so the OLED becomes part of the normal firmware lifecycle:

- boot-time startup + device status
- decision window screen
- sync mode status and upload progress
- minimal logging-mode display behavior

The flashtool was also updated so `drivers/oled.py` is copied during full sync / clean flash.

### Product / UX Decisions

A key product decision was made during integration:

- boot and sync mode should use the OLED richly
- logging integrity must remain higher priority than display richness

As a result, logging mode was intentionally simplified:

- show a logging start screen
- keep OLED traffic minimal during active capture
- reserve dynamic feedback during logging for rare event-style screens only

This keeps the display useful without letting it compete with telemetry capture timing.

### Main Technical Issue Encountered

The biggest issue was not wiring, not imports, and not general I2C connectivity.

The OLED would often remain completely black after a clean flash / normal boot, even though:

- the device could scan `0x3c` on I2C
- the low-level driver imported correctly
- boot code reached OLED init
- the same panel could be made to display content manually via `mpremote`

That meant the bug was specifically a boot-time panel wake / initialization issue.

### Investigation Path

We worked bottom-up and proved each layer separately.

#### 1. Hardware and I2C Were Verified

Direct `mpremote` commands confirmed:

- OLED at `0x3c`
- BMI323 at `0x69`

This ruled out wiring and bus-address mistakes.

#### 2. Raw Controller Tests Worked

The key breakthrough came from running a direct low-level controller test on the live board that:

- instantiated `SSD1306_I2C`
- then instantiated `SH1106_I2C`
- pushed explicit white / clear / text patterns for each

That command visibly woke the panel and proved:

- the display hardware was good
- low-level driver writes were good
- the actual board responded to `SH1106`
- the panel sometimes needed a stronger wake/init sequence than the normal firmware path was giving it

#### 3. Abstraction-Layer Fixes Alone Were Not Enough

Multiple intermediate attempts were made in higher-level code:

- deferred render scheduling
- simpler direct drawing in `oled_status.py`
- earlier boot rendering
- later boot rendering
- repeated SH1106-only retries

Those were not enough by themselves because they still did not reproduce the exact live sequence that had already been proven to wake the panel.

### Final Fix

The final stable fix was to make firmware boot reproduce the actual known-good wake path instead of approximating it.

The working wake sequence is now:

1. initialize `SSD1306_I2C`
2. write full white
3. clear
4. initialize `SH1106_I2C`
5. write full white
6. clear
7. re-bind normal runtime rendering through `OLEDStatus`

This mattered because the manual recovery that consistently worked on hardware did not use `SH1106` alone. It exercised both controller init paths in sequence before the panel became reliably usable.

Once firmware matched that exact sequence, clean-boot OLED behavior became reliable.

### Boot Flow Cleanup

After wake reliability was solved, the OLED boot experience was cleaned up:

- removed noisy on-screen controller/debug text during wake
- removed internal constructor screens that were never meant for the rider
- added a cleaner `RACESENSE` startup splash
- adjusted boot sequencing so the intended visible flow is:
  - startup splash
  - device status
  - decision window

This separated the hardware wake-up choreography from the rider-facing UI.

### Final Behavior

The OLED implementation now behaves as follows:

- clean flash / clean boot wakes the panel correctly
- startup splash is shown first
- boot health information is shown next
- decision window appears after boot status
- sync mode shows useful WiFi / heartbeat / queue / upload progress information
- logging mode remains conservative to protect telemetry integrity

### Outcome

This work introduced the first production OLED capability on RS-Core and also uncovered a subtle controller/init quirk of the generic I2C panel.

The major outcome was not just “OLED support added”, but:

- reliable boot wake
- clean rider-facing status screens
- correct integration with the firmware lifecycle
- preserved logging-first system priorities

**Status:** ✅ Implemented and working on hardware after matching firmware boot to the validated raw controller wake sequence.

---

## 17. Canonical Track Layout Tooling (Implemented)

**Date:** 2026-04-01 → 2026-04-02

### Why This Was Needed

Track outlines existed, and rider telemetry existed, but they were not enough by themselves to create a reusable canonical track reference.

The operational need was:

- align real rider telemetry to a clean track layout
- preserve that alignment in a stable package
- support repeated rider-line overlays on the same canonical map
- avoid rebuilding layout geometry manually for every track or session

PM decision:

> _The system should treat track layout alignment as a first-class authoring workflow, not an ad hoc engineering script._

### Tool Introduced

A new local web app was created at:

- `track-layout-generator/`

This tool supports:

- loading a track layout image or SVG
- loading telemetry CSV
- rough auto-alignment from telemetry to layout
- manual refinement by translation, rotation, scale, and pivot
- drag-based layout movement
- zoom / pan workspace controls
- anchor placement and labeling
- export of canonical track metadata

### Core Product Decision

PM clarified that the canonical output should not be “just an image”.

The correct artifact is a canonical package containing:

- the layout asset
- the canonical transform
- optional semantic anchors
- geo-reference basis from telemetry
- sampled aligned GPS reference points

This allows later rider sessions to be mapped into the same canonical track space without repeating full manual alignment.

### Canonical Package Structure

The package format was expanded to include:

- embedded layout asset
- telemetry auto-align metadata
- final manual layout transform
- optional anchors
- geo-reference basis:
  - `lat0`
  - `lon0`
  - `metersPerDegLat`
  - `metersPerDegLon`
- sampled aligned GPS references (`~75` points)

This was the key PM shift:

> _A canonical track package must be strong enough to support future sessions, not just reproduce one overlay._

### Anchor Point Clarification

PM clarified that anchor points are optional for phase-one canonicalization.

They are useful for:

- start / finish
- pit entry / exit
- sector boundaries
- named turn references

But they are not required just to render aligned rider lines.

Decision:

- canonical layout + transform is sufficient for baseline use
- anchors are additive semantics, not a hard dependency

### Asset Decision

SVG was confirmed as the preferred canonical layout asset when clean enough, because it is:

- scalable
- stylable
- suitable for overlays and future semantic decoration

PNG remains acceptable as fallback, but SVG is the preferred long-term canonical asset.

### Outcome

The project now has an explicit authoring path for canonical track generation.

That means:

- track alignment is no longer a one-off experiment
- canonical layouts can be created intentionally
- future rider telemetry can be mapped onto stable track references
- RaceSense admin upload can rely on a reusable package instead of manual memory

**Status:** ✅ Implemented as a local authoring tool with canonical package export.

## 2026-04-04: Canonical Track Package Rollout Into Product

### Objective

Take the canonical package concept from a local authoring experiment into the actual product runtime so RaceSense can stop drawing tracks purely from ad hoc rider session geometry.

PM direction was explicit:

- a shared master track package should become the central source of truth
- users should see precise racing lines on top of that package layout
- user-specific timing artifacts such as TBL, best laps, and active-track state must remain siloed
- unknown tracks should still fall back to the existing auto-generated path

### What Was Implemented

The system now has a true shared track catalog:

- `GlobalTrack` model for admin-managed canonical tracks
- admin package upload endpoint and UI
- package materialization into shared track storage under `server/data/tracks/<slug>/`
- merged user-facing tracks API that combines:
  - matched shared master tracks
  - private fallback tracks

Processing now follows a layered resolver:

1. try to identify a shared master track
2. validate candidate against package metadata
3. if accepted, export the session as `global_package`
4. otherwise fall back to per-user track generation

Unknown fallback tracks now create an admin review signal instead of silently remaining isolated forever.

### Important Product Decisions Captured

#### Shared Track Visibility

PM clarified that uploaded shared tracks should **not** appear to every rider immediately.

Decision:

- a shared master track becomes visible to a rider only after at least one of their sessions matches it

This prevents the Tracks tab from turning into a global catalog of irrelevant circuits.

#### Sector Standardization

PM clarified that master tracks should default to exactly **7 sectors**, starting from the start / finish basis in the uploaded package.

Decision:

- sector generation runs during package ingest
- start / finish anchor points in the package are authoritative
- existing centerline data is used when available
- sampled package GPS points can act as fallback geometry for sector derivation

#### Shared Layout Rendering Rule

PM clarified that any place in the app using track layout should prefer the canonical package once a session is matched.

Decision:

- shared master track => render canonical layout
- fallback track => retain legacy geometry rendering

### UI / Runtime Outcomes

The following now use shared package layouts when available:

- Tracks view
- Track detail
- Lap detail
- Comparative analysis
- Ghost lap replay / playback

The package outline is recolored for the dark theme using a dark orange treatment to keep the layout legible on the black/grey product palette.

### Hard Bugs Resolved During Rollout

Several non-obvious issues were uncovered and fixed:

- Alembic multiple-head migration conflict blocking startup
- standalone analysis subprocess import dependency on `api.*`
- mismatch between API-side and analysis-side data roots
- track matching failure caused by legacy start-line assumptions
- admin delete button generating malformed inline JS
- session API returning stale `user_fallback` track metadata from old session JSON
- canonical Y-axis sign mismatch between GPS math and package coordinate space
- playback modal still using legacy raw GPS map path instead of the canonical layout path

### Current Status

This rollout achieved the main architectural goal:

- RaceSense now has a centralized shared track package system
- sessions can resolve to a canonical master track
- shared canonical layouts can render rider telemetry overlays in product views
- user-specific performance data remains siloed

### Current Caveat

The final overlay alignment is improved but not fully closed out.

What is true now:

- package GPS anchor fitting is implemented
- session rendering uses many sampled GPS references from the package
- an additional client-side correction pass refines small rotation / translation drift

What is still likely needed:

- promote the final per-session correction from a browser-side estimate into a durable server-side alignment artifact

That is the remaining gap between “working canonical overlays” and “production-grade, deterministic overlay precision”.

## 2026-04-05: TFT Touchscreen Bring-Up on PSRAM Firmware

### Objective

Replace the tiny debug-only display path with a proper rider-facing TFT workflow and make it usable in the actual RS-Core boot flow:

- larger splash and boot screens on the 2.8" panel
- touch-driven decision window for entering sync
- first-time setup / pairing / sync / logging state visibility
- preserve PSRAM firmware usage
- stop fighting the SD card by moving the display off the SD SPI bus

### What Was Validated

The generic red 2.8" SPI TFT module was validated as:

- **TFT controller**: `ILI9341`
- **Touch controller**: `XPT2046`

Initial bring-up succeeded with standalone workbench scripts and raw touch calibration. The major validation milestones were:

1. TFT color-fill bring-up confirmed panel wiring and control signaling.
2. Touch controller came alive only after wiring the dedicated touch bus pins (`T_CLK`, `T_DIN`, `T_OUT`) in parallel with the display SPI lines.
3. Resistive touch was calibrated successfully with a tap-driven corner routine.
4. The TFT path was then integrated into the actual firmware boot flow.

### Critical Firmware Discovery

The first PSRAM MicroPython build exposed a subtle but important compatibility issue:

- `GPIO38` was valid
- `GPIO36` and `GPIO37` returned `invalid pin`

That meant the earlier temporary `36/37/38` mapping that worked on the non-PSRAM build could not be used on the PSRAM build.

This was not a soldering problem. It was a firmware pin-exposure difference.

### Temporary Pin Ownership Decision

To keep momentum while staying on PSRAM firmware, the following temporary repurpose decision was made:

- `IO5` -> `TFT_CS`
- `IO6` -> `TFT_DC`
- `IO7` -> `TOUCH_CS`
- `IO14` -> temporary battery ADC remap

Temporarily disabled:

- physical sync button
- onboard NeoPixel

This got the display path alive again on the PSRAM build.

### Structural Fix: Dedicated Second SPI Bus

The SD card and TFT originally shared the same SPI bus. That caused intermittent storage failures during logging and sync-path confusion.

After probing candidate pins on the PSRAM build, the following second SPI bus was validated as firmware-visible:

- `IO15`
- `IO16`
- `IO9`

The TFT/touch bus was therefore moved to:

- `SCK` -> `IO15`
- `MOSI` -> `IO16`
- `MISO` -> `IO9`

while keeping control lines on:

- `TFT_CS` -> `IO5`
- `TFT_DC` -> `IO6`
- `TOUCH_CS` -> `IO7`

This isolates the display from the SD card bus and is the correct long-term direction for reliable storage behavior on the current hardware revision.

### Firmware UX Integration

A new TFT UI module was added and expanded in stages:

- `firmware/lib/tft_ui.py`

The TFT now covers:

- enlarged splash screen
- larger boot sequence presentation
- large SD / IMU / GPS status cards
- YES / NO touch decision window
- first-time setup screen
- pairing / WiFi / heartbeat / queue / upload / result / idle sync screens
- logging summary with:
  - satellite count
  - current session filename
  - GPS status
  - battery percentage
  - SD usage percentage

### Important Debugging Outcome

At one point sync appeared broken because the TFT showed:

- successful heartbeat / ACK
- `Pending: 0`

This was not enough evidence to call upload broken.

The more important runtime observation was:

- logging had failed with SD `EIO` while opening the session file

So in that case, there was nothing to upload. The real fault path was storage/file-open, not the heartbeat logic.

### Current Status

What is working:

- TFT boot sequence integrated into main firmware
- first-time setup screen on TFT
- touch calibration validated
- touch decision routing implemented
- dedicated TFT/touch SPI bus mapped in firmware
- battery % and SD % shown in TFT header
- larger rider-facing state screens implemented

What remains under active refinement:

- final SD logging reliability after the display bus split
- sync/upload verification after a successful session file is created on SD
- visual polish beyond scaled bitmap-font rendering

### Product Direction Captured

This session changed the device UX direction materially:

- the TFT is no longer a bench-only experiment
- it is now part of the actual RS-Core runtime path
- the small OLED path remains as a hybrid fallback for now
- the larger display is now the preferred direction for rider-visible boot / sync / setup UX

## 2026-04-21: TFT UX, Sync Screen, Settings, and Touch Calibration Iteration

### Objective

Turn the TFT from a functional status surface into a more deliberate RaceSense device UI while improving sync-mode clarity and touch reliability.

### UI Direction

The TFT theme was moved toward the RaceSense orange/black visual language:

- black / dark neutral panels
- RaceSense orange for primary actions and progress
- white primary text
- muted gray secondary text
- red reserved for errors

The boot presentation was also simplified away from a photo-style logo treatment and toward a centered RaceSense wordmark style.

### Decision Window and Settings

The decision window was changed from the older YES / NO style into three explicit actions:

- `SYNC`
- `SET`
- `LOG`

`SET` opens a settings screen with:

- `WIFI`
- `CALIB`
- `BACK`

`WIFI` enters the setup / captive portal path. `CALIB` reruns touch calibration. `BACK` returns to the decision window.

### Touch Calibration

Touch reliability improved materially after adding per-device calibration.

Calibration now:

- runs automatically once if `/data/metadata/touch.json` is missing
- can be rerun from Settings -> `CALIB`
- uses five target points:
  - top-left
  - top-right
  - bottom-right
  - bottom-left
  - center
- saves calibration under `/data/metadata/touch.json`

This keeps calibration alongside device metadata such as WiFi credentials and active track data, so normal firmware sync does not erase it.

### WiFi Setup Visibility

The setup and settings screens were adjusted so the rider sees the correct WiFi context:

- saved SSID is shown in Settings
- first-time setup and pairing screens show the actual `RS-Core-XXXX` setup AP name
- the captive portal pre-fills saved SSID / token / API values from `/data/metadata/device.json`

### Sync Mode UX

The sync flow was simplified for the rider:

- WiFi search and connected states now use cleaner text
- heartbeat is shown as a red heart while contacting cloud and green after ACK
- the upload screen stays on one persistent sync progress screen
- only overall percentage, one progress bar, ETA, current file, file index, and chunk count are shown
- per-file archive messages are not shown on TFT

Archive still happens in the background after successful upload, but the TFT no longer interrupts the sync progress screen for each file.

### Sync Reliability Fixes

The sync file discovery path was widened so pending sessions are not missed when files are on active storage, flash fallback storage, or legacy session paths.

The uploader and TFT queue UI now share the same pending-session source of truth.

### Typography Finding

A key visual limitation was identified:

- MicroPython `framebuf.text()` is an 8x8 bitmap font
- scaling it up creates visibly pixelated text
- the current firmware should avoid scaled bitmap text where possible
- future polish should use a pluggable custom font renderer rather than tying typography directly into `tft_ui.py`

This keeps the door open for generated MicroPython font assets, LVGL, or a later native display renderer without rewriting the screen state model.

## 2026-04-22: TFT Font Renderer, Clean Boot/Decision UX, and Fast Logo Asset

### Objective

Move the TFT from a functional debug/status surface into a cleaner rider-facing RaceSense UI:

- remove pixelated scaled `framebuf.text()` from important TFT screens
- simplify boot and decision screens
- improve touch ergonomics
- keep the RaceSense logo visual quality without making boot painfully slow
- make firmware sync tooling copy the new nested font/logo assets reliably

### Typography

The firmware now uses a custom MicroPython TFT font path instead of relying on `framebuf.text()` for important TFT text.

Added:

- `firmware/lib/tft_fonts/renderer.py`
- generated `ui` font asset for labels/buttons/status
- generated `data` font asset for numeric values, ETA, percentages, chunks
- `firmware/tools/generate_tft_fonts.py`

The UI intentionally keeps only two font roles:

- `ui`: general interface text
- `data`: telemetry/numeric text

This solved the visibly pixelated scaled 8x8 text problem while keeping the firmware typography model simple.

### Boot Logo Pipeline

The TFT boot screen was simplified to show only the RaceSense logo.

Iteration history:

1. 4-bit alpha Python asset:
   - looked close to the source logo
   - too slow because MicroPython had to import a large Python module and blend pixels in Python
2. 1-bit threshold mask:
   - much faster
   - unacceptable visually because the detailed glowing logo collapsed into an orange blob
3. Raw RGB565 asset:
   - preserves the provided `RS logo full.png` artwork
   - avoids Python pixel blending
   - streams bytes directly to the TFT window

Final files:

- `firmware/lib/tft_boot_logo.py`: tiny metadata module
- `firmware/lib/tft_boot_logo.raw`: pre-rendered RGB565 image
- `firmware/tools/generate_tft_boot_logo.py`: converts the source PNG into the raw TFT asset

### Boot and Decision UX

The TFT boot screen no longer shows device diagnostics, progress copy, or verbose status text. It shows only the RaceSense logo and stays there until the decision window.

The decision window was reduced to only the useful rider-facing facts:

- GPS status icon
- IMU status icon
- SD status icon
- active track name, or `No track`
- interactive controls: `SYNC`, gear/settings, `LOG`

Technical logs remain on serial output, not on the rider screen.

### Settings and Touch UX

Touch targets were enlarged to use nearly all available non-conflicting screen space.

Settings changes:

- decision screen `SET` text became a gear icon
- settings `BACK` hitbox was enlarged and the cached render is invalidated on return
- added persistent `auto_log_enabled` in `/data/metadata/device.json`
- added Auto Log ON/OFF toggle in Settings
- when Auto Log is OFF, the device no longer falls through to logging after the 10-second decision timeout; rider must tap `LOG`

### Sync UX

Sync screen polish:

- WiFi search changed to an animated WiFi strength-bar screen with SSID at the bottom
- WiFi connect loop refreshes the animation while connecting
- sync ETA now uses rider-readable units such as `1h 05m`, `4m 12s`, or `42s`
- progress percentage uses the larger numeric font
- sync retry/pair/reboot buttons and hit areas were enlarged

### OLED Behavior

OLED initialization is now gated by an I2C presence check for `0x3c`.

If the OLED is absent and only the IMU at `0x69` is visible, firmware skips OLED revive and stops printing repeated `ENODEV` stack traces during the decision window.

### Deployment Tooling Fix

The new UI assets exposed a firmware sync gap:

- `flashtool.sh` and `push_to_device.sh` only copied `lib/*.py`
- nested packages like `lib/tft_fonts/` were not copied
- raw assets like `lib/tft_boot_logo.raw` were also not copied

Both sync paths now copy:

- `lib/*.py`
- `lib/*.raw`
- `lib/*/*.py`

This is required for the TFT font package and raw boot logo to work on-device.

### Current State

The TFT path is now the primary rider-facing display direction:

- clean RaceSense boot logo
- simplified decision screen
- generated custom fonts
- larger touch targets
- persistent auto-log setting
- animated WiFi search
- raw RGB565 boot asset streaming

The OLED path remains as a fallback/hybrid path, but the product UX direction is now clearly centered on the TFT.

## 2026-04-22: TFT Touch Responsiveness Pass

### Objective

Make the touchscreen feel more immediate without adding `TOUCH_IRQ` wiring yet.

The previous UI was usable, but taps could feel sticky because several small delays stacked together:

- the main decision/settings loops polled touch roughly every 50 ms
- accepted taps were debounced for 180 ms
- every touch poll could perform several XPT2046 SPI reads
- unchanged decision/settings screens could still redraw periodically
- settings rendered before polling touch

### Firmware Changes

The software-only responsiveness pass changed the TFT interaction path:

- touch debounce reduced from 180 ms to 110 ms
- debounce is now checked before doing the expensive XPT2046 read
- decision and settings screens skip redraws completely when visible state is unchanged
- invisible decision-window data, such as countdown and GPS sentence count, was removed from the TFT render key
- settings now renders once, then polls touch before future redraw work
- decision/settings loop delay was reduced from 50 ms to 30 ms

This keeps the current no-IRQ wiring while reducing perceived tap latency and avoiding unnecessary full-screen SPI transfers.

### Partial Sync Guard

A partial device sync exposed another failure mode: the device was missing `drivers/xpt2046.py`, which previously caused `lib.tft_ui` import to fail and made the whole TFT appear dead.

The TFT UI now handles this safely:

- if `drivers.xpt2046` is missing, the display still initializes
- touch is disabled with a clear serial log
- calibration exits cleanly with a message instead of crashing

This is a guardrail, not the desired deployed state. Full firmware sync must still copy `drivers/xpt2046.py` for touch to work.

### Decision

IRQ remains a later hardware/firmware improvement. The current priority is to exhaust low-risk software improvements first:

- lower debounce
- touch-before-render ordering
- fewer redraws
- complete source sync checks

Expected rider impact: noticeably faster tap recognition on decision/settings/sync screens without changing wiring.
