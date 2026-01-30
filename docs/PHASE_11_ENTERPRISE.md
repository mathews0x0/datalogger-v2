# Phase 11: Enterprise Readiness & Fleet Management

**Focus:** Moving from a "Single User Device" to a managed, secure, and supportable "Fleet Product".

**Strategy:** Ordered execution from Visibility -> Control -> Security -> Intelligence.

---

## 11.0 Operational Visibility & Robust Logging (Foundational)

**Objective:** "If you can't see what's happening, nothing else matters."
**Why First:** Zero risk, verified prerequisite for all future support and debugging.

- **Status:** [ ] Pending
- **Scope:**
  - **Structured Logs:** Unified logging format (JSON/Line) for Boot, GPS, IMU, LED, Network.
  - **Log Rotation:** `logrotate` configuration to prevent disk fill.
  - **Health Snapshots:** Periodic capture of CPU, Temp, Disk, GPS Time-to-Lock.
  - **Crash Dumps:** Automatic capture of stack traces and last-known-state.
  - **Fingerprinting:** Embed VERSION and commit hash in every log entry.

## 11.1 Remote Diagnostics (Read-Only)

**Objective:** "Support without control."
**Why Now:** Non-invasive support capability.

- **Scope:**
  - Opt-in "Support Mode" (Physical Toggle or UI).
  - Reverse SSH Tunnel (e.g., ngrok or custom relay) initiated by device.
  - Read-only filesystem export.
  - Session-safe auto-disable (Time-limited).

### 11.1.5 Network Provisioning (Support Enabler)

**Objective:** "The device never hunts. The operator commands."
**Role:** Enables the device to autonomously connect to the internet for remote support.

- **Architecture:**
  - **Front-End:** Settings -> Network Panel (Scan, Add SSID, Save).
  - **Back-End:** Flask API wrapping `nmcli` for persistent connection management.
  - **Boot Logic:** Strict adherence to hardware latch (Hotspot vs Client). Client mode uses NM priority.
- **Security:**
  - Passwords never logged/displayed.
  - Provisioning only allowed when authenticated/unlocked.
  - Audit logs for all network changes.
- **Performance:** Fast connect strategy (disable power save, high priority for support SSIDs).

## 11.2 Secure Update & Recovery Path

**Objective:** "You can now fix things you understand."
**Why Before Security:** Updates are impossible once the filesystem is locked.

- **Scope:**
  - **Signed Bundles:** Cryptographically signed update packages.
  - **A/B Partitioning:** Fallback if update fails (or Snapshot Rollback).
  - **Recovery Mode:** Hardware trigger (GPIO Button) to force factory reset/rollback.
  - **Brick-proof:** Watchdog timers for update application.

## 11.3 Device Identity & Provisioning

**Objective:** "Everything becomes per-device."

- **Scope:**
  - **Device UUID:** Immutable hardware identifier.
  - **Keypair Generation:** Unique crypto identity generated on first boot.
  - **Registration:** Handshake with central server (when online).
  - **Persistence:** Identity stored in secure/read-only location.

## 11.4 Filesystem Hardening & IP Protection

**Objective:** "Raise the theft bar."

- **Scope:**
  - Read-only Root Filesystem (overlayfs).
  - Encrypted Data Partition (LUKS).
  - Source Code Compilation (Python -> Cython/PyInstaller).
  - Service Sandboxing (systemd hardening).

## 11.5 Licensing & Policy Control

**Objective:** "Authority without always-on connectivity."

- **Scope:**
  - Signed License Artifacts (Time-bound, Feature-bound).
  - Offline Grace Periods.
  - UI State for License Status (Active/Expired).
  - Revocation Lists.

## 11.6 Central Track Registry & Federation

**Objective:** "Intelligence starts compounding."

- **Scope:**
  - Track Signature Hashing (Geometry-based ID).
  - Canonical Registry (Cloud Sync).
  - Automatic Conflict Resolution.

## 11.7 Scoped Comparison & Group Analytics

**Objective:** "Teams and academies get real value."

- **Scope:**
  - Group-scoped Sharing (Team Mode).
  - Cross-device Deltas.
  - Aggregated Distributions (Fleet Stats).
