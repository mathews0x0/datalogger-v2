# ESP32 Storage Architecture Migration Summary

**Date:** 2026-01-26

## Overview
Migrated ESP32 datalogger from SD card storage to **onboard flash memory** with cloud sync capabilities.

## What Changed

### Hardware
- ✅ **REMOVED:** SD Card Module (HW-125) and all SPI wiring
- ✅ **KEPT:** GPS Module only (UART on GPIO 26/27)
- ✅ **Result:** Simpler hardware, lower cost, smaller form factor

### Firmware (`firmware/esp32/`)

#### `main.py`
- Removed `from drivers.sdcard import SDCard` import
- Removed `PIN_SD_CS` configuration
- Removed `sd_mounted` global flag
- Removed entire SD card initialization block (30+ lines of SPI setup)
- Simplified to direct flash storage only

#### `lib/session_manager.py`
- Removed `sd_mounted` parameter from `__init__()`
- Removed `sync_to_sd()` method entirely
- Changed `get_log_file()` to return single path (not tuple)
- **Added new methods for cloud sync:**
  - `list_sessions()` - List all CSV files on flash
  - `get_session_data(filename)` - Read file content for upload
  - `delete_session(filename)` - Delete after successful sync
  - `get_storage_info()` - Monitor flash usage stats

### Documentation

#### `docs/ESP32_WIRING.md`
- Removed SD card wiring table and diagrams
- Updated mermaid diagram to show GPS-only setup
- Added "Storage Architecture" section explaining flash + cloud sync
- Added "Data Flow" section documenting ESP32 → Cloud pipeline

#### `docs/pm_diary.md`
- Added comprehensive Phase 14 entry documenting:
  - SD card removal rationale
  - WiFi dual-mode architecture (home network + AP fallback)
  - Network scanner implementation details
  - Connection status indicator UX
  - Settings loading bug fix
  - Technical debt identified
  - Full progress checklist

## New Architecture

### Data Flow
```
GPS → ESP32 (GPIO 26/27)
  ↓
Internal Flash (/sessions/*.csv)
  ↓
WiFi Upload (HTTP POST)
  ↓
Cloud Backend (firmware/pi/output/sessions/)
  ↓
Processing Pipeline (Lap Detection, TBL, etc.)
  ↓
Web UI Display
```

### Storage Capacity
- **ESP32 Flash:** ~4MB available
- **Estimated Capacity:** 200+ sessions (~10KB each)
- **Sync Strategy:** Upload to cloud, then delete local copy

### WiFi Modes
1. **Home WiFi (Priority):** Connect to configured network
2. **AP Fallback:** Create `Datalogger-AP` if home network unavailable
3. **Network Scanner:** Auto-discover device on local subnet (implemented in web UI)

## Files Modified

### Code Files
- `/firmware/esp32/main.py` - Removed SD card logic
- `/firmware/esp32/lib/session_manager.py` - Cloud sync methods added
- `/cloud-backend/api/main.py` - Fixed settings import path bug

### Documentation Files
- `/docs/ESP32_WIRING.md` - Hardware guide updated
- `/docs/pm_diary.md` - Phase 14 progress documented

## Next Steps

### Immediate Priorities
1. Implement `/api/device/upload` endpoint (backend receives CSV)
2. Build ESP32 HTTP POST client for uploading sessions
3. Test complete flow: Log → Store → Upload → Process → Display

### Future Enhancements
- Automatic sync on WiFi connect
- Periodic sync timer (e.g., every 5 minutes)
- Retry logic for failed uploads
- Compression for large session files
- OTA firmware updates via same WiFi connection

## Benefits Realized

✅ **Cost Savings:** $7-13 per unit (SD module + card)  
✅ **Simplified Assembly:** 6 fewer wire connections  
✅ **Better Reliability:** No mechanical failures, no corruption  
✅ **Lower Power:** No SPI bus activity  
✅ **Smaller Package:** Can use more compact enclosure  

---

**Status:** Migration Complete ✅  
**Ready For:** Cloud sync implementation
