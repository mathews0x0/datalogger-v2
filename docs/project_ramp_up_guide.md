# RaceSense Project Ramp-Up Guide

Welcome to the **RaceSense (Datalogger V2)** project! This guide is designed to be your single source of truth for understanding the project's architecture, features, and codebase.

---

## 🏎️ Project Overview

### 🏁 Mission
To de-democratize professional motorcycle telemetry. We bring high-fidelity data analysis tools, previously reserved for factory racing teams, to every trackday rider.

### 🔭 Vision
**Ride Faster. Ride Smarter.** We believe that every rider has untapped potential that can be unlocked through data-driven insights.

### 🎯 Goal
To provide a seamless, end-to-end platform where riders can record their performance, analyze it with precision, and share their progress with a community of like-minded enthusiasts.

### 🛠️ The "RaceSense" Module (RS-Core)
The heart of the project is the **RS-Core** hardware module. It is a compact, battery-powered datalogger that mounts to a motorcycle. It captures:
- **GPS Data**: Latitude, longitude, altitude, and speed at 10Hz/25Hz.
- **IMU Data**: 6-axis motion (Leaning angles, longitudinal/lateral G-force) at high frequency.
- **Autonomous Recording**: No phone connection is required while riding. It starts recording based on movement and auto-uploads when it detects a known WiFi network.
- **Rider-Facing TFT UX (current development path)**: a 2.8" ILI9341 + XPT2046 display now renders boot, setup, sync, and logging state directly on-device using a dedicated SPI bus separate from the SD card.

### 🌐 The Platform
The platform consists of:
1.  **Backend (Flask/SQLAlchemy)**: Manages users, sessions, metadata, and background analysis jobs.
2.  **Frontend (Vanilla JS SPA)**: A browser-first dashboard served directly from `server/ui/` with no frontend build step in the current repo.
3.  **Analysis Engine (Python)**: The "brain" that processes raw CSV logs into laps, sectors, and advanced metrics.

### ☁️ Deployment Posture
- Production now runs on a **self-managed Host.co.in VPS** behind Nginx and systemd.
- DNS is pointed at the new server before application routing is handed off to Gunicorn.
- PostgreSQL is the only supported application database across development, test, and production.
- Environment-specific configuration is split across `env/development.env`, `env/test.env`, and `env/production.env`.

---

## 🧩 Feature Documentation & File Mapping

Below is a detailed breakdown of every feature in the project, mapped to its implementation files.

