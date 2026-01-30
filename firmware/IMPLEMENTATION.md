# ESP32 Live Feedback Implementation

## Overview
This implementation brings track identification, sector timing feedback, and TBL (Theoretical Best Lap) comparison to the ESP32, with minimal resource usage.

## Architecture

### Data Flow
```
App --> POST /track/set --> ESP32 saves to /track.json
                            |
GPS Loop --> TrackEngine --> Sector Engine --> LED Feedback
```

### New Files
| File | Purpose | Size |
|------|---------|------|
| `lib/track_engine.py` | Track matching and sector timing logic | ~5KB |
| `/track.json` | Stored track metadata (pushed from app) | ~1KB |

### Modified Files
| File | Changes |
|------|---------|
| `lib/led_manager.py` | Added `trigger_event()`, `update_with_events()`, and flash animations |
| `lib/miniserver.py` | Added `POST /track/set` and `GET /track/status` endpoints |
| `main.py` | Integrated TrackEngine into logging thread and main loop |

---

## LED Priority System (Highest to Lowest)

| Priority | State | Animation | Duration |
|----------|-------|-----------|----------|
| 1 | Storage >= 90% | **Solid Red** | Permanent |
| 2 | Sector Complete (Fast) | 3x Green Flash | 600ms |
| 2 | Sector Complete (Neutral) | 3x Orange Flash | 600ms |
| 2 | Sector Complete (Slow) | 3x Red Flash | 600ms |
| 3 | Track Identified | Fast White Flash | 3 seconds |
| 4 | Logging (with/without track) | Blue Scanner | Continuous |
| 5 | GPS Searching | Red Breathe | Continuous |
| 6 | Idle | Dim Green Breathe | Continuous |

---

## API Endpoints

### `POST /track/set`
Save track metadata from the app. Body should be JSON:

```json
{
  "id": "kari_speedway",
  "name": "Kari Motor Speedway",
  "start_line": {"lat": 12.345678, "lon": 77.123456, "radius_m": 20},
  "sectors": [
    {"idx": 0, "end_lat": 12.346, "end_lon": 77.124},
    {"idx": 1, "end_lat": 12.347, "end_lon": 77.125}
  ],
  "tbl": {
    "0": 12.34,
    "1": 15.67,
    "2": 18.90
  }
}
```

Response:
```json
{"success": true, "track_name": "Kari Motor Speedway"}
```

### `GET /track/status`
Returns current track state:

```json
{
  "track_loaded": true,
  "track_name": "Kari Motor Speedway",
  "track_identified": false,
  "current_sector": 0,
  "sector_count": 3
}
```

---

## Thresholds

| Parameter | Value | Notes |
|-----------|-------|-------|
| Start Line Radius | 20m | Distance to trigger track identification |
| Sector Gate Radius | 15m | Distance to trigger sector crossing |
| Sector Fast Threshold | <= 0.2s | Green flash |
| Sector Neutral Threshold | <= 0.6s | Orange flash |
| Sector Slow Threshold | > 0.6s | Red flash |
| Storage Critical | >= 90% | Solid red LED |
| Storage Warning | >= 85% | Yellow pulse |

---

## Verification Steps

### 1. Deploy Code
```bash
cd firmware/esp32
./deploy.sh --sync
```

### 2. Push Track via API
```bash
curl -X POST http://<ESP_IP>/track/set \
  -H "Content-Type: application/json" \
  -d '{"id":"test","name":"Test Track","start_line":{"lat":12.9,"lon":77.6,"radius_m":20},"sectors":[{"idx":0,"end_lat":12.901,"end_lon":77.601}],"tbl":{"0":10.0}}'
```

### 3. Verify Track Loaded
```bash
curl http://<ESP_IP>/track/status
```

Expected:
```json
{"track_loaded": true, "track_name": "Test Track", ...}
```

### 4. Field Test
1. Drive near start line coordinates -> **White flash for 3 seconds**
2. Cross sector boundary:
   - Faster than TBL -> **Green flash**
   - Within 0.6s of TBL -> **Orange flash**
   - Slower than TBL by 0.6s+ -> **Red flash**
3. Fill storage to 90% -> **Solid red** overrides everything

---

## Memory Footprint

| Component | RAM Usage | Flash Usage |
|-----------|-----------|-------------|
| TrackEngine class | ~2KB | ~5KB |
| Track JSON (loaded) | ~1KB | ~1KB on disk |
| LED Event State | ~50 bytes | - |

Total additional overhead: **~3KB RAM, ~6KB Flash**
