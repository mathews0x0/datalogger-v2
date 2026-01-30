# Datalogger Companion App - Requirements & Architecture

**Date:** 2025-12-25  
**Version:** 1.0 (Phase 3.2)  
**Target:** Mobile/Desktop Companion Application

---

## Overview

The **Companion App** is a racer-friendly UI that connects to the Raspberry Pi datalogger, processes session data, and provides analysis tools for track-day performance improvement.

### Use Case Flow:

1. **At Track:** Racer mounts Pi on motorcycle → Starts logging → Rides session → Stops logging
2. **Post-Session:** Racer connects to Pi via Companion App (WiFi/FTP)
3. **Analysis:** App processes raw data → Shows track map → Displays session analysis
4. **Action:** Racer reviews laps, sectors, compares to TBL, prepares for next session

---

## Connection Options (TBD)

### Option A: WiFi Hotspot (Recommended)

**Pi as Access Point:**

- Pi broadcasts WiFi network (e.g., "DataloggerAP")
- Companion app connects to Pi's network
- Access files via HTTP/FTP server on Pi
- **Pros:** No internet needed, direct connection, fast
- **Cons:** Pi needs WiFi adapter configuration

### Option B: FTP/SFTP

**File Transfer Protocol:**

- Pi runs FTP server (vsftpd)
- Companion app connects via FTP client
- Read/write to `output/` directory
- **Pros:** Simple, reliable, well-tested
- **Cons:** Requires network setup, slower for browsing

### Option C: REST API (Future)

**HTTP API on Pi:**

- Pi runs lightweight Flask/FastAPI server
- Companion calls REST endpoints
- **Pros:** Clean architecture, scalable
- **Cons:** More complex, needs server development

**Recommendation:** Start with **WiFi Hotspot + HTTP server** for simplicity.

---

## Feature Requirements

### 1. Raw Learning Data Access 🔧

**Priority:** Low (Debug Mode Only)

**Location:** `output/learning/*.csv`

**UI Flow:**

```
Settings → Debug Mode → Learning Data
  → List all CSVs in learning/
  → Tap to download/view
  → Show metadata (date, size, row count)
```

**API Endpoint:**

```
GET /api/learning/list          → Return list of learning CSVs
GET /api/learning/{filename}    → Download CSV file
```

**Notes:**

- Hidden by default (not for average racer)
- Useful for advanced users debugging track generation
- Show warning: "Raw data - processing required"

---

### 2. Process Session (Trigger Analysis) ⚙️

**Priority:** HIGH (Core Feature)

**Existing Script:** `src/analysis/run_analysis.py`

**UI Flow:**

```
Home → "New Session Available" badge
  → Tap "Process Session"
  → Select CSV from output/learning/
  → Trigger: py run_analysis.py {filename}
  → Show progress indicator
  → On complete: Navigate to session view
```

**API Endpoint:**

```
POST /api/process
  Body: { "csv_file": "output/learning/session_20251225_143022.csv" }
  Response: { "status": "processing", "job_id": "abc123" }

GET /api/process/status/{job_id}
  Response: {
    "status": "complete",
    "track_id": 1,
    "session_id": "kari_motor_speedway_session_3"
  }
```

**Implementation:**

```python
# On Pi (Flask server)
@app.route('/api/process', methods=['POST'])
def process_session():
    csv_file = request.json['csv_file']

    # Run analysis in background
    job_id = str(uuid.uuid4())
    subprocess.Popen([
        'python3', 'src/analysis/run_analysis.py', csv_file
    ])

    return {"status": "processing", "job_id": job_id}
```

**UI Behavior:**

- Show spinner during processing (~5-10 seconds)
- Auto-refresh when complete
- Display success: "Session processed! 2 laps detected."
- Navigate to session view automatically

---

### 3. View Track Information 🗺️

**Priority:** HIGH (Core Feature)

**Data Sources:**

- `output/registry.json` → List of tracks
- `output/tracks/{folder}/track.json` → Track details
- `output/tracks/{folder}/track_map.png` → Visual map

**UI Flow:**

