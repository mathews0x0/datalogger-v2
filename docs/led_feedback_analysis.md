# LED Feedback: Minimal Device Exposure Analysis

## Your Use Case Recap

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   RIDE      │───▶│   PIT       │───▶│   CLOUD     │
│             │    │             │    │             │
│ Dumb Logger │    │ Phone Sync  │    │ Processing  │
│ (GPS/IMU)   │    │ Upload CSV  │    │ Track Learn │
│             │    │             │    │ Lap Detect  │
│             │    │             │    │ TBL Calc    │
└─────────────┘    └─────────────┘    └─────────────┘
```

**Current dumb logger = Fully protected. ✅**

**Problem: Adding LED feedback requires some on-device intelligence.**

---

## What LED Feedback Needs (Real-Time)

For the LED to show "you're faster/slower than your best" at each sector:

| Requirement | Real-Time Need | Data |
|-------------|----------------|------|
| Know current GPS position | Yes | Raw GPS stream |
| Know which sector you're in | Yes | Sector boundary coords |
| Know time since sector start | Yes | Simple timer |
| Know best sector time | Yes | TBL sector times |
| Compare and light LED | Yes | Trivial math |

---

## Minimal Data Needed on Device

After cloud sync, device receives a **"feedback package"** for known tracks:

```json
{
  "track_id": "coastt_hpc",
  "start_line": {
    "lat": 9.1234, "lon": 76.5678,
    "heading": 45,
    "radius": 15
  },
  "sectors": [
    {"lat": 9.1240, "lon": 76.5690, "heading": 90, "radius": 15},
    {"lat": 9.1250, "lon": 76.5700, "heading": 135, "radius": 15},
    // ... 7 sector boundaries
  ],
  "tbl_sectors": [28.5, 31.2, 29.8, 30.1, 27.9, 32.4, 28.0],
  "best_lap": 208.9
}
```

**Size: ~500 bytes per track.**

---

## What Code MUST Run on Device

### Option A: Minimal Comparator (Recommended)

**Device code (~100 lines):**

```python
# feedback_engine.py - EXPOSED (but trivial)

def is_crossing_line(gps, line):
    """Check if GPS position crosses a boundary line."""
    dist = haversine(gps.lat, gps.lon, line.lat, line.lon)
    return dist < line.radius

def get_sector_color(current_time, best_time):
    """Green if faster, Red if slower."""
    delta = current_time - best_time
    if delta < -0.5: return GREEN
    if delta > 0.5: return RED
    return YELLOW

# Main loop
while logging:
    gps = read_gps()
    
    for i, sector in enumerate(sectors):
        if is_crossing_line(gps, sector):
            sector_time = time.now() - sector_start
            color = get_sector_color(sector_time, tbl_sectors[i])
            led.show(color)
            sector_start = time.now()
```

**What's exposed:**
- `is_crossing_line()` - Simple geometry (public knowledge)
- `get_sector_color()` - Trivial comparison

**What's protected (cloud only):**
- HOW sector boundaries are calculated
- HOW TBL times are computed
- Track learning algorithm
- All analytics/diagnostics

---

### Option B: Encrypted Feedback Package

Same as Option A, but the feedback package is encrypted.

**How it works:**
1. Cloud encrypts the JSON with device-specific key
2. Device decrypts at runtime using hardware ID
3. Reverse engineering gets encrypted blob, not raw coords

**Protection level:** Medium (determined attacker can still dump RAM)

**Complexity:** Higher (need encryption layer)

---

### Option C: Obfuscated Boundaries (Sneaky)

Instead of sending raw lat/lon, cloud sends **transformed coordinates**:

```json
{
  "sectors": [
    {"x": 4523, "y": 8291, "t": 156},  // Not real GPS!
    {"x": 4589, "y": 8310, "t": 203}
  ],
  "transform_key": "abc123"
}
```

Device has a simple transform function:
```python
def to_gps(x, y, key):
    # Apply device-specific transform
    return real_lat, real_lon
