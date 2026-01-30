# Datalogger V2 - Feature Gap Analysis

## Summary

This document identifies UI features and API endpoints that were designed for the Raspberry Pi-based datalogger but do not apply or need modification for the ESP32-only architecture.

---

## 🔴 PI-ONLY FEATURES (Not Applicable to ESP32)

### 1. System Settings - Auto-Start Logging on Boot
- **UI Location:** Settings View → System Card (line 324-329 in index.html)
- **Toggle ID:** `sysAutoStart`
- **API:** `/api/settings` (system.auto_start_logging)
- **Issue:** ESP32 doesn't have a systemd service to control. On ESP32, logging is controlled manually or via the boot.py script.
- **Recommendation:** Remove or repurpose as "Start logging when GPS fix is acquired"

### 2. System Settings - Disable Button when Auto-Start Active
- **UI Location:** Settings View → System Card (line 331-339 in index.html)
- **Toggle ID:** `sysDisableBtn`
- **API:** `/api/settings` (system.disable_button_with_auto_start)
- **Issue:** Pi had GPIO buttons; ESP32 doesn't have physical buttons in current implementation.
- **Recommendation:** Remove entirely

### 3. System Settings - Show Network Info on OLED
- **UI Location:** Settings View → System Card (line 341-347 in index.html)
- **Toggle ID:** `oledNetwork`
- **API:** `/api/settings` (oled.show_network)
- **Issue:** ESP32 implementation doesn't have OLED support. Pi had I2C OLED display.
- **Recommendation:** Remove unless OLED is added to ESP32

### 4. Firmware Update (ZIP) - Pi System Update
- **UI Location:** Settings View → System Card (line 349-362 in index.html)
- **JS Function:** `uploadUpdate()` (line 3515-3574 in app.js)
- **API:** `/api/system/update` (POST, not implemented in API)
- **Issue:** This was for updating Python files on the Pi. ESP32 has OTA via WiFi which is already implemented.
- **Recommendation:** Remove. ESP32 OTA is already handled in the ESP32 Firmware section.

### 5. Service Maintenance - Restart Individual Services
- **UI Location:** Settings View → Service Maintenance Card (line 519-536 in index.html)
- **Buttons:** "Restart Datalogger", "Restart Web API", "Restart Buttons"
- **JS Function:** `restartService()` (line 3588-3616 in app.js)
- **API:** `/api/system/services/restart` (POST, not implemented)
- **Issue:** Pi used systemd services (datalogger, datalogger-api, gpio_buttons). ESP32 is a single embedded process.
- **Recommendation:** Remove entirely. Could add "Reboot ESP32" button instead.

### 6. System Restart - Reboot Pi
- **UI Location:** Settings View → System Card (line 367-369 in index.html)
- **JS Function:** `restartSystem()` (line 3576-3586 in app.js)
- **API:** `/api/system/restart` (POST, not implemented)
- **Issue:** This rebooted the entire Pi. Could be repurposed for ESP32.
- **Recommendation:** Implement to send reboot command to ESP32 via `/reboot` endpoint

### 7. Diagnostics View - Hardware Test Mode
- **UI Location:** Diagnostics View (line 209-303 in index.html)
- **Features:**
  - I2C Bus Scan (`testI2C()`)
  - GPS Stream Test (`testGPS()`)
  - IMU Sensor Test (`testIMU()`)
  - LED Strip Test (`testLED()`)
  - Button Test (`testButtons()`)
- **APIs:** `/api/test/mode`, `/api/test/i2c`, `/api/test/gps`, `/api/test/imu`, `/api/test/led`, `/api/test/buttons` (mostly not implemented)
- **Issue:** This was for testing Pi GPIO hardware. ESP32 hardware is different (uses MicroPython drivers directly).
- **Recommendation:** Remove or reimplement to test ESP32 directly via HTTP to ESP32

### 8. Logs View - System Logs
- **UI Location:** Logs View (line 176-207 in index.html)
- **Options:** "System Log (JSON)", "GPIO Debug (Text)"
- **JS Function:** `fetchLogs()` (line 3623-3666 in app.js)
- **API:** `/api/system/logs` (not implemented)
- **Issue:** Pi had journald logs. ESP32 uses print() statements that go to serial.
- **Recommendation:** Remove or repurpose for viewing server logs only. ESP32 logs not accessible via WiFi by default.

### 9. Start/Stop Logging Buttons (Header)
- **UI Location:** Header (line 57-66 in index.html)
- **JS Functions:** `startLogging()`, `stopLogging()` (line 3872-3891 in app.js)
- **APIs:** `/api/logging/start`, `/api/logging/stop` (not implemented)
- **Issue:** Pi could start/stop logging via API. ESP32 controls logging internally via GPS state.
- **Recommendation:** Could implement to proxy to ESP32's `/log/start` and `/log/stop` endpoints