```
Tracks Tab
  → List of tracks (from registry)
  → Tap track
    → Show track map image
    → Display track info:
      - Track name
      - Number of sectors (7)
      - Last session date
      - Total sessions count
    → Actions:
      - [Rename Track] button
      - [View Sessions] button
```

**API Endpoints:**

```
GET /api/tracks
  Response: { "tracks": [...] }  // From registry.json

GET /api/tracks/{track_id}
  Response: {
    "track_id": 1,
    "track_name": "Kari Motor Speedway",
    "folder_name": "kari_motor_speedway",
    "sessions_count": 5,
    "last_session": "2025-12-25T14:30:00"
  }

GET /api/tracks/{track_id}/map
  Response: PNG image (track_map.png)
```

**UI Component Example:**

```jsx
<TrackCard>
  <TrackMap src="/api/tracks/1/map" />
  <TrackName>Kari Motor Speedway</TrackName>
  <TrackStats>
    <Stat label="Sessions" value={5} />
    <Stat label="Sectors" value={7} />
  </TrackStats>
  <Button onClick={renameTrack}>Rename</Button>
  <Button onClick={viewSessions}>View Sessions</Button>
</TrackCard>
```

---

### 4. Rename Track 📝

**Priority:** MEDIUM (Quality of Life)

**Existing Script:** `scripts/rename_track.py`

**UI Flow:**

```
Track Detail → Tap "Rename"
  → Modal popup
  → Input: New track name
  → Preview: "kari_motor_speedway" (sanitized name shown)
  → Confirmation: "Rename 5 session files?"
  → [Cancel] [Rename]
  → On success: Toast "Renamed successfully!"
  → Refresh track list
```

**API Endpoint:**

```
POST /api/tracks/{track_id}/rename
  Body: { "new_name": "Kari Motor Speedway" }
  Response: {
    "success": true,
    "old_name": "track_1",
    "new_name": "Kari Motor Speedway",
    "folder_name": "kari_motor_speedway",
    "files_renamed": 5
  }
```

**Implementation:**

```python
@app.route('/api/tracks/<int:track_id>/rename', methods=['POST'])
def rename_track(track_id):
    new_name = request.json['new_name']

    # Call existing rename script
    result = subprocess.run([
        'python3', 'scripts/rename_track.py',
        '--track_id', str(track_id),
        '--new_name', new_name
    ], capture_output=True, text=True)

    if result.returncode == 0:
        return {"success": True, "new_name": new_name}
    else:
        return {"success": False, "error": result.stderr}, 400
```

**Validation:**

- Show sanitized name preview in real-time
- Warn if name already exists
- Confirm before rename (show number of affected files)

---

### 5. View Sessions Organized by Date 📅

**Priority:** HIGH (Core Feature)

**Data Source:** `output/sessions/` directory

**UI Flow:**

```
Sessions Tab (or Track Detail → Sessions)
  → Grouped by date:

    Today
      • Session 3 - 14:30 - Best: 1:45.2
      • Session 2 - 10:15 - Best: 1:47.8

    Yesterday
      • Session 1 - 16:45 - Best: 1:52.3

    Dec 23, 2025
      • Session 5 - 12:00 - Best: 1:44.1*  ← New TBL
```

**API Endpoint:**

```
GET /api/sessions?track_id={id}
  Response: [
    {
      "session_id": "kari_motor_speedway_session_3",
      "session_name": "Session 3",
      "date": "2025-12-25T14:30:00",
      "best_lap": 145.2,
      "total_laps": 8,
      "tbl_improved": false,
      "track_name": "Kari Motor Speedway"
    }
  ]
```

**Sorting:**

- Default: Newest first
- Group by: Day
- Filter by: Track (if viewing all sessions)

**Session Card UI:**

```jsx
<SessionCard onClick={viewSession}>
  <SessionTime>14:30</SessionTime>
  <SessionStats>
    <BestLap>1:45.2</BestLap>
    <LapCount>8 laps</LapCount>
    {tblImproved && <Badge>New TBL!</Badge>}
  </SessionStats>
</SessionCard>
```

---

### 6. Visualize Session Data 📊