```

**Attacker sees:** Meaningless numbers  
**Your cloud knows:** The transform for each device

---

## Comparison of Options

| Option | IP Exposure | Complexity | User Experience |
|--------|-------------|------------|-----------------|
| **A: Minimal Comparator** | Low (coords only) | Simple | Best |
| **B: Encrypted Package** | Very Low | Medium | Same |
| **C: Obfuscated Coords** | Very Low | Medium | Same |
| **D: No LED** | None | None | Worse |

---

## My Recommendation: Option A

**Why:**

1. **What you're exposing isn't valuable alone:**
   - 7 GPS coordinates (sector lines)
   - 7 float numbers (best times)
   - Anyone at the track can measure these manually

2. **What's protected is what matters:**
   - Your algorithm to FIND optimal sector placements
   - Your track learning system
   - Your cloud processing pipeline
   - Your user data and analytics

3. **The moat is the network effect:**
   - You'll have 50+ tracks learned
   - Cloner would need to learn each track themselves
   - Your cloud has TBL history, they have nothing

4. **Encryption adds complexity for marginal gain:**
   - If someone wants to clone, they'll just ride the track
   - Physical access = game over anyway (they can log their own GPS)

---

## Detailed Device Architecture

```
┌────────────────────────────────────────────────────────┐
│                    DEVICE (Pi)                          │
│                                                         │
│  ┌──────────────────┐  ┌────────────────────────────┐  │
│  │   LOGGER         │  │   FEEDBACK ENGINE          │  │
│  │   (Protected)    │  │   (Exposed but trivial)    │  │
│  │                  │  │                            │  │
│  │ • GPS @ 10Hz     │  │ • Load cached tracks.json  │  │
│  │ • IMU @ 100Hz    │  │ • Check sector crossings   │  │
│  │ • Write CSV      │  │ • Compare to TBL           │  │
│  │ • Timestamp      │  │ • Drive LED color          │  │
│  └──────────────────┘  └────────────────────────────┘  │
│           │                         │                   │
│           ▼                         ▼                   │
│     session.csv              feedback_cache.json        │
│     (upload to cloud)        (downloaded from cloud)    │
│                                                         │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                      CLOUD                              │
│                                                         │
│  • Track Learning Algorithm (SECRET)                   │
│  • Sector Optimization Logic (SECRET)                  │
│  • TBL Calculation Engine (SECRET)                     │
│  • Diagnostics & Analytics (SECRET)                    │
│  • User Accounts & Subscriptions                       │
│  • Generate feedback_cache.json per device             │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## What A Clone Would Get

**If someone copies your device code:**
- A GPS logger (commodity, worthless)
- An LED that lights up (only works with YOUR cloud's track data)
- No way to learn new tracks
- No analytics, no TBL, no comparisons
- Useless without paying for your cloud

**You still win.**

---

## Implementation Effort

| Component | Effort | Notes |
|-----------|--------|-------|
| Strip device code down | 2-3 days | Remove track learning, analysis |
| Cloud API for processing | 1 week | Port SessionProcessor to server |
| Cloud API for track data | 1 day | Return feedback_cache.json |
| Device feedback loader | 1 day | Load cached tracks on boot |
| End-to-end testing | 2-3 days | Test sync flow |
| **Total** | **~2 weeks** | |

---

## Alternative: Delayed LED (No Real-Time)

If you want ZERO device exposure:

**How it works:**
1. Device logs GPS/IMU (dumb logger)
2. After session, cloud processes
3. Next session: Device plays back LED patterns from cloud

**LEDs not truly "live"** but based on last session's data.

**Downside:** Not responsive to current performance, just historical.

---

## Final Recommendation

**Go with Option A (Minimal Comparator):**

1. Keep device code trivial and public-knowledge equivalent
2. Protect track learning and TBL algorithms in cloud
3. Accept that sector coordinates will be on device (not valuable alone)
4. Focus protection on the CLOUD services

**Your business moat is:**
- Pre-learned track database
- Cloud processing intelligence
- Subscription model enforcement
- Community and brand

Not a few hundred lines of geometry code.

---

*Created: 2026-01-22*
