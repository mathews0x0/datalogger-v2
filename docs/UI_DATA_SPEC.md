# Datalogger UI - JSON Data Specification

**Date:** 2025-12-25  
**Version:** 1.0  
**For:** UI Designer / Frontend Developer

---

## Overview

The datalogger generates 4 types of JSON files in the `output/` directory:

1. **`registry.json`** - Index of all tracks
2. **`track.json`** - Immutable track geometry (per track folder)
3. **`tbl.json`** - Theoretical Best Lap performance records (per track folder)
4. **`<track_name>_session_<N>.json`** - Complete session data (UI-ready)

---

## 1. Registry JSON

**Location:** `output/registry.json`

**Purpose:** Single source of truth for all tracks. Use this to populate track selection dropdowns.

```json
{
  "next_id": 2,
  "tracks": [
    {
      "track_id": 1,
      "track_name": "Kari Motor Speedway",
      "folder_name": "kari_motor_speedway",
      "created": "2025-12-25T13:31:41.432302",
      "last_updated": "2025-12-25T13:36:07.497928"
    }
  ]
}
```

### Fields:

| Field          | Type     | Description                                  |
| -------------- | -------- | -------------------------------------------- |
| `next_id`      | int      | Auto-increment counter (internal use)        |
| `tracks`       | array    | List of all registered tracks                |
| `track_id`     | int      | **Immutable** unique identifier              |
| `track_name`   | string   | Human-readable name (mutable)                |
| `folder_name`  | string   | Directory name (mutable, matches track_name) |
| `created`      | ISO 8601 | Track creation timestamp                     |
| `last_updated` | ISO 8601 | Last rename timestamp (optional)             |

### UI Usage:

```javascript
// Fetch all tracks for dropdown
fetch("output/registry.json")
  .then((res) => res.json())
  .then((data) => {
    data.tracks.forEach((track) => {
      // Display: track.track_name
      // Link to: output/tracks/{track.folder_name}/
    });
  });
```

---

## 2. Track JSON

**Location:** `output/tracks/<folder_name>/track.json`

**Purpose:** Immutable track geometry. **Never changes after creation.**

```json
{
  "track_id": 1,
  "track_name": "Kari Motor Speedway",
  "start_line": {
    "lat": 14.769496666666667,
    "lon": 82.10247733333333,
    "radius_m": 20.0
  },
  "metadata": {
    "sector_strategy": "distance_equal_v1",
    "num_sectors": 7,
    "source_session": "tests/testdata/214524.csv"
  },
  "sectors": [
    {
      "id": "S1",
      "end_lat": 14.769019199999999,
      "end_lon": 82.1020082,
      "radius_m": 50.0
    },
    {
      "id": "S2",
      "end_lat": 14.768953999999999,
      "end_lon": 82.1014058,
      "radius_m": 50.0
    }
    // ... S3-S7
  ],
  "location": "Unknown",
  "created_at": "now"
}
```

### Fields:

| Field                  | Type   | Description                     |
| ---------------------- | ------ | ------------------------------- |
| `track_id`             | int    | Immutable ID (matches registry) |
| `track_name`           | string | Track name                      |
| `start_line.lat`       | float  | Start/finish latitude           |
| `start_line.lon`       | float  | Start/finish longitude          |
| `start_line.radius_m`  | float  | Detection radius (meters)       |
| `metadata.num_sectors` | int    | Always 7 sectors                |
| `sectors`              | array  | Sector end points (7 items)     |
| `sectors[].id`         | string | "S1" to "S7"                    |
| `sectors[].end_lat`    | float  | Sector end latitude             |
| `sectors[].end_lon`    | float  | Sector end longitude            |
| `sectors[].radius_m`   | float  | Detection radius                |

### UI Usage:

```javascript
// Display track map with sectors
fetch(`output/tracks/${folder_name}/track.json`)
  .then((res) => res.json())
  .then((track) => {
    // Plot start line: track.start_line
    // Plot sectors: track.sectors (S1-S7)
    // Show track image: output/tracks/${folder_name}/track_map.png
  });
```

---

## 3. TBL JSON (Theoretical Best Lap)

**Location:** `output/tracks/<folder_name>/tbl.json`

**Purpose:** Mutable performance records. **Updates after every session.**

```json
{
  "track_id": 1,
  "sectors": [
    {
      "sector_index": 0,
      "best_time": 6.992865085601807
    },
    {
      "sector_index": 1,
      "best_time": 20.847114086151123
    }
    // ... sectors 2-6 (total 7)
  ],
  "total_best_time": 140.03248620033264,
  "best_real_lap": {
    "time": null,
    "session": null
  },
  "track_name": "track_1",
  "sector_count": 7,
  "last_updated_session_id": "tests/testdata/214524.csv",
  "last_updated_time": "2025-12-25T08:02:41.701651Z"
}
```