**Priority:** HIGH (Core Feature)

**Data Source:** `output/sessions/{track_name}_session_{N}.json`

**UI Screens:**

#### A. Session Overview

```
Session 3 - Kari Motor Speedway
  Dec 25, 2025 14:30
  Duration: 7:21 (441s)

  Best Lap: 1:45.105 (Lap 1)
  TBL: 2:20.032

  [View Lap Times] [View Sectors] [View Delta Chart]
```

#### B. Lap Times List

```
┌─────┬──────────┬────────┬──────┐
│ Lap │ Time     │ Delta  │ Best │
├─────┼──────────┼────────┼──────┤
│ 1   │ 1:45.105 │ +0.000 │  ✓   │
│ 2   │ 1:49.205 │ +4.100 │      │
│ 3   │ 1:47.832 │ +2.727 │      │
└─────┴──────────┴────────┴──────┘

Tap lap → View detailed sector breakdown
```

#### C. Sector Analysis

```
Sector Performance (Lap 1)

S1  █████████░░░  7.82s  vs TBL: 6.99s  [+0.83s]
S2  ███████████░  25.09s vs TBL: 20.85s [+4.24s]
S3  ██░░░░░░░░░  0.19s  vs TBL: 0.19s  [+0.00s]
S4  ████████████ 42.49s vs TBL: 42.49s [+0.00s]
S5  ███░░░░░░░░  3.89s  vs TBL: 3.89s  [+0.00s]
S6  ████████████ 44.58s vs TBL: 44.58s [+0.00s]
S7  ██████░░░░░  21.03s vs TBL: 21.03s [+0.00s]

Green = Improved TBL
Red = Slower than TBL
```

#### D. Delta Chart (Advanced)

```
     Time Delta vs TBL
+5s  ┆          ╱╲
     ┆        ╱    ╲
 0s  ┆━━━━━━━━━━━━━━━━━━━
     ┆                  ╲
-5s  ┆                   ╲╱
     └────────────────────────
     S1  S2  S3  S4  S5  S6  S7

Shows where rider gained/lost time vs TBL
```

**API Endpoint:**

```
GET /api/sessions/{session_id}
  Response: Full session JSON (already UI-ready)
```

**Visualization Libraries:**

- **Charts:** Chart.js / Recharts / D3.js
- **Tables:** React Table / AG Grid
- **Maps:** Leaflet.js for track overlay

---

## Application Architecture

### Technology Stack Recommendations

#### Option A: Mobile App (React Native / Flutter)

**Pros:**

- Native mobile experience
- Can work offline after sync
- Best performance
  **Cons:**
- Deployment complexity (App Store/Play Store)
- Longer development time

#### Option B: Web App (React / Vue / Svelte)

**Pros:**

- Works on any device (phone, tablet, laptop)
- No installation needed
- Faster development
  **Cons:**
- Requires network connection
- Slightly less responsive

#### Option C: Hybrid (PWA - Progressive Web App)

**Pros:**

- Best of both worlds
- Installable like native app
- Works offline
  **Cons:**
- Some platform limitations

**Recommendation:** Start with **PWA (React/Vue)** for fastest delivery.

---

## Backend API (On Raspberry Pi)

### Minimal Flask Server

**File:** `src/api/server.py`

