# Project Phases & Roadmap

**Purpose:** This document serves as the single authoritative source for the project's roadmap, consolidating all past, present, and future phases.
**Source:** Consolidated from `pm_diary.md` and individual phase specifications.
**Last Updated:** 2026-01-09

---

## Phase 1: Truth Capture (Completed)

**Focus:** Reliable raw telemetry logging without interpretation.

- **Objective:** Log GPS (10Hz) and IMU (100Hz) data to CSV with absolute reliability.
- **Key Decisions:**
  - Headless Raspberry Pi architecture.
  - Ignition-triggered power control.
  - Raw data is ground truth; no filtering at capture time.

## Phase 2: Structural Understanding (Completed)

**Focus:** Auto-detection of track geometry.

- **Objective:** Automatically identify tracks and detect laps from raw coordinates.
- **Key Features:**
  - `TrackGenerator`: Auto-generates `track.json` from median lap geometry.
  - `LapDetector`: Robust start/finish line detection.
  - Immutable Track IDs.

## Phase 3: Comparative Primitives (Completed)

**Focus:** Building the mathematical foundation for comparison.

- **Objective:** Enable specific lap comparisons.
- **Key Features:**
  - **Fixed Sectors:** 7-sector standard for all tracks.
  - **TBL (Theoretical Best Lap):** Synthetic lap composed of best individual sectors.
  - **Filesystem Architecture:** `output/` directory as the database (`registry.json`, `sessions/`, `tracks/`).
- **Phase 3.2: Companion App (MVP):**
  - Flask API + Vanilla JS PWA.
  - Wifi Hotspot access.
  - Real-time session processing and renaming.

## Phase 4: Insight & Intelligence (Blocked)

- **Status:** Explicitly blocked to prevent premature AI/Coaching features.

## Phase 5: Hardware Stability (Ongoing)

- **Focus:** Power management, verified boot, and ruggedization.

## Phase 6: Persistent Learning (Completed)

- **Focus:** System gets smarter with every session.
- **Key Features:** TBL and Track Registry persist across reboots.

---

## Phase 7: Rider Performance Enhancements (Deployed)

**Focus:** Transform accurate session data into clear rider understanding — without compromising trust.

### 7.1 Visual Clarity & Trend Awareness

- **Objective:** Help riders see improvement or regression over time.
- **Key Features:**
  - **Consistency Score:** Derived Standard Deviation of lap times.
  - **Sector Heatmap:** Breakdown of sector performance relative to session median (Green=Fast, Red=Slow).
  - **Session Trend Chart:** Interactive SVG chart showing lap time progression.

### 7.2 Spatial Understanding

- **Objective:** Show _where_ time is gained or lost.
- **Key Features:**
  - **Track Map Heat Overlays:** Visualizing performance on the track geometry.
  - **Lap Path Overlays:** Comparing lines between best and selected laps.

### 7.3 Sensor Intelligence

- **Objective:** Introduce IMU data responsibly.
- **Key Features:**
  - **7.3.1 Trust Layer:** `IMUCalibrator` aligns gravity vector (Z-up) during static periods.
  - **7.3.2 Load & Stability:** Metrics for Lateral/Longitudinal G-force and Jerk (Smoothness).
  - **Confidence Scoring:** Explicitly flagging data quality.

### 7.4 Lap Drill-Down & Detailed Visualization

- **Objective:** Per-lap actionable insights.
- **Key Features:**
  - **Interactive Dashboard:** Dual maps for Rider Dynamics (Accel/Brake) and Speed Profile.
  - **Ghost Map Replay:** Trace-based animation comparing two laps side-by-side.
  - **Delta Charts:** Time vs Distance graphs showing exactly where speed was carried or lost.
  - **Sector Table:** Detailed comparison vs Theoretical Best Lap (TBL).

### 7.5 Output & Portability

- **Objective:** Data portability.
- **Key Features:**
  - **Export:** ZIP backup of raw and processed data.
  - **Reporting:** One-click PDF reports.
  - **Renaming:** Robust session and track renaming API.

---

## Phase 8: Diagnostic Intelligence (Planned)

**Focus:** Help coaches notice the right things faster using the "Attention Funnel".

### 8.0 Guardrails

- **Rule:** No prescriptive language (e.g., "Brake Later"). Use statistical terms (Variance, Deviation).

### 8.1 Variance Highlighting

- **Objective:** Instantly spot inconsistency.
- **Features:**
  - **Sector Variance:** Calculate Standard Deviation ($\sigma$) and Coefficient of Variation ($C_v$).
  - **Cluster Detection:** Identify "Top 3 Variance Regions".
  - **Heat Overlay:** Color segments Yellow/Orange based on variance.

### 8.2 Delta Extremes

- **Objective:** Find the biggest "Moments".
- **Features:**
  - **Delta Scanner:** Find global max positive/negative deltas.
  - **UI Markers:** "⚠️" icons on the map at event locations.

