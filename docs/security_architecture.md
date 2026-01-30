# IP Protection & Security Architecture

## The Problem

When you ship hardware, users have physical access to:
- SD card (can clone, read all files)
- Pi filesystem (can SSH, inspect code)
- Network traffic (can intercept API calls)

**Risk**: Your analysis algorithms, track learning logic, and UI could be copied.

---

## Architecture Options

### Option 1: Thin Client (Cloud-Heavy) ⭐ Recommended

```
┌────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Pi Device    │────▶│   Your Cloud     │────▶│   Phone App     │
│                │     │                  │     │                 │
│ • GPS Logger   │     │ • Track Learning │     │ • Visualization │
│ • IMU Logger   │     │ • Lap Detection  │     │ • Analysis UI   │
│ • LED Driver   │     │ • TBL Calc       │     │ • Account Mgmt  │
│ • Raw Upload   │     │ • Diagnostics    │     │                 │
└────────────────┘     └──────────────────┘     └─────────────────┘
     DUMB                   SMART                   DISPLAY
```

**What stays on Pi:**
- GPS/IMU data collection (10Hz logging)
- LED feedback driver
- Raw CSV generation
- WiFi/upload agent
- Device authentication

**What moves to Cloud:**
- Track identification & learning
- Lap detection algorithms
- Sector segmentation
- TBL calculation
- Session analysis
- Diagnostics engine
- All "intelligence"

**Pros:**
- Pi code is worthless without cloud
- Can update algorithms without device update
- Subscription enforceable (no cloud = no analysis)
- Can't be cloned meaningfully

**Cons:**
- Requires internet after trackday
- Cloud infrastructure cost (~₹5,000/month for 500 users)
- Latency for analysis

---

### Option 2: Signed Binary / Encrypted Core

```
┌────────────────────────────────────────┐
│               Pi Device                 │
│                                         │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │ Open Source  │  │ Encrypted Core  │ │
│  │ • Logger     │  │ • Analysis.so   │ │
│  │ • LED        │  │ • Track Learn   │ │
│  │ • Companion  │  │ • Lap Detect    │ │
│  └──────────────┘  └─────────────────┘ │
│                           │             │
│                    Hardware Key         │
│                    (Pi Serial)          │
└────────────────────────────────────────┘
```

**How it works:**
- Core algorithms compiled to binary (.so file)
- Binary encrypted with Pi's unique serial number
- License file signed by your server
- Decryption key derived from hardware ID

**Pros:**
- Works fully offline
- Hard to reverse engineer
- Can still revoke licenses remotely

**Cons:**
- Binary can still be cracked (dedicated attacker)
- Requires compilation pipeline
- Updates are harder

---

### Option 3: Hybrid (Best of Both)

```
┌─────────────────┐     ┌──────────────────┐
│   Pi Device     │────▶│   Cloud          │
│                 │     │                  │
│ • Logging       │     │ • Track DB       │
│ • Basic laps    │◀────│ • License check  │
│ • LED (basic)   │     │ • Advanced AI    │
│ • Local cache   │     │ • Sync           │
└─────────────────┘     └──────────────────┘
```

**Division:**
| Feature | Location | Why |
|---------|----------|-----|
| GPS/IMU logging | Device | Real-time, offline |
| Basic lap timing | Device | Works without internet |
| LED feedback | Device | Real-time requirement |
| Track learning | Cloud | Your IP |
| TBL calculation | Cloud | Your IP |
| Sector analysis | Cloud | Your IP |
| Diagnostics | Cloud | Your IP |
| Comparison/Ghost | Cloud | Your IP |

**User Experience:**
1. Ride at track (device logs + basic laps locally)
2. Return to WiFi, device syncs raw data to cloud
3. Cloud processes, returns full analysis
4. Next trackday: device has cached track data

---

## Security Layers

### Layer 1: Device Authentication

```python
# Each device has unique ID burned at manufacture
DEVICE_ID = get_pi_serial()  # e.g., "0000000012345678"

# On boot, device proves identity to cloud
token = cloud.authenticate(DEVICE_ID, HMAC_SECRET)
```

### Layer 2: License Validation

```json
// License file on device (signed by your server)
{
  "device_id": "0000000012345678",
  "plan": "pro",
  "expires": "2027-01-22",
  "signature": "base64_signature_here"
}
```

Device validates signature using your public key. Can't forge without private key.

### Layer 3: Feature Gating

```python
def analyze_session(csv_file):
    if not license.is_valid():
        return {"error": "License expired"}
    
    if license.plan == "free":
        return basic_lap_times(csv_file)
    
    # Full analysis only for paid
    return cloud.full_analysis(csv_file)
```

### Layer 4: Code Obfuscation (Optional)

- Use PyArmor or Cython to compile Python to binary
- Won't stop determined attacker but raises the bar
- Cost: ~$500 one-time for PyArmor

---

## What You CAN'T Protect (Accept This)

| Exposed | Risk Level | Mitigation |
|---------|------------|------------|
| GPS logging code | Low | Trivial to rewrite |
| IMU calibration | Medium | Math is public anyway |
| LED patterns | Low | Not your moat |
| UI design | Medium | Easy to copy |
| Track detection algo | **High** | Keep in cloud |
| Sector optimization | **High** | Keep in cloud |
| TBL calculation | **High** | Keep in cloud |

---

## Recommended Architecture

### For Your Product

```
DEVICE (Exposed, OK to copy)          CLOUD (Protected)
─────────────────────────             ─────────────────
config.py                             /api/analyze
gps_module.py                         /api/tracks
imu_module.py                         /api/sessions
led_driver.py                         /api/diagnostics
raw_logger.py                         /api/compare
uploader.py                           /api/license
companion_basic.py                    Track Learning Engine
                                      Lap Detection Engine
                                      TBL Calculator
                                      Consistency Analyzer
```

### Cloud Stack Suggestion

| Component | Service | Cost/month |
|-----------|---------|------------|
| API Server | Railway / Render | ₹1,500 |
| Database | Supabase / PlanetScale | ₹0 (free tier) |
| File Storage | Cloudflare R2 | ₹500 |
| Auth | Supabase Auth | ₹0 |
| **Total** | | **~₹2,000/month** |

Scales to 1,000+ users before needing upgrade.

---

## Implementation Phases

### Phase 1: Current (Local-Only)
- Everything runs on device
- No protection, but you learn what works

### Phase 2: Add Cloud Sync
- Sessions upload to cloud after trackday
- Cloud stores as backup
- Device still does all analysis

### Phase 3: Move Analysis to Cloud
- Migrate SessionProcessor to cloud
- Device becomes "dumb logger"
- Subscription enforced

### Phase 4: Advanced Features (Cloud-Only)
- Cross-rider comparisons
- Track leaderboards
- AI coaching suggestions

---

## Quick Decision Matrix

| Priority | Choose |
|----------|--------|
| Maximum protection | **Thin Client (Cloud-Heavy)** |
| Offline-first UX | **Encrypted Binary** |
| Balanced | **Hybrid** |
| MVP speed | **Ship now, protect later** |

---

## My Recommendation

**Start with Hybrid:**
1. Ship current product (local-only)
2. Add cloud sync + accounts (2-3 weeks work)
3. Gradually move IP to cloud as you identify what's valuable
4. Don't over-engineer security before you have customers

The real moat isn't code—it's:
- Your track database (network effect)
- Your community of riders
- Your iteration speed
- Your brand trust

*Created: 2026-01-22*