```python
from flask import Flask, jsonify, request, send_file
import os
import subprocess
import json

app = Flask(__name__)

# Enable CORS for companion app
from flask_cors import CORS
CORS(app)

@app.route('/api/tracks')
def get_tracks():
    with open('output/registry.json') as f:
        return jsonify(json.load(f))

@app.route('/api/tracks/<int:track_id>')
def get_track(track_id):
    # Load registry, find track by ID
    with open('output/registry.json') as f:
        registry = json.load(f)

    for track in registry['tracks']:
        if track['track_id'] == track_id:
            folder = track['folder_name']

            # Load track.json and tbl.json
            with open(f'output/tracks/{folder}/track.json') as tf:
                track_data = json.load(tf)

            with open(f'output/tracks/{folder}/tbl.json') as tbf:
                tbl_data = json.load(tbf)

            # Count sessions
            sessions = [f for f in os.listdir('output/sessions')
                       if f.startswith(f'{folder}_session_')]

            return jsonify({
                **track_data,
                'tbl': tbl_data,
                'sessions_count': len(sessions)
            })

    return jsonify({'error': 'Track not found'}), 404

@app.route('/api/tracks/<int:track_id>/map')
def get_track_map(track_id):
    # Find folder, return PNG
    with open('output/registry.json') as f:
        registry = json.load(f)

    for track in registry['tracks']:
        if track['track_id'] == track_id:
            folder = track['folder_name']
            return send_file(f'output/tracks/{folder}/track_map.png',
                           mimetype='image/png')

    return jsonify({'error': 'Map not found'}), 404

@app.route('/api/sessions')
def get_sessions():
    track_id = request.args.get('track_id')

    # List all sessions, optionally filter by track_id
    sessions = []
    for filename in os.listdir('output/sessions'):
        if filename.endswith('.json'):
            with open(f'output/sessions/{filename}') as f:
                session = json.load(f)

                # Filter if track_id provided
                if track_id and session['track']['track_id'] != int(track_id):
                    continue

                sessions.append({
                    'session_id': session['meta']['session_id'],
                    'date': session['meta']['start_time'],
                    'best_lap': session['summary']['best_lap_time'],
                    'total_laps': session['summary']['total_laps'],
                    'tbl_improved': session['summary']['tbl_improved'],
                    'track_name': session['track']['track_name']
                })

    # Sort by date (newest first)
    sessions.sort(key=lambda x: x['date'], reverse=True)
    return jsonify(sessions)

@app.route('/api/sessions/<session_id>')
def get_session(session_id):
    # Return full session JSON
    with open(f'output/sessions/{session_id}.json') as f:
        return jsonify(json.load(f))

@app.route('/api/process', methods=['POST'])
def process_session():
    csv_file = request.json['csv_file']

    # Validate file exists
    if not os.path.exists(csv_file):
        return jsonify({'error': 'File not found'}), 404

    # Run analysis script
    result = subprocess.run([
        'python3', 'src/analysis/run_analysis.py', csv_file
    ], capture_output=True, text=True)

    if result.returncode == 0:
        return jsonify({'status': 'complete', 'output': result.stdout})
    else:
        return jsonify({'status': 'error', 'error': result.stderr}), 500

@app.route('/api/tracks/<int:track_id>/rename', methods=['POST'])
def rename_track_api(track_id):
    new_name = request.json['new_name']

    # Run rename script
    result = subprocess.run([
        'python3', 'scripts/rename_track.py',
        '--track_id', str(track_id),
        '--new_name', new_name
    ], capture_output=True, text=True, input='y\n')

    if result.returncode == 0:
        return jsonify({'success': True, 'new_name': new_name})
    else:
        return jsonify({'success': False, 'error': result.stderr}), 400

@app.route('/api/learning/list')
def list_learning_files():
    files = []
    for filename in os.listdir('output/learning'):
        if filename.endswith('.csv'):
            path = f'output/learning/{filename}'
            stat = os.stat(path)
            files.append({
                'filename': filename,
                'size_kb': stat.st_size / 1024,
                'modified': stat.st_mtime
            })
    return jsonify(files)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

**Run on Pi:**
The API server runs automatically as a systemd service (`datalogger-api`) on Port 5000.

- **Check Status:** `sudo systemctl status datalogger-api`
- **Restart:** `sudo systemctl restart datalogger-api`
- **Logs:** `sudo journalctl -u datalogger-api -f`

**Access from companion:**

```
http://{pi_ip_address}:5000/api/tracks
```

### API Additions (Phase 7.5 - Export & Sharing)

**Endpoints:**

- `GET /api/sessions/<id>/export`
  - Returns `application/zip` containing session JSON and README.txt.
- `POST /api/sessions/<id>/rename`
  - Payload: `{ "new_name": "My Session" }`
  - Updates `meta.session_name`.

**Security Considerations:**

- Path Traversal: All file operations are sandboxed to `output/` directory using `os.path.basename`.
- Error Handling: Generic error messages returned to client to avoid exposing internal paths.

---

## UI Wireframes (Conceptual)

### Home Screen

```
┌─────────────────────────────────┐
│  Datalogger Companion           │
├─────────────────────────────────┤
│                                 │
│  [!] New Session Available      │
│      Process Now →              │
│                                 │
│  Recent Sessions                │
│    Today                        │
│    • Session 3 - 14:30          │
│      Kari Motor Speedway        │
│      Best: 1:45.2               │
│                                 │
│    Yesterday                    │
│    • Session 2 - 10:15          │
│      Best: 1:47.8               │
│                                 │
├─────────────────────────────────┤
│  [Tracks] [Sessions] [Settings] │
└─────────────────────────────────┘
```

### Tracks Screen

```
┌─────────────────────────────────┐
│  Tracks                         │
├─────────────────────────────────┤
│                                 │
│  ┌───────────────────────────┐ │
│  │  Kari Motor Speedway      │ │
│  │  [Track Map Image]        │ │
│  │                           │ │
│  │  5 sessions               │ │
│  │  Last: Dec 25, 14:30      │ │
│  │                           │ │
│  │  [Rename] [View Sessions] │ │
│  └───────────────────────────┘ │
│                                 │
│  ┌───────────────────────────┐ │
│  │  Bangalore Circuit        │ │
│  │  [Track Map Image]        │ │
│  └───────────────────────────┘ │
│                                 │
└─────────────────────────────────┘
```

### Session Detail Screen

```
┌─────────────────────────────────┐
│ ← Session 3                     │
├─────────────────────────────────┤
│  Kari Motor Speedway            │
│  Dec 25, 2025 14:30             │
│  Duration: 7:21                 │
│                                 │
│  Best Lap: 1:45.105 (Lap 1)    │
│  TBL: 2:20.032                  │
│                                 │
│  ─────────────────────────      │
│                                 │
│  Lap Times                      │
│  ┌───┬──────────┬────────┬───┐ │
│  │ # │ Time     │ Delta  │ ✓ │ │
│  ├───┼──────────┼────────┼───┤ │
│  │ 1 │ 1:45.105 │ +0.000 │ ✓ │ │
│  │ 2 │ 1:49.205 │ +4.100 │   │ │
│  │ 3 │ 1:47.832 │ +2.727 │   │ │
│  └───┴──────────┴────────┴───┘ │
│                                 │
│  [View Sectors] [View Delta]   │
└─────────────────────────────────┘
```

---

## Development Phases

### Phase 3.2a: Core Features (Week 1-2)

- ✅ Basic Flask API server
- ✅ Track list view
- ✅ Session list view
- ✅ Session detail view
- ✅ Process session trigger

### Phase 3.2b: Quality of Life (Week 3)

- ✅ Track rename functionality
- ✅ Date grouping for sessions
- ✅ Track map visualization
- ✅ Search/filter sessions

### Phase 3.2c: Advanced Analytics (Week 4)

- ✅ Sector comparison charts
- ✅ Delta visualization
- ✅ TBL progress tracking
- ✅ Lap-by-lap comparison

### Phase 3.2d: Polish (Optional)

- ✅ Offline mode
- ✅ Export session data (CSV/PDF)
- ✅ Dark mode
- ✅ Notifications

---

## Summary

**The companion app will:**

1. ✅ Connect to Pi via WiFi/FTP (implementation TBD)
2. ✅ Trigger CSV processing from learning data
3. ✅ Display tracks with visual maps
4. ✅ Allow track renaming
5. ✅ Show sessions organized by date
6. ✅ Provide rich session data visualization

**Architecture:**

- **Backend:** Lightweight Flask API on Pi
- **Frontend:** PWA (React/Vue) for cross-platform
- **Data:** Read-only access to `output/` directory
- **Scripts:** Trigger existing Python scripts via API

**All infrastructure already exists** - companion app is just a UI layer on top of the robust filesystem architecture built in Phase 3.1!

Ready to start Phase 3.2 when you are! 🚀