### 10. WiFi Scan & Connect (Pi's WiFi)
- **UI Location:** Settings View → Network Card (line 372-390 in index.html)
- **JS Functions:** `scanWifi()`, `submitWifiConnect()` (line 3441-3508 in app.js)
- **APIs:** `/api/wifi/status`, `/api/wifi/scan`, `/api/wifi/connect` (not implemented)
- **Issue:** This scanned WiFi networks from the Pi's perspective. With cloud backend, the server is on a different machine.
- **Recommendation:** Remove or change to scan/list networks visible to ESP32 (requires ESP32 endpoint)

### 11. Socket Command Communication
- **Code Location:** `send_socket_command()` in main.py (line 72-84)
- **Config:** `config.SOCKET_PATH`
- **Issue:** Pi used Unix domain sockets for IPC between API and datalogger service. Not applicable in cloud architecture.
- **Recommendation:** Remove. Communication with ESP32 is via HTTP.

### 12. Recording Status Indicator
- **UI Location:** Header (line 48-53 in index.html)
- **Poll Function:** `pollStatus()` checks `res.is_recording`
- **API:** `/api/status` returns `is_recording` (not implemented for ESP32)
- **Issue:** Relied on querying local Pi service. ESP32 status endpoint returns different data.
- **Recommendation:** Update to check ESP32 `/status` endpoint for logging state

### 13. LED Configuration - Full Event Map
- **UI Location:** Settings View → LED Configuration Card (line 493-517 in index.html)
- **Modal:** LED Config Modal (line 540-634 in index.html)
- **JS Functions:** `renderEventList()`, `openLedModal()`, `submitLedConfig()`, `testLedEvent()`
- **API:** `/api/settings` (led.events), `/api/test/led`
- **Issue:** Pi had neopixel strip with driver. ESP32 also has LED but config format may differ.
- **Recommendation:** Review if LED events are compatible with ESP32 LED manager. Likely needs adjustment.

---

## 🟡 MISSING API ENDPOINTS

These endpoints are called by the UI but not implemented in the API:

| Endpoint | Method | UI Usage | Status |
|----------|--------|----------|--------|
| `/api/status` | GET | Recording status | Partial - missing `is_recording` |
| `/api/logging/start` | POST | Start recording | Not implemented |
| `/api/logging/stop` | POST | Stop recording | Not implemented |
| `/api/system/restart` | POST | Reboot system | Not implemented |
| `/api/system/update` | POST | Upload update ZIP | Not implemented |
| `/api/system/services/restart` | POST | Restart services | Not implemented |
| `/api/system/logs` | GET | View system logs | Not implemented |
| `/api/wifi/status` | GET | WiFi connection status | Not implemented |
| `/api/wifi/scan` | GET | Scan networks | Not implemented |
| `/api/wifi/connect` | POST | Connect to network | Not implemented |
| `/api/test/mode` | POST | Enter/exit test mode | Not implemented |
| `/api/test/i2c` | GET | I2C bus scan | Not implemented |
| `/api/test/gps` | GET | GPS stream test | Not implemented |
| `/api/test/imu` | GET | IMU read test | Not implemented |
| `/api/test/buttons` | GET/POST | Button test | Not implemented |

---

## 🟢 WORKING FEATURES (ESP32-Compatible)

These features work correctly with the ESP32:

1. **Tracks Management** - View, rename, delete tracks
2. **Sessions Management** - View, analyze, compare sessions
3. **Trackdays** - Group sessions into trackdays
4. **Process View** - Sync from ESP32, process CSV files
5. **Device Scanning** - Find ESP32 on network
6. **Device WiFi Config** - Add/remove WiFi networks to ESP32
7. **ESP32 OTA Updates** - Flash firmware via WiFi
8. **Track Push to ESP32** - Sync track data to device
9. **Storage Indicator** - Shows ESP32 flash usage
10. **Active Track Badge** - Shows track set on ESP32

---

## 📋 RECOMMENDED ACTIONS

### High Priority (Remove/Hide)
1. Remove "Start/Stop Logging" buttons from header (or proxy to ESP32)
2. Hide Diagnostics View entirely (Pi-only hardware tests)
3. Hide Logs View or repurpose for server-only logs
4. Remove Service Maintenance section
5. Remove/hide WiFi Scan & Connect (for Pi networking)

### Medium Priority (Refactor)
1. Repurpose "Restart System" to reboot ESP32
2. Remove ZIP firmware update (ESP32 OTA is separate)
3. Update Recording Status to use ESP32's state
4. Review LED settings compatibility with ESP32

### Low Priority (Future)
1. Implement ESP32-specific diagnostics (test via ESP32 HTTP)
2. Add ESP32 log streaming (if WebSocket is added)
3. Settings persistence in cloud vs local file

---

## 📁 FILES TO MODIFY

| File | Changes Needed |
|------|----------------|
| `server/ui/index.html` | Remove/hide unused sections |
| `server/ui/app.js` | Remove dead code for unused features |
| `server/api/main.py` | Remove socket command code |
| `server/api/config.py` | Remove SOCKET_PATH |