### Fields:

| Field                    | Type        | Description                    |
| ------------------------ | ----------- | ------------------------------ |
| `track_id`               | int         | Track identifier               |
| `sectors`                | array       | Best time per sector (7 items) |
| `sectors[].sector_index` | int         | 0-6 (maps to S1-S7)            |
| `sectors[].best_time`    | float       | Best time in seconds           |
| `total_best_time`        | float       | Sum of all sector bests (TBL)  |
| `best_real_lap.time`     | float/null  | Fastest complete lap time      |
| `best_real_lap.session`  | string/null | Session ID where it occurred   |
| `last_updated_time`      | ISO 8601    | Last TBL update                |

### UI Usage:

```javascript
// Display current TBL and sector bests
fetch(`output/tracks/${folder_name}/tbl.json`)
  .then((res) => res.json())
  .then((tbl) => {
    // Display TBL: tbl.total_best_time
    // Display sector bests: tbl.sectors[0..6].best_time
    // Compare current lap to TBL
  });
```

---

## 4. Session JSON (UI-Ready)

**Location:** `output/sessions/<track_name>_session_<N>.json`

**Purpose:** Complete session analysis. **This is your primary data source for UI.**

### Full Structure:

```json
{
  "meta": {
    "session_id": "kari_motor_speedway_session_1",
    "session_name": "tests/testdata/214524.csv",
    "start_time": "2025-12-22T21:45:26.634673Z",
    "end_time": "2025-12-22T21:52:48.455393Z",
    "duration_sec": 441.82,
    "logger_version": "v3.6",
    "schema_version": "1.0"
  },

  "environment": {
    "track_temperature": null,
    "ambient_temperature": null,
    "gps_quality_summary": {
      "total_fixes": 3586,
      "fix_dropouts": 0
    }
  },

  "mode": {
    "mode_type": "active",
    "learning_active": false,
    "notes": ""
  },

  "calibration": {
    "calibrated": true,
    "confidence": "HIGH",
    "gravity_vector": [0.01, -0.05, 15998.0],
    "gyro_bias": [5.0, -2.0, 3.0]
  },

  "analysis": {
    "signals": {
      "aligned_accel_x": [0.1, 0.2],
      "aligned_accel_y": [-0.1, -0.1],
      "aligned_accel_z": [16000.0, 16005.0]
    }
  },

  "track": {
    "track_id": 1,
    "track_name": "Kari Motor Speedway",
    "sector_count": 7,
    "sector_definition_source": {
      "fastest_lap_session_id": null,
      "fastest_lap_time": null
    }
  },

  "references": {
    "best_real_lap_reference": {
      "lap_time": null,
      "session_id": null
    },
    "theoretical_best_reference": 140.03248620033264,
    "sector_times": [
      6.992865085601807, 20.847114086151123, 0.19170069694519043,
      42.492719411849976, 3.8910562992095947, 44.58292531967163,
      21.03410530090332
    ],
    "reference_type_used_for_deltas": "theoretical"
  },

  "laps": [
    {
      "lap_index": 0,
      "lap_number": 1,
      "lap_time": 145.105,
      "valid": true,
      "reason_invalid": null,
      "sector_times": [
        7.82462477684021, 25.087791919708252, 0.19179797172546387,
        42.492719411849976, 3.8910562992095947, 44.58292531967163,
        21.03410530090332
      ],
      "delta_to_reference": 0.0,
      "is_session_best": true
    }
  ],

  "sectors": [
    {
      "sector_index": "S1",
      "best_time_this_session": 6.992865085601807,
      "median_time": 7.82462477684021,
      "worst_time": 7.82462477684021,
      "laps_count": 2
    }
    // ... S2-S7
  ],

  "summary": {
    "total_laps": 2,
    "valid_laps": 2,
    "invalid_laps": 0,
    "best_lap_index": 0,
    "best_lap_time": 145.105,
    "tbl_improved": true,
    "sectors_improved": [0, 1, 2]
  }
}
```

## 5. Telemetry JSON (Lazy Loaded)

**Location:** `output/sessions/<track>_session_<N>_telemetry.json`

**Purpose:** High-resolution (10Hz) time-series data for charts and detailed maps. Loaded on-demand.

**Structure (Columnar Arrays):**

```json
{
  "time": [0.0, 0.1, 0.2, ...],        // Seconds relative to session start
  "lat": [12.9, 12.9001, ...],
  "lon": [77.5, 77.5001, ...],
  "speed": [50.1, 50.5, ...],          // km/h
  "ax": [0.1, 0.15, ...],              // Aligned Longitudinal Accel (if available)
  "ay": [0.01, 0.02, ...]              // Aligned Lateral Accel (if available)
}
```

### Key Sections for UI:

#### A. Session Overview (`meta`)

```javascript
// Display session header
const { session_name, start_time, duration_sec } = data.meta;
```