### 8.3 Consistency Classification

- **Objective:** Neutral labeling of stability.
- **Logic:**
  - **Stable:** Variance within 1 $\sigma$.
  - **Variable:** Variance > 1 $\sigma$.
  - **Highly Variable:** Variance > 2 $\sigma$.

### 8.4 Distribution Views

- **Objective:** Show input spread.
- **Features:**
  - **Braking Histogram:** Distribution of peak G-force in braking zones.
  - **Corner Entry Speed Scatter:** Spread of entry speeds.

---

## Phase 9: Real-Time Feedback (Completed)

**Focus:** Provide real-time acknowledgement of performance state using minimal, non-intrusive LED signals.

### 9.0 Guardrails

- **Rule:** Communicate _state_, not meaning. No technique advice. "What just happened?", not "What should you do?".

### 9.1 Hardware

- **Device:** Addressable RGB LED Strip (WS2812B/NeoPixel).
- **Driver:** Python-based `LEDStripDriver` with `rpi_ws281x`.

### 9.2 Sector Boundary (Heartbeat)

- **Trigger:** Crossing a sector boundary.
- **Signal:** Short Blue Flash (~200ms).
- **Meaning:** Temporal grounding ("Sector complete").

### 9.3 Performance State (TBL-Relative)

- **Trigger:** Immediately after boundary flash.
- **Logic:** Compare last sector time to TBL sector record.
- **Signals:**
  - 🟢 **Green:** On Pace ($\Delta \le +0.2s$)
  - 🟠 **Orange:** Off Pace ($+0.2s < \Delta \le +0.6s$)
  - 🔴 **Red:** Poor ($\Delta > +0.6s$)
- **Behavior:** Steady color hold until next boundary.

### 9.4 Implementation Details

- **Architecture:** Threaded `LiveAnalysisService` decoupled from main logger.
- **Event States (Revised Phase 9.8):**
  - **No GPS:** Red Blink (<4 Sats).
  - **Idle:** White Breath (GPS Locked, Track Found, Not Logging).
  - **Logging:** Blue Scanner (Active).
  - **GPS Strength:** Cyan Bar Graph (Toggle in Track Mode).
  - **Feedback:** Sector Flash + Delta Color.

---

# V1.0.0 PRODUCT RELEASE (2026-01-09)

_Base Platform, Analysis Engine, and Rider Feedback System Verified._

---

## Phase 10: Coaching Mode (Postponed)

**Focus:** Enable human coaches to analyze data more effectively (Human-in-the-Loop).

### 10.1 Instructor Mode

- **Feature:** UI Toggle & Permanent Banner ("INSTRUCTOR ACTIVE").
- **Constraint:** Phase 10 features are disabled unless this mode is active.

### 10.2 Annotations

- **Feature:** Time/Distance-linked notes stored in `annotations.json`.
- **Goal:** Allow coaches to mark specific corners or moments.

### 10.3 Playback

- **Feature:** Replay session on the map with Instructor Notes appearing at relevant timestamps.

### 10.4 Liability & Ethics

- **Rule:** All notes attributed to a user. No AI-generated tips.
- **Disclaimer:** "Analysis provided by Human Instructor."

---

---

## Phase 11: Enterprise Readiness (Planned)

**Focus:** Transforming the device into a maintainable, secure, and supportable fleet product.

- **11.0 Operational Visibility:** Structured logging, rotation, and health snapshots.
- **11.1 Remote Diagnostics:** Read-only support tunnels.
- **11.2 Secure Update:** Signed bundles and A/B partition recovery.
- **11.3 Device Identity:** Unique crypto-identity per device.
- **11.4 Hardening:** Read-only rootfs and encryption.
- **11.5 Licensing:** Signed license enforcement.
- **11.6 Federation:** Central track registry.
- **11.7 Group Analytics:** Cross-device comparison.

---

## Phase 12: Companion App Enhancements (Deployed)

**Focus:** Improve usability, safety, and remote management of the datalogger.

### 12.1 System Control & Feedback

- **Start/Stop Logging:** Manual control buttons in the UI header.
- **Recording Indicator:** Visual "RECORDING" status dot in the UI.
- **Auto-Start Config:** UI toggle to enable/disable boot-time logging.

### 12.2 Advanced File Management

- **Locking:** Prevent accidental deletion of important session files.
- **Bulk Operations:** Select and delete multiple files.
- **Raw Data View:** Inspect CSV headers and data rows directly in the browser (Color-coded).
- **Path Visualization:** Instant SVG rendering of the GPS path from raw logs.

### 12.3 Maintenance & Diagnostics

- **Tailscale Integration:** Script for easy remote VPN access.
- **Service Control:** UI to restart specific services (API, Logger, Buttons).
- **Diagnostics:** Enhanced LED and Sensor tests with detailed error reporting.
