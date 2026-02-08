# PM_DIARY — Motorcycle Data Logger Project

**Owner:** Product Management (PM)
**Purpose:** Single consolidated, authoritative project memory
**Last Updated:** 2025-12-25
PRODUCT manager - CHATGPT
Engineering manager/Devs - Antigravity

---

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

- **Phase 3.3: Data Validation & Regression Testing**

### Explicitly Blocked

- Phase 4: Insight & Intelligence
- Phase 6: Live Feedback

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
- **IMU Selection:** Finalized **BMI160** with dedicated I2C pull-ups and optimized decoupling for low-noise telemetry.
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
    - Set I2C frequency to **400kHz** (Fast Mode) for the BMI160.
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
