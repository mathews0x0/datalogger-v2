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

### 🌐 The Platform
The platform consists of:
1.  **Backend (Flask/SQLAlchemy)**: Manages users, sessions, metadata, and background analysis jobs.
2.  **Frontend (Vanilla JS/Capacitor)**: A high-performance web dashboard that also runs as a native mobile app.
3.  **Analysis Engine (Python)**: The "brain" that processes raw CSV logs into laps, sectors, and advanced metrics.

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
| **Network Scan** | 2-Phase Scan: **Priority (ARP table)** then **Parallel Brute Force (50 threads)**. | `server/ui/app.js` (scanForDevice) | `server/api/blueprints/devices.py` | N/A |
| **Device Token** | Unique `rsk_` token for hardware auth. Dual-auth supported on uploads. | `server/ui/app.js` (generateDeviceToken)| `server/api/blueprints/devices.py` | `DeviceToken` |
| **WiFi Config** | Web-proxy to push SSID/Password to device in AP mode (`192.168.4.1`). | `server/ui/app.js` (configureDevice) | `server/api/blueprints/devices.py` | N/A |
| **Firmware OTA** | Pushes binary updates to device over WiFi using `UpdateManager`. | `server/ui/app.js` (flashLatest) | `server/api/update_manager.py` | N/A |
| **Status Bar** | Real-time polling of device Flash/SD usage, battery, GPS fix, and sync progress/health. | `server/ui/app.js` (pollStatus) | `server/api/blueprints/core.py` (status)| N/A |
| **Resumable Upload** | Chunked session upload can resume from previously received chunks after sync interruption. | N/A | `server/api/blueprints/core.py` (`/api/upload/status`, `/api/upload/chunk`, `/api/upload/complete`) | `DeviceToken` |

### 🏁 Tracks & Circuits
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Track List** | Global registry + User-specific tracks ridden. | `server/ui/app.js` (tracksView) | `server/api/blueprints/tracks.py` | `TrackMeta` |
| **Sectors** | Define split points. Auto-detection of known tracks (MMRT, Kari, etc.). | `server/ui/app.js` (trackDetail) | `src/analysis/core/track_manager.py` | Track JSONs |
| **Active Track** | Push current track metadata to the RS-Core for live timing. | `server/ui/app.js` (setActive) | `server/api/blueprints/devices.py` (ensureTrackSynced) | N/A |
| **Pit Lane** | Mark entry/exit to filter sessions for "Clean" track time only. | `server/ui/app.js` (markPitLane) | `server/api/blueprints/tracks.py` | JSON metadata |

### ⏱️ Sessions & Analysis
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Lap Table** | Detailed lap times with **Standard Deviation (Consistency)** scoring. | `server/ui/app.js` (viewSession) | `server/api/blueprints/sessions.py` | `SessionMeta` |
| **Ghost Lap™** | **Distance-based** telemetry alignment for frame-accurate comparison. | `server/ui/app.js` (showComparison) | `server/api/blueprints/leaderboards.py` (/api/compare) | N/A |
| **Lap Detail** | Dual Maps: **Dynamics (G-Force Halo)** and **Speed Profile**. | `server/ui/app.js` (viewLapDetail) | `server/api/blueprints/sessions.py` | JSON Telemetry |
| **Playback** | Interactive 2D Map Replay using **Leaflet** and **Synced Charts**. | `server/ui/app.js` (openPlayback) | N/A (UI only) | CSV / JSON |
| **Session Health** | GPS quality summary (fix dropouts), Track Temp, and IMU confidence. | `server/ui/app.js` (sectionContext)| `server/api/blueprints/sessions.py` | Analysis Result |
| **Coach Corner** | Text/Voice notes anchored to specific laps or sectors. | `server/ui/app.js` (annotations) | `server/api/blueprints/annotations.py`| `Annotation` |

### 📅 Trackdays
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Trackdays** | Grouping sessions. **Aggregated Stats** (Total Trackday Best, TBL, Consistency). | `server/ui/app.js` (viewTrackday) | `server/api/blueprints/trackdays.py` | `TrackDayMeta` |
| **Bulk Tagging** | Multi-select sessions to associate with an event. | `server/ui/app.js` (showTagSessionModal)| `server/api/blueprints/trackdays.py` | JSON relation |

### 👥 Community & Social
| Feature | Description | Frontend Files | Backend Files | Models |
| :--- | :--- | :--- | :--- | :--- |
| **Public Feed** | Explore shared sessions. Following/Follower system. | `server/ui/app.js` (loadFollowingFeed)| `server/api/blueprints/social.py` | `Follow` |
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
Data is stored in a per-user silo:
- `server/instance/data/users/<user_id>/`
  - `sessions/`: JSON analysis files and `_telemetry.json` blobs.
  - `tracks/`: User-defined track configurations.
  - `trackdays.json`: Trackday groupings for that user.
  - `learning/`: Raw CSV logs before rotation to archives.

### 2. The Analysis Pipeline
- **Job Creation**: `POST /api/process` creates a `Job` row (status: `queued`).
- **Worker**: `worker.py` polls for jobs, spawns `run_analysis.py` as a subprocess.
- **Processing**:
  - `CSVLoader`: Sanitizes and parses 10/25Hz logs.
  - Marker rows (`row_type=M`) are tolerated and ignored by the current loader so interrupted-session breadcrumbs do not break ingestion.
  - `LapDetector`: Uses `StartLine` (lat/lon) and `distance_to_segment` logic.
  - `Comparator`: Interpolates two telemetry streams based on **Distance** (using cumulative sum of `speed * dt`) to calculate deltas.

### 3. Identity & Permissions
- **JWT**: Identity stored as `user_id` string in the token.
- **Team Access**: Coaches and Owners can bypass `is_public` checks for their members' sessions (implemented in `leaderboards.py` and `sessions.py`).
- **Subscription Tiers**: Enforced via `@require_tier` decorator in the backend and `user.subscription_tier` in the frontend UI.

---

## 🚀 Getting Started for Developers

1.  **Backend Setup**:
    - Install requirements: `pip install -r server/requirements.txt`
    - Run migrations: `flask db upgrade`
    - Start server: `python server/run.py`
    - Start worker: `python server/worker.py`

2.  **Frontend Setup**:
    - The frontend is served statically by Flask from `server/ui/`.
    - No build step required for web development.
    - For mobile (iOS/Android), use Capacitor commands in `server/ui/`.

3.  **Database**:
    - SQLite is used by default: `server/instance/data/racesense.db`.
    - Use DB Browser for SQLite or `flask shell` to inspect.

---

*This guide is a living document. Please update it as you add new features or refactor existing ones.*