#### B. Lap List (`laps`)

```javascript
// Display lap times table
data.laps.forEach((lap) => {
  // Show: lap.lap_number, lap.lap_time, lap.valid
  // Highlight best: lap.is_session_best
});
```

#### C. Sector Analysis (`sectors`)

```javascript
// Display sector performance
data.sectors.forEach((sector) => {
  // Show: sector.sector_index, sector.best_time_this_session
  // Compare to TBL: data.references.sector_times[index]
});
```

#### D. TBL Comparison (`references`)

```javascript
// Show if rider improved TBL
const tbl = data.references.theoretical_best_reference;
const improved = data.summary.tbl_improved;
const improvedSectors = data.summary.sectors_improved;
```

---

## File Structure Summary

```
output/
├── registry.json                              # All tracks index
├── tracks/
│   ├── kari_motor_speedway/
│   │   ├── track.json                         # Immutable geometry
│   │   ├── tbl.json                           # Mutable records
│   │   └── track_map.png                      # Visual reference
│   └── bangalore_circuit/
│       ├── track.json
│       ├── tbl.json
│       └── track_map.png
└── sessions/
    ├── kari_motor_speedway_session_1.json     # Complete session data
    ├── kari_motor_speedway_session_2.json
    └── bangalore_circuit_session_1.json
```

---

## UI Flow Recommendation

### 1. **Landing Page**

```javascript
// Load registry
GET output/registry.json
// Display track cards with track_name
```

### 2. **Track Detail Page**

```javascript
// Load track geometry
GET output/tracks/{folder_name}/track.json
// Load current TBL
GET output/tracks/{folder_name}/tbl.json
// Display track map
IMG output/tracks/{folder_name}/track_map.png
```

### 3. **Sessions List**

```javascript
// Glob pattern for sessions
GET output/sessions/{folder_name}_session_*.json
// Display session list with best lap times
```

### 4. **Session Analysis Page**

```javascript
// Load full session
GET output/sessions/{folder_name}_session_{N}.json
// Display:
// - Lap times table
// - Sector comparison chart
// - TBL delta chart
// - Best lap highlight
```

---

## Key Data Contracts

### Immutability Rules:

- ✅ `track_id` - **NEVER changes**
- ✅ `track.json` geometry - **NEVER changes**
- ❌ `track_name` - **CAN change** (via rename)
- ❌ `folder_name` - **CAN change** (via rename)
- ❌ `tbl.json` - **UPDATES** after every session

### Sector Indexing:

- JSON uses: `0-6` (sector_index)
- Display uses: `S1-S7` (sector_id)
- Always 7 sectors (hardcoded)

### Time Format:

- All times in **seconds** (float)
- Timestamps in **ISO 8601** format
- GPS quality: integer counts

---

## Example UI Components

### Track Selector

```javascript
<select id="track-selector">
  {tracks.map((t) => (
    <option value={t.track_id}>{t.track_name}</option>
  ))}
</select>
```

### Lap Times Table

```javascript
<table>
  <thead>
    <tr>
      <th>Lap</th>
      <th>Time</th>
      <th>Delta</th>
      <th>Best</th>
    </tr>
  </thead>
  <tbody>
    {laps.map((lap) => (
      <tr class={lap.is_session_best ? "best" : ""}>
        <td>{lap.lap_number}</td>
        <td>{lap.lap_time.toFixed(3)}s</td>
        <td>{lap.delta_to_reference.toFixed(3)}s</td>
        <td>{lap.is_session_best ? "✓" : ""}</td>
      </tr>
    ))}
  </tbody>
</table>
```

### Sector Chart

```javascript
<div class="sector-chart">
  {sectors.map((sector, i) => (
    <div class="sector">
      <label>{sector.sector_index}</label>
      <div class="bar" style={{ width: `${sector.best_time_this_session}%` }}>
        {sector.best_time_this_session.toFixed(3)}s
      </div>
    </div>
  ))}
</div>
```

---

## Notes for UI Designer

1. **All JSON is pre-computed** - No complex calculations needed in UI
2. **Session JSON is UI-ready** - Contains everything for display
3. **Use registry.json** as single source of track list
4. **Folder names are filesystem safe** - lowercase, underscores only
5. **Track IDs are stable** - Safe to use as database keys
6. **TBL updates automatically** - Always fetch latest from tbl.json
7. **Sessions are immutable** - Once created, never modified

---

## API Endpoints (Future)

If building a backend API layer:

```
GET  /api/tracks                    → Return registry.json
GET  /api/tracks/{track_id}         → Return track.json + tbl.json
GET  /api/tracks/{track_id}/sessions → Return session list
GET  /api/sessions/{session_id}     → Return full session JSON
```

For now, **direct filesystem reads** are sufficient (files are UI-ready).

---

**End of Specification**
