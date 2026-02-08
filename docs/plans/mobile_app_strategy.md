# Racesense Mobile App Strategy

**Date:** 2026-02-09  
**Status:** Strategic Plan  
**Architect:** Strategic Planning Agent  
**Revision:** 2.0 — "Hybrid Burst" Model

---

## Executive Summary

This document defines the development strategy for bringing Racesense to iOS and Android. Given the existing Vanilla JS/CSS UI and the need for native BLE + WiFi capabilities, **Capacitor** is the recommended framework.

**Key Architectural Decision: The "Thin App" Philosophy**

The mobile app is a **data conduit**, NOT a processing engine. All telemetry analysis, lap detection, and TBL computation happens in the cloud backend. This simplifies the mobile app, ensures consistent analysis across devices, and allows rapid iteration of the analysis algorithms without app updates.

---

## Table of Contents

1. [Framework Evaluation](#1-framework-evaluation)
2. [The Hybrid Burst Model](#2-the-hybrid-burst-model)
3. [Data Pipeline Architecture](#3-data-pipeline-architecture)
4. [Offline-First Strategy](#4-offline-first-strategy)
5. [Required Plugins](#5-required-plugins)
6. [Development Roadmap](#6-development-roadmap)
7. [Risk Assessment](#7-risk-assessment)

---

## 1. Framework Evaluation

### Why Capacitor?

| Framework | Web UI Reuse | Native Access | Learning Curve | Community | Verdict |
|-----------|--------------|---------------|----------------|-----------|---------|
| **Capacitor** | ✅ Full | ✅ Excellent | Low | Growing | **RECOMMENDED** |
| React Native | ❌ Rewrite | ✅ Good | Medium | Large | Not suitable |
| Flutter | ❌ Rewrite | ✅ Excellent | High | Large | Overkill |
| Cordova | ✅ Full | ⚠️ Aging | Low | Declining | Legacy |
| PWA Only | ✅ Full | ❌ Limited BLE | None | N/A | Insufficient |

### Capacitor Advantages for Racesense

1. **Zero UI Rewrite**: Existing `app.js`, `index.html`, and `styles.css` work as-is
2. **Modern Plugin Ecosystem**: First-class BLE, Filesystem, and Network plugins
3. **Native Shell**: Full access to iOS/Android APIs when needed
4. **Hot Reload**: Web code changes instantly during development
5. **Ionic Team Backing**: Active maintenance and enterprise support
6. **Web Bluetooth Migration Path**: Current `ble-connector.js` logic translates directly to Capacitor BLE plugin

### Capacitor vs Cordova

Capacitor is the spiritual successor to Cordova, built by the same team:

| Aspect | Capacitor | Cordova |
|--------|-----------|---------|
| Config | `capacitor.config.ts` (typed) | `config.xml` (legacy) |
| Native Code | Encouraged, easy access | Discouraged, difficult |
| Plugin API | Modern Promise-based | Callback hell |
| Build System | Native IDE integration | CLI-only |
| Maintenance | Active (Ionic) | Declining |

**Decision: Use Capacitor 6.x**

---

## 2. The Hybrid Burst Model

### 2.1 Core Philosophy: Zero-Config Data Sync

The ESP32's WiFi Access Point mode is the **primary** high-speed data transfer mechanism. This eliminates complex WiFi provisioning, hotspot configuration, and network juggling.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE HYBRID BURST MODEL                               │
│                                                                         │
│   BLE = Command Channel (always-on, low-power)                          │
│   WiFi AP = Data Burst Channel (on-demand, high-speed)                  │
│                                                                         │
│   User Flow:                                                            │
│   ┌────────┐    ┌──────────┐    ┌───────────┐    ┌────────────────┐    │
│   │  BLE   │───▶│ App says │───▶│ Phone     │───▶│ High-speed     │    │
│   │Handshake│   │"Start AP"│    │joins ESP  │    │CSV download    │    │
│   └────────┘    └──────────┘    │WiFi       │    │(~1 min)        │    │
│                                 └───────────┘    └───────┬────────┘    │
│                                                          │             │
│   ┌────────────────┐    ┌──────────────┐    ┌───────────▼────────┐    │
│   │ Phone auto-    │◀───│ App says     │◀───│ Download complete  │    │
│   │ rejoins LTE/5G │    │ "Kill AP"    │    │ (via BLE command)  │    │
│   └────────────────┘    └──────────────┘    └────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Architecture Overview: Thin App

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      RACESENSE "THIN APP" ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────────────┐    │
│   │  BLE Layer  │      │ WiFi Layer  │      │   Cloud Sync Layer  │    │
│   │  (Control)  │      │   (Data)    │      │    (Upload/Download)│    │
│   └──────┬──────┘      └──────┬──────┘      └──────────┬──────────┘    │
│          │                    │                        │               │
│   • Handshake          • Join ESP AP           • Upload raw CSVs      │
│   • Start/Stop AP      • Download CSVs         • Receive results      │
│   • Status updates     • HTTP file transfer    • Get TBL/Sectors      │
│   • Push TBL/Sectors   • ~2 MB/s burst         • Cache for offline    │
│          │                    │                        │               │
│          ▼                    ▼                        ▼               │
│   ╔═════════════════════════════════════════════════════════════════╗  │
│   ║                    ⛔ NO LOCAL PROCESSING ⛔                     ║  │
│   ║                                                                  ║  │
│   ║   • No lap detection       • No CSV parsing beyond validation   ║  │
│   ║   • No TBL calculation     • No sector computation              ║  │
│   ║   • No ML/analysis         • App is a DATA CONDUIT only         ║  │
│   ╚═════════════════════════════════════════════════════════════════╝  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
           │                    │                        │
           ▼                    ▼                        ▼
    ┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
    │   ESP32-S3  │     │   ESP32 WiFi AP │     │  Cloud Backend   │
    │  Datalogger │     │  (192.168.4.1)  │     │  (All Processing)│
    └─────────────┘     └─────────────────┘     └──────────────────┘
```

### 2.3 BLE Command Protocol

The BLE channel is the control plane — always connected, low bandwidth, low power.

#### BLE Service Definition

```
Service UUID:     12345678-1234-5678-1234-567812345678

Characteristics:
├── Status       (12345678-1234-5678-1234-567812345002) - Read/Notify
│                { gps_lock, recording, session_count, ap_active }
│
├── Configure    (12345678-1234-5678-1234-567812345003) - Write
│                Commands: START_AP, STOP_AP, START_RECORD, STOP_RECORD
│
├── Device Info  (12345678-1234-5678-1234-567812345004) - Read
│                { device_id, firmware, storage_used, sessions[] }
│
└── Config Data  (12345678-1234-5678-1234-567812345005) - Write
                 TBL + Sector targets (JSON, chunked if needed)
```

### 2.4 Complete Sync Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HYBRID BURST SYNC SEQUENCE                                │
└─────────────────────────────────────────────────────────────────────────────┘

     Mobile App                    ESP32-S3                    Cloud Backend
         │                            │                              │
    ═══════════════════════════ PHASE 1: BLE HANDSHAKE ═══════════════════════
         │                            │                              │
         │  1. BLE Scan (Racesense-*) │                              │
         │ ──────────────────────────▶│                              │
         │                            │                              │
         │  2. GATT Connect           │                              │
         │ ──────────────────────────▶│                              │
         │                            │                              │
         │  3. Read Device Info       │                              │
         │ ◀──────────────────────────│                              │
         │  { device_id, sessions[] } │                              │
         │                            │                              │
    ═══════════════════════════ PHASE 2: WIFI AP BURST ═══════════════════════
         │                            │                              │
         │  4. BLE Write: START_AP    │                              │
         │ ──────────────────────────▶│                              │
         │                            │                              │
         │  5. BLE Notify: AP Ready   │                              │
         │ ◀──────────────────────────│                              │
         │  { ap_ssid, ap_password }  │                              │
         │                            │                              │
         │  6. Phone joins ESP WiFi   │                              │
         │   (SSID: Racesense-XXXX)   │                              │
         │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▶│                              │
         │                            │                              │
         │  7. HTTP GET /sessions     │                              │
         │ ──────────────────────────▶│                              │
         │                            │                              │
         │  8. Stream CSV files       │                              │
         │ ◀══════════════════════════│  (High-speed, ~2 MB/s)       │
         │  { session1.csv, ... }     │                              │
         │                            │                              │
         │  9. HTTP POST /ack         │                              │
         │ ──────────────────────────▶│  (Mark synced on ESP)        │
         │                            │                              │
         │  10. BLE Write: STOP_AP    │                              │
         │ ──────────────────────────▶│                              │
         │                            │                              │
         │  [Phone auto-rejoins LTE]  │                              │
         │                            │                              │
    ═══════════════════════════ PHASE 3: CLOUD UPLOAD ════════════════════════
         │                            │                              │
         │  11. POST /sessions/upload │                              │
         │ ─────────────────────────────────────────────────────────▶│
         │      { device_id, raw CSV files (gzipped) }               │
         │                            │                              │
         │                            │      [ Cloud Processing ]    │
         │                            │      • Parse CSV             │
         │                            │      • Detect laps           │
         │                            │      • Calculate sectors     │
         │                            │      • Update TBL            │
         │                            │      • Generate insights     │
         │                            │                              │
         │  12. GET /sessions/results │                              │
         │ ◀─────────────────────────────────────────────────────────│
         │  { laps[], sectors[], tbl, insights }                     │
         │                            │                              │
    ═══════════════════════════ PHASE 4: PUSH TO ESP ═════════════════════════
         │                            │                              │
         │  13. BLE Write: Config     │                              │
         │ ──────────────────────────▶│                              │
         │  { tbl, sector_targets }   │                              │
         │  (Small JSON, ~1-2KB)      │                              │
         │                            │                              │
         │  14. BLE Notify: Updated   │                              │
         │ ◀──────────────────────────│                              │
         │                            │                              │
    ════════════════════════════════ COMPLETE ════════════════════════════════
```

### 2.5 Connection State Machine

```
                    ┌────────────────┐
                    │  DISCONNECTED  │
                    └───────┬────────┘
                            │ BLE scan finds device
                            ▼
                    ┌────────────────┐
                    │  BLE_CONNECTED │◀────────────────────────────┐
                    └───────┬────────┘                             │
                            │ User taps "Sync"                     │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ AP_STARTING    │                             │
                    └───────┬────────┘                             │
                            │ ESP32 AP ready                       │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ JOINING_AP     │                             │
                    └───────┬────────┘                             │
                            │ Phone connected to ESP WiFi          │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ DOWNLOADING    │─────────────────────────────┤
                    └───────┬────────┘  WiFi lost / Error          │
                            │ All CSVs downloaded                  │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ AP_STOPPING    │                             │
                    └───────┬────────┘                             │
                            │ Phone rejoins cellular               │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ UPLOADING      │                             │
                    └───────┬────────┘                             │
                            │ Cloud upload complete                │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │ PUSHING_CONFIG │                             │
                    └───────┬────────┘                             │
                            │ TBL/Sectors pushed to ESP            │
                            ▼                                      │
                    ┌────────────────┐                             │
                    │  SYNC_COMPLETE │─────────────────────────────┘
                    └────────────────┘   (Returns to BLE_CONNECTED)
```

---

## 3. Data Pipeline Architecture

### 3.1 The Cloud-Centric Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE                                      │
│                                                                              │
│   "Raw data flows UP, processed results flow DOWN"                           │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌───────────┐         ┌───────────┐         ┌───────────────────────────┐
  │  ESP32    │  WiFi   │  Mobile   │  LTE/5G │     Cloud Backend         │
  │  Flash    │ ─────▶  │   App     │ ─────▶  │                           │
  │           │  AP     │  (Cache)  │         │  ┌─────────────────────┐  │
  │ Raw CSV   │ ~2MB/s  │ Raw CSV   │         │  │   Processing Engine │  │
  │ GPS + IMU │         │ (pending) │         │  │   ─────────────────  │  │
  │ + CAN     │         │           │         │  │   • CSV parsing     │  │
  └───────────┘         └─────┬─────┘         │  │   • Lap detection   │  │
                              │               │  │   • Sector times    │  │
                              │               │  │   • TBL calculation │  │
                              │               │  │   • ML insights     │  │
  ┌───────────┐         ┌─────▼─────┐         │  └──────────┬──────────┘  │
  │  ESP32    │  BLE    │  Mobile   │  LTE/5G │             │             │
  │  Config   │ ◀─────  │   App     │ ◀─────  │  ┌──────────▼──────────┐  │
  │           │ ~1KB    │  (Cache)  │         │  │   Results & Config  │  │
  │ TBL JSON  │         │ TBL +     │         │  │   ──────────────────│  │
  │ Sectors   │         │ Sectors   │         │  │   • Lap times       │  │
  │           │         │ Results   │         │  │   • Sector targets  │  │
  └───────────┘         └───────────┘         │  │   • Updated TBL     │  │
                                              │  │   • Session stats   │  │
                                              │  └─────────────────────┘  │
                                              └───────────────────────────┘
```

### 3.2 Data Formats

#### ESP32 Session Storage

```
/sessions/
  ├── 2026-02-09_session_001.csv    # Raw telemetry
  ├── 2026-02-09_session_002.csv
  └── manifest.json                  # Metadata index
```

#### Manifest Structure

```json
{
  "device_id": "RS-A1B2C3",
  "sessions": [
    {
      "id": "2026-02-09_session_001",
      "filename": "2026-02-09_session_001.csv",
      "start_time": 1739052000,
      "duration_sec": 1245,
      "size_bytes": 982400,
      "synced": false,
      "checksum": "sha256:abc123..."
    }
  ]
}
```

#### Cloud Upload Payload

```typescript
interface CloudUploadPayload {
  device_id: string;
  user_id: string;
  sessions: Array<{
    id: string;
    recorded_at: string;      // ISO 8601
    duration_sec: number;
    checksum: string;
    csv_data: Blob;           // gzipped raw CSV
  }>;
}
```

#### Cloud Response (Processed Results)

```typescript
interface CloudResponse {
  sessions: Array<{
    id: string;
    track_detected: {
      id: string;
      name: string;
      country: string;
    };
    laps: Array<{
      lap_number: number;
      lap_time_ms: number;
      sector_times: number[];    // ms per sector
      max_speed_kmh: number;
      max_lean_angle: number;
      is_valid: boolean;
    }>;
    best_lap_index: number;
    insights: string[];          // ML-generated tips
  }>;
  
  // Config to push to ESP32
  device_config: {
    tbl: {                       // Theoretical Best Lap
      time_ms: number;
      sector_times: number[];
    };
    sector_targets: Array<{
      sector_id: number;
      target_time_ms: number;
      entry_speed_kmh: number;
    }>;
    track_boundaries: GeoJSON;   // For lap detection on ESP32
  };
}
```

### 3.3 WiFi AP Transfer Protocol

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ESP32 HTTP API (When AP Active)                           │
└─────────────────────────────────────────────────────────────────────────────┘

  GET /api/manifest
  ─────────────────
  Response: { device_id, sessions: [...] }
  
  GET /api/sessions/{id}/download
  ─────────────────────────────────
  Response: Binary CSV stream (chunked transfer encoding)
  Headers: Content-Length, X-Checksum-SHA256
  
  POST /api/sessions/{id}/ack
  ────────────────────────────
  Body: { synced: true }
  Response: { ok: true }
  Note: ESP32 marks session as synced in manifest
```

---

## 4. Offline-First Strategy

### 4.1 The Trackday Reality

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TYPICAL TRACKDAY CONNECTIVITY                                              │
│                                                                              │
│  07:00  Arrive at track         📶📶📶   (parking lot, near road)           │
│  08:00  Tech inspection         📶       (paddock, weak signal)             │
│  09:00  Rider's meeting         📶📶     (main building)                    │
│  09:30  Session 1               ❌       (on track, no signal)              │
│  10:00  Cool down               📶       (paddock)                          │
│  10:30  Session 2               ❌       (on track)                         │
│  ...                                                                         │
│  16:00  Pack up                 📶📶📶   (leaving)                          │
│  18:00  Home                    📶📶📶📶📶 (WiFi)                            │
└─────────────────────────────────────────────────────────────────────────────┘

  KEY INSIGHT: ESP32 WiFi AP works ANYWHERE — no cell signal needed!
  Cloud sync happens whenever connectivity returns.
```

### 4.2 Offline Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OFFLINE MODE BEHAVIOR                                     │
└─────────────────────────────────────────────────────────────────────────────┘

  AT THE TRACK (No Internet):
  ───────────────────────────
  1. BLE connects to ESP32                    ✅ Works
  2. ESP32 AP activated                       ✅ Works
  3. CSVs downloaded to phone                 ✅ Works
  4. AP stopped, phone tries LTE              ❌ No signal
  5. CSVs cached locally                      ✅ Queued for later
  6. App shows: "3 sessions pending upload"   ✅ User informed
  
  LATER (Internet Available):
  ───────────────────────────
  1. Phone detects connectivity               ✅ Auto-detect
  2. Background upload triggered              ✅ Works (if allowed)
  3. CSVs uploaded to cloud                   ✅ Works
  4. Results received                         ✅ Works
  5. Next BLE connect → push TBL to ESP32     ✅ Deferred push
```

### 4.3 Local Database Schema (Simplified for Thin App)

```sql
-- Cached sessions (raw CSVs waiting for upload)
CREATE TABLE pending_sessions (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    recorded_at DATETIME NOT NULL,
    duration_sec INTEGER,
    file_path TEXT NOT NULL,        -- Local filesystem path
    file_size INTEGER,
    checksum TEXT,
    
    -- Sync status
    upload_status TEXT DEFAULT 'pending',  -- pending, uploading, complete, failed
    upload_attempts INTEGER DEFAULT 0,
    last_attempt_at DATETIME,
    error_message TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Cached cloud results (for display when offline)
CREATE TABLE session_results (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    track_id TEXT,
    track_name TEXT,
    laps_json TEXT,                 -- Full lap breakdown
    best_lap_ms INTEGER,
    insights_json TEXT,
    
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES pending_sessions(id)
);

-- Config to push to ESP32 (cached for next connection)
CREATE TABLE pending_device_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    config_json TEXT NOT NULL,      -- TBL + Sectors
    pushed BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 4.4 Sync Strategy

```typescript
class SyncManager {
  
  // Called after CSV download from ESP32
  async queueForUpload(sessions: LocalSession[]): Promise<void> {
    for (const session of sessions) {
      await this.db.insert('pending_sessions', {
        id: session.id,
        device_id: session.device_id,
        file_path: session.localPath,
        upload_status: 'pending'
      });
    }
    
    // Try immediate upload if online
    if (await this.isOnline()) {
      this.uploadPending();
    }
  }
  
  // Triggered on network change, app foreground, or timer
  async uploadPending(): Promise<SyncResult> {
    const networkStatus = await Network.getStatus();
    
    if (!networkStatus.connected) {
      return { status: 'offline', queued: await this.getQueueCount() };
    }
    
    // Prefer WiFi for large uploads
    const useCellular = await this.getUserPreference('sync_on_cellular');
    if (networkStatus.connectionType === 'cellular' && !useCellular) {
      return { status: 'waiting_for_wifi' };
    }
    
    const pending = await this.db.query('pending_sessions', { upload_status: 'pending' });
    
    for (const session of pending) {
      try {
        await this.db.update('pending_sessions', session.id, { upload_status: 'uploading' });
        
        const result = await this.cloudApi.uploadSession(session);
        
        // Store results locally
        await this.db.insert('session_results', {
          session_id: session.id,
          ...result
        });
        
        // Queue config for ESP32 push
        if (result.device_config) {
          await this.db.insert('pending_device_config', {
            device_id: session.device_id,
            config_json: JSON.stringify(result.device_config)
          });
        }
        
        await this.db.update('pending_sessions', session.id, { upload_status: 'complete' });
        
      } catch (error) {
        await this.db.update('pending_sessions', session.id, {
          upload_status: 'failed',
          upload_attempts: session.upload_attempts + 1,
          error_message: error.message
        });
      }
    }
    
    return { status: 'complete', synced: pending.length };
  }
  
  // Called when BLE connects to ESP32
  async pushPendingConfig(deviceId: string): Promise<void> {
    const pending = await this.db.query('pending_device_config', {
      device_id: deviceId,
      pushed: false
    });
    
    for (const config of pending) {
      await this.ble.writeConfig(deviceId, config.config_json);
      await this.db.update('pending_device_config', config.id, { pushed: true });
    }
  }
}
```

---

## 5. Required Plugins

### 5.1 Core Capacitor Plugins (Minimal for Thin App)

| Plugin | Package | Purpose |
|--------|---------|---------|
| **BLE** | `@capacitor-community/bluetooth-le` | ESP32 discovery, commands, config push |
| **Filesystem** | `@capacitor/filesystem` | Cache downloaded CSVs |
| **Network** | `@capacitor/network` | Detect connectivity for cloud sync |
| **Preferences** | `@capacitor/preferences` | User settings (sync on cellular, etc.) |
| **App** | `@capacitor/app` | Lifecycle events, background/foreground |
| **Splash Screen** | `@capacitor/splash-screen` | Launch experience |
| **Status Bar** | `@capacitor/status-bar` | UI integration |

### 5.2 Extended Functionality

| Plugin | Package | Purpose |
|--------|---------|---------|
| **SQLite** | `@capacitor-community/sqlite` | Local cache for pending uploads & results |
| **HTTP** | `@capacitor/http` | Native HTTP for ESP32 file transfer |
| **Background Task** | `@capacitor/background-task` | Complete upload before app suspend |
| **Local Notifications** | `@capacitor/local-notifications` | "Sync complete" alerts |

### 5.3 NOT Required (Thin App Advantage)

| Plugin | Why Not Needed |
|--------|----------------|
| **Geolocation** | No local track detection — cloud does it |
| **Heavy processing libs** | No local CSV parsing or analysis |
| **ML/TensorFlow** | Cloud handles all ML insights |

### 5.4 Installation Commands

```bash
# Initialize Capacitor in existing web project
npm install @capacitor/core @capacitor/cli
npx cap init Racesense com.racesense.app

# Core plugins
npm install @capacitor/app @capacitor/filesystem @capacitor/network
npm install @capacitor/preferences
npm install @capacitor/splash-screen @capacitor/status-bar

# BLE (Community plugin - excellent quality)
npm install @capacitor-community/bluetooth-le

# SQLite for local cache
npm install @capacitor-community/sqlite

# HTTP for ESP32 file transfer
npm install @capacitor/http

# Background and notifications
npm install @capacitor/background-task
npm install @capacitor/local-notifications

# Add native platforms
npx cap add ios
npx cap add android

# Sync web assets to native projects
npx cap sync
```

---

## 6. Development Roadmap

### Phase 1: Foundation (Weeks 1-3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: FOUNDATION                                                         │
│  Goal: Basic app with BLE control and WiFi AP data transfer                  │
└─────────────────────────────────────────────────────────────────────────────┘

  Week 1: Project Setup
  ─────────────────────
  □ Initialize Capacitor in existing web UI directory
  □ Configure capacitor.config.ts for both platforms
  □ Set up iOS project (Xcode) with signing
  □ Set up Android project (Android Studio)
  □ Verify web UI runs in native shell
  □ Configure splash screen and app icon
  
  Week 2: BLE Command Channel
  ───────────────────────────
  □ Install @capacitor-community/bluetooth-le
  □ Implement device scanning (Racesense-* prefix)
  □ BLE connect and read device info
  □ Implement START_AP / STOP_AP commands
  □ Subscribe to status notifications
  □ Handle BLE permission flows (iOS + Android)
  
  Week 3: WiFi AP Burst Transfer
  ──────────────────────────────
  □ Detect when phone joins ESP32 AP
  □ HTTP client to ESP32 (192.168.4.1)
  □ Download manifest and CSV files
  □ Store CSVs to local filesystem
  □ Send STOP_AP command after transfer
  □ Handle phone rejoining cellular
```

### Phase 2: Cloud Integration (Weeks 4-6)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: CLOUD INTEGRATION                                                  │
│  Goal: Upload raw data to cloud, receive processed results                   │
└─────────────────────────────────────────────────────────────────────────────┘

  Week 4: Local Cache Layer
  ─────────────────────────
  □ Install and configure SQLite plugin
  □ Create simplified schema (pending_sessions, session_results)
  □ Queue downloaded CSVs for upload
  □ Implement network status detection
  
  Week 5: Cloud Upload Pipeline
  ─────────────────────────────
  □ Implement cloud API client
  □ Gzip compression for CSV uploads
  □ Upload queue with retry logic
  □ Store received results locally
  □ Handle offline → online transitions
  
  Week 6: Config Push to ESP32
  ────────────────────────────
  □ Parse TBL/Sector config from cloud response
  □ Store pending config in SQLite
  □ Push config via BLE on next connection
  □ Chunked BLE write for larger payloads
  □ Confirm config received by ESP32
```

### Phase 3: UX & Polish (Weeks 7-9)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: UX & POLISH                                                        │
│  Goal: Polished user experience, clear status indicators                     │
└─────────────────────────────────────────────────────────────────────────────┘

  Week 7: Sync UI
  ───────────────
  □ Connection status indicator (BLE, WiFi AP, Cloud)
  □ Download progress bar
  □ Upload progress indicator
  □ "Pending uploads" badge/counter
  □ Error states with retry actions
  
  Week 8: Results Display
  ───────────────────────
  □ Session list with lap counts
  □ Lap time breakdown view
  □ Sector comparison visualization
  □ Best lap highlighting
  □ Cloud insights display
  
  Week 9: Settings & Preferences
  ──────────────────────────────
  □ Sync on cellular toggle
  □ Storage usage display
  □ Clear cache option
  □ Device management (link/unlink)
  □ Local notifications for sync complete
```

### Phase 4: Authentication & Launch (Weeks 10-12)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: AUTHENTICATION & LAUNCH                                            │
│  Goal: User accounts, beta testing, store submission                         │
└─────────────────────────────────────────────────────────────────────────────┘

  Week 10: User Authentication
  ────────────────────────────
  □ User registration/login flows
  □ Secure token storage
  □ Device linking (ESP32 → User account)
  □ Session ownership
  
  Week 11: Beta Testing
  ─────────────────────
  □ TestFlight beta (iOS)
  □ Internal testing track (Android)
  □ Real-world trackday testing
  □ Performance profiling
  □ Crash reporting integration
  
  Week 12: Store Submission
  ─────────────────────────
  □ App Store screenshots and metadata
  □ Play Store listing
  □ Privacy policy and terms
  □ Review submission
  □ Launch coordination
```

---

## 7. Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Phone fails to join ESP32 AP | Medium | High | Clear UI guidance; fallback instructions |
| Phone doesn't auto-rejoin cellular after AP | Medium | Medium | Explicit "Sync complete" step; OS-level testing |
| BLE reliability varies by device | Medium | Medium | Extensive device testing; reconnect logic |
| Large CSV upload fails mid-transfer | Low | Medium | Chunked upload with resume support |
| iOS background upload limitations | High | Low | Use Background Task; educate on foreground sync |

### Platform-Specific Concerns

**iOS:**
- Joining ESP32 WiFi requires user interaction (Settings or prompt)
- Background processing heavily restricted
- TestFlight required for beta distribution

**Android:**
- WiFi switching more flexible programmatically
- Location permission required for WiFi scanning (Android 10+)
- Battery optimization may interrupt background uploads

### Recommended Testing Devices

```
iOS:
  - iPhone 12 or newer (reliable BLE + WiFi switching)
  - iPhone SE 3rd gen (smaller screen edge cases)

Android:
  - Google Pixel 6+ (reference Android)
  - Samsung Galaxy S21+ (most common flagship)
  - OnePlus mid-range (common in riding community)
```

---

## Appendix A: capacitor.config.ts Template

```typescript
import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.racesense.app',
  appName: 'Racesense',
  webDir: 'ui',
  
  server: {
    // Allow cleartext for ESP32 local AP
    cleartext: true,
  },
  
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#1a1a2e',
      androidScaleType: 'CENTER_CROP',
      showSpinner: false,
    },
    
    BluetoothLe: {
      displayStrings: {
        scanning: 'Searching for Racesense device...',
        cancel: 'Cancel',
        availableDevices: 'Available Devices',
        noDeviceFound: 'No Racesense device found',
      },
    },
    
    LocalNotifications: {
      smallIcon: 'ic_stat_icon',
      iconColor: '#e94560',
    },
  },
  
  ios: {
    scheme: 'Racesense',
  },
  
  android: {
    allowMixedContent: true,
  },
};

export default config;
```

---

## Appendix B: BLE Command Adapter

```typescript
// capacitor-ble-commander.ts
import { BleClient, BleDevice, numbersToDataView } from '@capacitor-community/bluetooth-le';

const SERVICE_UUID = '12345678-1234-5678-1234-567812345678';
const CHAR_STATUS_UUID = '12345678-1234-5678-1234-567812345002';
const CHAR_CONFIGURE_UUID = '12345678-1234-5678-1234-567812345003';
const CHAR_DEVICE_INFO_UUID = '12345678-1234-5678-1234-567812345004';
const CHAR_CONFIG_DATA_UUID = '12345678-1234-5678-1234-567812345005';

type Command = 'START_AP' | 'STOP_AP' | 'START_RECORD' | 'STOP_RECORD';

export class RacesenseBLE {
  private device: BleDevice | null = null;
  
  async initialize(): Promise<void> {
    await BleClient.initialize();
  }
  
  async connect(): Promise<BleDevice> {
    this.device = await BleClient.requestDevice({
      namePrefix: 'Racesense',
      optionalServices: [SERVICE_UUID],
    });
    
    await BleClient.connect(this.device.deviceId, () => {
      console.log('Disconnected');
      this.device = null;
    });
    
    return this.device;
  }
  
  async sendCommand(command: Command): Promise<void> {
    if (!this.device) throw new Error('Not connected');
    
    const encoder = new TextEncoder();
    await BleClient.write(
      this.device.deviceId,
      SERVICE_UUID,
      CHAR_CONFIGURE_UUID,
      numbersToDataView(Array.from(encoder.encode(command)))
    );
  }
  
  async pushConfig(config: { tbl: object; sector_targets: object[] }): Promise<void> {
    if (!this.device) throw new Error('Not connected');
    
    const payload = JSON.stringify(config);
    const encoder = new TextEncoder();
    const bytes = encoder.encode(payload);
    
    // Chunk if needed (BLE MTU ~512 bytes typical)
    const chunkSize = 500;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const chunk = bytes.slice(i, i + chunkSize);
      await BleClient.write(
        this.device.deviceId,
        SERVICE_UUID,
        CHAR_CONFIG_DATA_UUID,
        numbersToDataView(Array.from(chunk))
      );
    }
  }
  
  async subscribeToStatus(callback: (status: any) => void): Promise<void> {
    if (!this.device) throw new Error('Not connected');
    
    await BleClient.startNotifications(
      this.device.deviceId,
      SERVICE_UUID,
      CHAR_STATUS_UUID,
      (value) => {
        const decoder = new TextDecoder();
        const str = decoder.decode(value);
        try {
          callback(JSON.parse(str));
        } catch {
          callback({ raw: str });
        }
      }
    );
  }
}
```

---

*Document revised for "Hybrid Burst" architecture. Thin App → Cloud-centric processing.*