### 🛡️ Authentication & User Management
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Landing Page** | First point of entry explaining RaceSense features to new users. | `server/ui/index.html` (#landingPage) | `server/api/blueprints/core.py` | N/A |
| **Registration** | New user sign-up. Requires **Admin Approval** (`is_approved=False`). | `server/ui/app.js` (submitRegister) | `server/api/blueprints/auth.py` | `User` |
| **Login** | Secure JWT-based login using cookies (`HttpOnly`, `SameSite=Lax`). | `server/ui/app.js` (submitLogin) | `server/api/blueprints/auth.py` | `User` |
| **Profile Photo** | Upload profile picture. Resized/Cropped to **256x256 square** via Pillow. | `server/ui/app.js` (uploadProfilePhoto) | `server/api/blueprints/auth.py` | `User.profile_photo`|
| **User Tiers** | **Free (5 Session Limit)**, **Pro (Unlimited)**, **Team (Organization/Coaching)**. | `server/ui/app.js` (tierBadge) | `server/api/blueprints/admin.py` | `User.subscription_tier` |
| **Security** | Change password with 8+ char requirement (Digit/Uppercase check). | `server/ui/app.js` (changePassword) | `server/api/blueprints/auth.py` | `User.password_hash`|

### ⚙️ Admin Tools
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **User Approval** | Admin must manually approve users before they can log in. | `server/ui/app.js` (adminView) | `server/api/blueprints/admin.py` | `User.is_approved` |
| **Management** | List, search, filter users by tier/status. | `server/ui/app.js` (searchAdminUsers) | `server/api/blueprints/admin.py` | `User` |

### 🛰️ Device Integration (RS-Core)
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Network Scan / Local Device Ops** | LAN device scan, reachability checks, WiFi configure proxy, and OTA endpoints still exist but are restricted to local mode with `@local_only`. | `server/ui/app.js` | `server/api/blueprints/devices.py` | N/A |
| **Device Token** | Unique `rsk_` token for hardware auth. Dual-auth supported on uploads. | `server/ui/app.js` (generateDeviceToken)| `server/api/blueprints/devices.py` | `DeviceToken` |
| **WiFi Config** | Web-proxy to push SSID/Password to device in AP mode (`192.168.4.1`). | `server/ui/app.js` (configureDevice) | `server/api/blueprints/devices.py` | N/A |
| **Firmware OTA** | Pushes binary updates to device over WiFi using `UpdateManager`. | `server/ui/app.js` (flashLatest) | `server/api/update_manager.py` | N/A |
| **Status Bar** | Real-time polling of device Flash/SD usage, battery, GPS fix, and sync progress/health. | `server/ui/app.js` (pollStatus) | `server/api/blueprints/core.py` (status)| N/A |
| **Resumable Upload** | Chunked session upload can resume from previously received chunks after sync interruption. | N/A | `server/api/blueprints/core.py` (`/api/upload/status`, `/api/upload/chunk`, `/api/upload/complete`) | `DeviceToken` |

### 🏁 Tracks & Circuits
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Track List** | User sees private fallback tracks plus only the shared master tracks they have actually matched a session against. | `server/ui/app.js` (tracksView) | `server/api/blueprints/tracks.py` | `TrackMeta`, `GlobalTrack` |
| **Master Track Packages** | Admin uploads canonical track packages containing SVG layout, geo-reference, sampled GPS anchors, and transform metadata. | `server/ui/app.js` (adminView) | `server/api/blueprints/admin.py`, `server/api/track_catalog.py` | `GlobalTrack` |
| **Sectors** | Shared master tracks are initialized with 7 sectors from the uploaded package start/finish basis; fallback tracks retain existing behavior. | `server/ui/app.js` (trackDetail) | `server/api/track_catalog.py`, `server/core/` analysis modules | Track JSONs |
| **Active Track** | Push current track metadata to the RS-Core for live timing. For shared master tracks, firmware receives the canonical track definition plus user-specific TBL overlay. | `server/ui/app.js` (setActive) | `server/api/blueprints/devices.py` (ensureTrackSynced) | N/A |
| **Pit Lane** | Mark entry/exit to filter sessions for "Clean" track time only. | `server/ui/app.js` (markPitLane) | `server/api/blueprints/tracks.py` | JSON metadata |

### ⏱️ Sessions & Analysis
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Lap Table** | Detailed lap times with **Standard Deviation (Consistency)** scoring. | `server/ui/app.js` (viewSession) | `server/api/blueprints/sessions.py` | `SessionMeta` |
| **Ghost Lap™** | **Distance-based** telemetry alignment for frame-accurate comparison. For matched master tracks, both laps are projected onto the canonical package layout first. | `server/ui/app.js` (showComparison) | `server/api/blueprints/leaderboards.py` (/api/compare) | N/A |
| **Lap Detail** | Dual Maps: **Dynamics (G-Force Halo)** and **Speed Profile**. Matched master tracks use canonical SVG layout with projected GPS overlays. | `server/ui/app.js` (viewLapDetail) | `server/api/blueprints/sessions.py` | JSON Telemetry |
| **Playback** | Interactive 2D replay. Legacy fallback tracks still use raw GPS bounds; matched master tracks now use canonical SVG layout with projected telemetry overlays. | `server/ui/app.js` (openPlayback) | `server/api/blueprints/sessions.py` | CSV / JSON |
| **Session Health** | GPS quality summary (fix dropouts), Track Temp, and IMU confidence. | `server/ui/app.js` (sectionContext)| `server/api/blueprints/sessions.py` | Analysis Result |
| **Coach Corner** | Text/Voice notes anchored to specific laps or sectors. | `server/ui/app.js` (annotations) | `server/api/blueprints/annotations.py`| `Annotation` |

### 📅 Trackdays
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Trackdays** | Grouping sessions. **Aggregated Stats** (Total Trackday Best, TBL, Consistency). | `server/ui/app.js` (viewTrackday) | `server/api/blueprints/trackdays.py` | `TrackDayMeta` |
| **Race View CTA** | Contextual multi-rider replay entry point surfaced inside Trackday detail when 2+ public sessions overlap on the same canonical track. | `server/ui/app.js` (loadTrackdayRaceViewCta, openRaceView) | `server/api/blueprints/race_view.py` | `SessionMeta`, `GlobalTrack` |
| **Bulk Tagging** | Multi-select sessions to associate with an event. | `server/ui/app.js` (showTagSessionModal)| `server/api/blueprints/trackdays.py` | JSON relation |

### 👥 Community & Social
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Public Feed** | Explore shared sessions. Following/Follower system. | `server/ui/app.js` (loadFollowingFeed)| `server/api/blueprints/social.py` | `Follow` |
| **Race View** | Public multi-rider replay for overlapping public sessions on the same canonical track. Surfaced first through Community discovery cards and Trackday CTAs rather than a top-level tab. | `server/ui/app.js` (loadCommunityRaceViewRail, renderRaceView) | `server/api/blueprints/race_view.py` | `SessionMeta`, `GlobalTrack` |
| **Leaderboards** | Track rankings filtered by `all`, `month`, `week`. One entry per user. | `server/ui/app.js` (loadLeaderboard) | `server/api/blueprints/leaderboards.py`| `SessionMeta` |
| **Teams** | Roles: `owner`, `coach`, `rider`. Coaching access to member data. **Team creation requires Team tier.** | `server/ui/app.js` (teamsView) | `server/api/blueprints/teams.py` | `Team` |
| **Team Invites** | UUID-based invitation links with 7-day expiration. | `server/ui/app.js` (generateInvite) | `server/api/blueprints/teams.py` | `TeamInvite` |

### 🔄 Data Management
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Bulk Actions** | **Locking** (prevent deletion), **Archiving**, and **Multi-select** processing. | `server/ui/app.js` (updateBulkUI)| `server/api/blueprints/files.py` | N/A |
| **Archives** | Move raw CSVs to an archive folder to declutter the process view. | `server/ui/app.js` (archiveFile) | `server/api/blueprints/files.py` | N/A |
| **Quick Peek** | View raw CSV telemetry in a tabular format before analyzing. | `server/ui/app.js` (peekCsv) | `server/api/blueprints/files.py` | N/A |
| **Analysis** | **Background Worker** polling `Job` queue for `run_analysis.py`. | `server/worker.py` | `server/api/blueprints/sessions.py` | `Job` |

---

## 🏗️ Core Architecture Concepts

### 1. The Silo Storage System
Data is stored in a per-user silo rooted at `server/data/users/<user_id>/`:
  - `sessions/`: JSON analysis files and `_telemetry.json` blobs.
  - `tracks/`: User-defined track configurations.
  - `trackdays.json`: Trackday groupings for that user.
  - `learning/`: Raw CSV logs before rotation to archives.

Important current-state clarification:
- Shared master tracks are **not** stored in user silos.
- Canonical package assets live in `server/data/tracks/<slug>/`.
- User silos still hold user-specific artifacts for the matched track, especially TBL and active-track overlays.
- Session JSON is normalized at read time so older sessions can still resolve to a newly matched shared master track.

### 2. The Analysis Pipeline
- **Job Creation**: `POST /api/process` creates a `Job` row (status: `queued`).
- **Worker**: `worker.py` polls for jobs, spawns `run_analysis.py` as a subprocess.
- **Processing**:
  - The analysis implementation lives under `server/core/` (`ingestion/`, `processing/`, `core/`), but several files still reference an older `src.analysis...` import namespace. Treat this as a known codebase inconsistency until that namespace migration is completed.
  - `CSVLoader`: Sanitizes and parses telemetry logs plus marker rows.
  - Marker rows (`row_type=M`) are tolerated and ignored by the current loader so interrupted-session breadcrumbs do not break ingestion.
  - `LapDetector`: Uses `StartLine` (lat/lon) and `distance_to_segment` logic.
  - `Comparator`: Interpolates two telemetry streams based on **Distance** (using cumulative sum of `speed * dt`) to calculate deltas.

Track-resolution layering as of the canonical package rollout:
- First attempt to identify a **shared global track** using start/finish proximity.
- Then validate that candidate against the uploaded package metadata and sampled GPS anchor basis.
- If accepted, mark the session as `track_scope=global` and `track_source=global_package`.
- If no shared track matches, fall back to the existing per-user track generation path.
- Fallback generation also creates an admin review signal so a missing shared master track can be uploaded later.

### 3. Canonical Track Package System
- **Authoring Tool**: `track-layout-generator/` is a static local app used to align layout artwork to telemetry and export canonical package JSON.
- **Launcher**: `./track-generator.sh` starts that authoring tool on port `8080` by default.
- **Package Contents**:
  - embedded layout SVG
  - geo-reference basis
  - manual transform metadata
  - semantic anchors such as start/finish or pit markers
  - sampled GPS anchor points mapped into canonical layout space
- **Admin Flow**:
  - upload package in Admin
  - package becomes a `GlobalTrack`
  - shared layout is visible to a user only after one of their sessions resolves to that track
- **Rendering Rule**:
  - `global_package` track source => canonical layout everywhere possible
  - `user_fallback` track source => legacy geometry/GPS rendering

### 4. Current Known Gap
- The canonical package pipeline is implemented end-to-end, but overlay alignment is still being tuned.
- Package anchor fit is in place and session reads now resolve to canonical layouts correctly.
- A client-side corrective pass currently refines session overlay rotation/translation against the package’s sampled GPS cloud.
- The remaining likely follow-up is to move that final correction into a durable server-side alignment artifact rather than recalculating it in the browser.

### 5. Identity & Permissions
- **JWT**: Identity stored as `user_id` string in the token.
- **Team Access**: Coaches and Owners can bypass `is_public` checks for their members' sessions (implemented in `leaderboards.py` and `sessions.py`).
- **Subscription Tiers**: Enforced via `@require_tier` decorator in the backend and `user.subscription_tier` in the frontend UI.

### 6. Current Device UI State
- The active development display path is now the 2.8" TFT + touch panel under `firmware/lib/tft_ui.py`.
- The firmware is now TFT-only for rider-facing display behavior; the old OLED fallback path has been removed.
- The TFT currently handles:
  - per-device TFT panel selection on first boot when `/data/metadata/display.json` is missing
  - fast RaceSense boot wordmark from a raw RGB565 asset streamed by `boot.py` once display selection is complete
  - Home as the post-boot landing page and Sync return target
  - simplified SD / IMU / GPS status icons
  - active track display, or `No track`
  - Home `SYNC` / gear / `LOG` touch routing
  - settings screen with `WIFI`, `TRACK`, `mount profile`, `CALIB`, `BACK`, and Auto Log ON/OFF
  - first-time setup and pairing screens showing saved WiFi or the actual setup AP name
  - per-device display config stored at `/data/metadata/display.json`
  - one-time second-boot and on-demand 5-point touch calibration stored at `/data/metadata/touch.json`
  - persistent IMU mount profiles stored under device metadata and reused across sessions
  - guided IMU profile calibration flow with `STATIC`, `ENGINE`, `LEAN LEFT`, `LEAN RIGHT`, and `PUSH` capture phases
  - no-IRQ touch responsiveness tuning: 110 ms debounce, touch-before-redraw ordering, and state-based redraw skipping
  - cached top bar with slower full refresh and faster RAM-only refresh
  - partial content redraws for Home/settings/sync transitions
  - sync queue / upload / heartbeat / result / idle states
  - animated WiFi search with SSID at the bottom and `EXIT` back to Home
  - single-screen sync upload progress with large overall percentage, ETA, current file, file index, and chunk count
  - logging status without exposing session filenames as rider-facing log output
  - first-5-seconds logging-start IMU validation screen
  - validation screen split into `TOP VIEW` mount direction plus `FRONT` / `SIDE` static mount-angle indicators
- The TFT uses generated MicroPython font assets under `firmware/lib/tft_fonts/` to avoid scaled 8x8 bitmap text.
- The boot wordmark is generated by `firmware/tools/generate_tft_wordmark.swift` into `firmware/lib/tft_wordmark.raw` and streamed directly to the TFT after a panel preset has been selected. On fresh units without `/data/metadata/display.json`, `boot.py` skips the branded splash and `main.py` runs the panel-selection flow instead.
- The heartbeat screen is rider-facing: a red heart while contacting cloud, green after ACK. Technical cloud/auth details stay in serial logs.
- Per-file archive messages are not shown to the rider during sync. Archive happens in the background while the TFT remains on the sync progress screen.
- Firmware sync tooling must copy nested `lib` packages, `.raw` assets, and all `drivers/*.py`; this is handled in the current `flashtool.sh` and `push_to_device.sh`.
- If a partial sync omits `drivers/xpt2046.py`, the TFT display should still boot, but touch remains disabled until the driver is restored.

### 7. Current IMU Processing Contract
- The previous backend-first assumption that the device is always mounted forward and mostly flat is no longer the only intended path.
- Sessions can now carry on-device IMU calibration metadata through CSV marker rows such as `IMU_PROFILE` and `IMU_VALIDATION`.
- When that metadata exists, backend session processing prefers the stored calibration profile:
  - saved `rotation_matrix`
  - saved `gyro_bias`
  - saved gravity / mount geometry metadata
  - rollout validation result mapped into confidence tiers
- Current exported source modes are:
  - `imu_trusted`
  - `imu_warn`
  - `gps_assisted`
- This means the TFT validation screen is not just cosmetic; it reflects the same stored mount interpretation that the backend now consumes for calibrated sessions.

---

## 🚀 Getting Started for Developers

1.  **Backend Setup**:
    - Install requirements: `pip install -r server/requirements.txt`
    - Create `env/development.env` from `env/development.env.example`
    - Ensure your local PostgreSQL database exists and matches `DATABASE_URL`
    - Run migrations: `flask db upgrade`
    - Start server: `python server/run.py`
    - Start worker: `python server/worker.py`

2.  **Frontend Setup**:
    - The frontend is served statically by Flask from `server/ui/`.
    - No build step is required for web development.
    - There are no active Capacitor/mobile project files in the current repo snapshot.

3.  **Database**:
    - PostgreSQL is required in every environment via `DATABASE_URL`.
    - Local development should use its own Postgres database, not a separate SQLite mode.
    - Tests should use `env/test.env` or `TEST_DATABASE_URL`.
    - Production uses `env/production.env` on the server and is deployed onto the Host.co.in VPS.
    - Use `psql` or `flask shell` to inspect data.

---

*This guide is a living document. Please update it as you add new features or refactor existing ones.*
