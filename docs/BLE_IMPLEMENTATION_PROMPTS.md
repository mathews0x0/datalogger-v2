# BLE WiFi Provisioning - Implementation Guide & Prompts

**Date:** 2026-02-02  
**Status:** Implementation Ready  
**Goal:** Implement BLE-based WiFi provisioning for ESP32 Datalogger

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Implementation Order](#implementation-order)
3. [Component 1: ESP32 BLE Service](#component-1-esp32-ble-service)
4. [Component 2: Web Bluetooth UI](#component-2-web-bluetooth-ui)
5. [Component 3: Integration with Existing Code](#component-3-integration-with-existing-code)
6. [Testing Checklist](#testing-checklist)

---

## Architecture Overview

### The Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: User opens Web App, clicks "Connect Device"                    │
│                                                                         │
│  STEP 2: Browser shows BLE device picker → User selects "Datalogger"    │
│                                                                         │
│  STEP 3: Web App reads available WiFi networks from ESP32 (via BLE)     │
│                                                                         │
│  STEP 4: User selects their home WiFi and enters password               │
│                                                                         │
│  STEP 5: Web App sends credentials to ESP32 (via BLE)                   │
│                                                                         │
│  STEP 6: ESP32 connects to WiFi, reports back IP address (via BLE)      │
│                                                                         │
│  STEP 7: Web App now communicates with ESP32 over WiFi (HTTP)           │
│                                                                         │
│  STEP 8: If no common WiFi → ESP32 starts AP, user connects manually    │
└─────────────────────────────────────────────────────────────────────────┘
```

### File Structure (What We're Creating)

```
firmware/
├── lib/
│   ├── ble_provisioning.py    # NEW - BLE service for WiFi setup
│   ├── wifi_manager.py        # MODIFY - Add BLE integration
│   └── miniserver.py          # EXISTING - No changes
├── main.py                    # MODIFY - Add BLE initialization
└── boot.py                    # EXISTING - No changes

server/
├── ui/
│   ├── app.js                 # MODIFY - Add BLE connect flow
│   ├── index.html             # MODIFY - Add BLE UI elements
│   └── ble-connector.js       # NEW - Web Bluetooth module
└── api/
    └── main.py                # EXISTING - No changes
```

---

## Implementation Order

| Order | Component | File | Effort |
|-------|-----------|------|--------|
| 1 | ESP32 BLE Service | `firmware/lib/ble_provisioning.py` | Medium |
| 2 | Integrate BLE into main.py | `firmware/main.py` | Low |
| 3 | Web Bluetooth Module | `server/ui/ble-connector.js` | Medium |
| 4 | UI Integration | `server/ui/app.js` + `index.html` | Low |
| 5 | Testing & Polish | - | Low |

---

## Component 1: ESP32 BLE Service

### Context for Gemini

Before giving the prompt, Gemini needs to understand the context:

**Project Context:**
- ESP32 running MicroPython (standard ESP32 MicroPython firmware)
- Device is a GPS datalogger that needs WiFi to sync data to cloud
- Currently uses `lib/wifi_manager.py` for WiFi connection
- Has `lib/miniserver.py` for HTTP API
- Uses `lib/session_manager.py` for session storage

**BLE Requirements:**
- Advertise as "Datalogger-XXXX" (XXXX = last 4 chars of MAC)
- Expose GATT service with characteristics for:
  - WiFi scanning (read list of available networks)
  - WiFi status (current connection state, IP address)
  - WiFi configuration (receive SSID + password)
  - Device info (firmware version, storage status)

---

### PROMPT 1: ESP32 BLE Provisioning Service

Copy this prompt exactly to Gemini:

```
=== PROMPT START ===

Create a MicroPython BLE provisioning module for ESP32. This will be used to configure WiFi credentials from a phone/laptop via Bluetooth Low Energy.

**File:** `lib/ble_provisioning.py`

**Requirements:**

1. **Class Name:** `BLEProvisioning`

2. **BLE Service UUID:** `0000180A-0000-1000-8000-00805F9B34FB` (Device Information base, but use custom)
   - Actually use: `12345678-1234-5678-1234-567812345678` for custom service

3. **Characteristics (all under the main service):**

   | Name | UUID | Properties | Description |
   |------|------|------------|-------------|
   | WiFi Networks | `12345678-1234-5678-1234-567812345001` | READ | JSON array of available SSIDs |
   | WiFi Status | `12345678-1234-5678-1234-567812345002` | READ, NOTIFY | JSON: {connected, ssid, ip, mode} |
   | WiFi Configure | `12345678-1234-5678-1234-567812345003` | WRITE | Receive JSON: {ssid, password} or "SCAN" or "START_AP" |
   | Device Info | `12345678-1234-5678-1234-567812345004` | READ | JSON: {version, storage_pct, gps_status} |

4. **Advertising:**
   - Name: "Datalogger-XXXX" where XXXX = last 4 hex chars of device MAC address
   - Include service UUID in advertisement

5. **Methods:**
   ```python
   class BLEProvisioning:
       def __init__(self, wifi_manager=None, session_manager=None):
           """Initialize BLE with optional references to other managers"""
       
       def start(self):
           """Start BLE advertising"""
       
       def stop(self):
           """Stop BLE advertising"""
       
       def is_connected(self) -> bool:
           """Return True if a BLE central is connected"""
       
       def update_device_info(self, gps_valid: bool, storage_pct: float):
           """Update device info characteristic (call from main loop)"""
       
       def notify_wifi_status(self, connected: bool, ssid: str, ip: str, mode: str):
           """Send notification to connected client about WiFi state"""
   ```

6. **WiFi Scanning Logic:**
   - When client reads "WiFi Networks" characteristic, perform a WiFi scan
   - Return JSON array: `["HomeWiFi", "OfficeNet", "Neighbor5G"]`
   - Maximum 10 networks, sorted by signal strength

7. **WiFi Configuration Logic:**
   - When client writes to "WiFi Configure":
     - If value is `"SCAN"`: Trigger fresh WiFi scan, update Networks characteristic
     - If value is `"START_AP"`: Start AP mode, update Status characteristic
     - If value is JSON `{"ssid": "X", "password": "Y"}`: 
       - Save credentials using `wifi_manager.add_credential(ssid, password)` if wifi_manager provided
       - Attempt connection
       - Update Status characteristic with result

8. **Status Updates:**
   - After any WiFi change, update the Status characteristic
   - If client is connected, send NOTIFY

9. **Error Handling:**
   - If BLE fails to initialize, print error but don't crash
   - All WiFi operations should have timeouts

10. **Imports:**
    - Use `bluetooth` module (built into ESP32 MicroPython)
    - Use `network` for WiFi operations
    - Use `json` for serialization
    - Use `ubinascii` for MAC address

**Example Usage:**
```python
from lib.ble_provisioning import BLEProvisioning
from lib.wifi_manager import add_credential, connect_or_ap

# In main.py setup
ble = BLEProvisioning()
ble.start()

# In main loop
ble.update_device_info(gps_valid=True, storage_pct=75.5)
```

**Important Notes:**
- Use `micropython.const()` for IRQ constants to save memory
- Keep characteristic values under 512 bytes
- Handle multiple simultaneous connections gracefully
- The ESP32 should continue working even if BLE fails

Generate the complete, production-ready code.

=== PROMPT END ===
```

---

## Component 2: Web Bluetooth UI

### Context for Gemini

**Project Context:**
- Web UI is a single-page app using vanilla JavaScript
- Main app file is `server/ui/app.js` (large file with existing functionality)
- Uses `apiCall()` helper for HTTP requests
- Uses `showToast()` for notifications
- Has a settings tab where device connection is managed

**Web Bluetooth Requirements:**
- Create a reusable BLE connector module
- Handle connect, disconnect, reconnect
- Read/write characteristics
- Subscribe to notifications
- Work on Chrome macOS and Chrome Android

---

### PROMPT 2: Web Bluetooth Connector Module

Copy this prompt exactly to Gemini:

```
=== PROMPT START ===

Create a JavaScript module for Web Bluetooth communication with an ESP32 datalogger device.

**File:** `server/ui/ble-connector.js`

**Requirements:**

1. **Class Name:** `DataloggerBLE`

2. **Service and Characteristic UUIDs:** (must match ESP32)
   ```javascript
   const SERVICE_UUID = '12345678-1234-5678-1234-567812345678';
   const CHAR_NETWORKS_UUID = '12345678-1234-5678-1234-567812345001';
   const CHAR_STATUS_UUID = '12345678-1234-5678-1234-567812345002';
   const CHAR_CONFIGURE_UUID = '12345678-1234-5678-1234-567812345003';
   const CHAR_DEVICE_INFO_UUID = '12345678-1234-5678-1234-567812345004';
   ```

3. **Public Methods:**
   ```javascript
   class DataloggerBLE {
       constructor()
       
       // Connection
       async connect()           // Opens browser BLE picker, connects
       async disconnect()        // Gracefully disconnect
       isConnected()             // Returns boolean
       
       // WiFi Operations
       async scanNetworks()      // Returns array of SSIDs
       async getWifiStatus()     // Returns {connected, ssid, ip, mode}
       async configureWifi(ssid, password)  // Send credentials, returns result
       async startAPMode()       // Tell device to start AP
       
       // Device Info
       async getDeviceInfo()     // Returns {version, storage_pct, gps_status}
       
       // Event Callbacks (set these)
       onConnect = null          // Called when connected
       onDisconnect = null       // Called when disconnected
       onStatusChange = null     // Called when WiFi status notification received
       onDeviceInfoChange = null // Called when device info notification received
   }
   ```

4. **Connection Flow:**
   - Use `navigator.bluetooth.requestDevice()` with filter for name prefix "Datalogger"
   - Connect to GATT server
   - Get primary service
   - Get all characteristics
   - Subscribe to notifications on Status and DeviceInfo characteristics
   - Call `onConnect` callback

5. **Reconnection Logic:**
   - If device disconnects unexpectedly, try to reconnect automatically (3 attempts)
   - Wait 2 seconds between attempts

6. **Error Handling:**
   - Wrap all BLE operations in try-catch
   - Return meaningful error messages
   - Check if Web Bluetooth is supported before operations

7. **Helper Function:**
   ```javascript
   static isSupported() {
       return 'bluetooth' in navigator;
   }
   ```

8. **Text Encoding:**
   - Use `TextEncoder` for writing
   - Use `TextDecoder` for reading
   - Parse JSON responses

9. **Notification Handling:**
   - When Status characteristic notifies, parse JSON and call `onStatusChange(status)`
   - When DeviceInfo notifies, parse JSON and call `onDeviceInfoChange(info)`

**Example Usage:**
```javascript
const ble = new DataloggerBLE();

ble.onConnect = () => console.log('Connected!');
ble.onDisconnect = () => console.log('Disconnected');
ble.onStatusChange = (status) => {
    console.log(`WiFi: ${status.connected ? status.ssid : 'Disconnected'}`);
    if (status.connected) {
        updateDeviceIP(status.ip);
    }
};

// Connect button click
await ble.connect();

// Get available networks
const networks = await ble.scanNetworks();
console.log('Available networks:', networks);

// Configure WiFi
const result = await ble.configureWifi('HomeWiFi', 'password123');
if (result.success) {
    console.log(`Connected to WiFi! IP: ${result.ip}`);
}
```

**Browser Compatibility:**
- Must work on Chrome 56+ (macOS, Windows, Android)
- Gracefully fail on unsupported browsers (Safari, Firefox)

Generate the complete, production-ready code with JSDoc comments.

=== PROMPT END ===
```

---

### PROMPT 3: UI Integration Code

Copy this prompt exactly to Gemini:

```
=== PROMPT START ===

Create the HTML and JavaScript code to integrate BLE WiFi provisioning into an existing web app.

**Context:**
- Existing app has a Settings tab with device connection options
- Currently uses WiFi scanning via HTTP API
- Need to add BLE as the PRIMARY connection method
- Existing helpers: `showToast(message, type)`, `apiCall(endpoint, options)`

**File 1: HTML snippet to add to Settings tab** (`settings-ble-section.html`)

Create a complete HTML section for BLE connection with:
1. "Connect via Bluetooth" button with BLE icon
2. Connection status indicator (Disconnected → Connecting → Connected)
3. WiFi network selector dropdown (populated after BLE connect)
4. Password input field
5. "Connect to WiFi" button
6. Alternative: "Use Device Hotspot" button
7. Status messages area

Style Requirements:
- Use CSS classes (no inline styles)
- Modern, clean design
- Icons using Unicode symbols (no external libraries)
- Responsive layout

**File 2: JavaScript integration code** (`ble-integration.js`)

Create code that:
1. Imports/uses `DataloggerBLE` class from `ble-connector.js`
2. Initializes BLE on page load (check if supported)
3. Handles "Connect via Bluetooth" button click
4. After BLE connect:
   - Automatically scan for WiFi networks
   - Populate dropdown with results
   - Show password input
5. Handles "Connect to WiFi" button:
   - Send credentials via BLE
   - Show progress
   - On success: Save IP to localStorage, show success, switch to WiFi mode
   - On failure: Show error, allow retry
6. Handles "Use Device Hotspot" button:
   - Tell device to start AP
   - Show instructions to user
7. Updates UI based on connection state
8. Integrates with existing device status polling

**State Machine:**
```
IDLE → BLE_CONNECTING → BLE_CONNECTED → WIFI_CONFIGURING → WIFI_CONNECTED
  ↓                          ↓               ↓                    ↓
  └── (user clicks) ←── (BLE lost) ←── (failed) ←── (disconnect) ←┘
```

**Example UI Flow:**
```
┌─────────────────────────────────────────────────────────┐
│  📱 Device Connection                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [🔵 Connect via Bluetooth]                             │
│                                                         │
│  Status: Not connected                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘

After BLE connect:

┌─────────────────────────────────────────────────────────┐
│  📱 Device Connection                      [Disconnect] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ✅ Connected to Datalogger-A1B2 (Bluetooth)            │
│                                                         │
│  Select WiFi Network:                                   │
│  ┌─────────────────────────────────────────────────┐    │
│  │ HomeWiFi                                    ▼   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Password:                                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ••••••••                                        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  [Connect to WiFi]    [Use Device Hotspot Instead]      │
│                                                         │
└─────────────────────────────────────────────────────────┘

After WiFi connect:

┌─────────────────────────────────────────────────────────┐
│  📱 Device Connection                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ✅ Connected via WiFi                                  │
│  IP: 192.168.1.42                                       │
│  Device: Datalogger-A1B2                                │
│                                                         │
│  [Disconnect]  [Reconfigure WiFi]                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**LocalStorage Keys:**
- `datalogger.deviceIP` - Last known device IP
- `datalogger.deviceName` - Last connected device name
- `datalogger.wifiSSID` - Last configured WiFi SSID

Generate complete, production-ready code with comments.

=== PROMPT END ===
```

---

## Component 3: Integration with Existing Code

### PROMPT 4: main.py Integration

Copy this prompt exactly to Gemini:

```
=== PROMPT START ===

Modify an existing ESP32 MicroPython main.py to integrate BLE provisioning.

**Current main.py structure:**
```python
# main.py - Unified Datalogger Firmware
import machine
import time
import os
import gc
import _thread

from drivers.gps import GPS
from drivers.bmi323 import BMI323
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine
from lib.wifi_manager import connect_or_ap
from lib.miniserver import MiniServer

# Pin definitions...

def setup():
    # Initialize LED, wait for power stability
    # Mount SD card
    # Initialize SessionManager
    # Initialize IMU
    # Initialize GPS
    # Initialize TrackEngine
    # Connect WiFi (currently blocks for ~10-20 seconds)
    # Start MiniServer in thread
    return led, gps, imu, sm, track_eng, mode

def main_loop():
    led, gps, imu, sm, track_eng, wifi_mode = setup()
    # Main logging loop...
```

**Required Changes:**

1. **Add BLE import:**
   ```python
   from lib.ble_provisioning import BLEProvisioning
   ```

2. **Initialize BLE early in setup() (before WiFi):**
   - Create BLEProvisioning instance
   - Pass wifi_manager and session_manager references
   - Start BLE advertising

3. **New WiFi connection flow:**
   ```python
   # Option A: Check if we have saved credentials
   mode, ip = connect_or_ap()  # Existing function
   
   # Option B: If no credentials, BLE is already advertising
   # User will provision via BLE, which will trigger WiFi connect
   ```

4. **In main_loop, update BLE with device status:**
   - Every second (or every 10th loop iteration):
     ```python
     ble.update_device_info(
         gps_valid=fix['valid'],
         storage_pct=usage
     )
     ```

5. **Handle BLE-triggered WiFi reconnection:**
   - BLE module may trigger WiFi connection
   - Listen for connection events and update miniserver IP if needed

**Output:** 
Generate ONLY the modified sections of main.py, clearly marked with:
- `# ADD AFTER LINE X:` for new code
- `# REPLACE LINES X-Y:` for modifications

Do not generate the entire file, just the changes needed.

=== PROMPT END ===
```

---

## Testing Checklist

After implementing all components, test in this order:

### Test 1: ESP32 BLE Advertising
```
[ ] Flash updated firmware to ESP32
[ ] ESP32 boots and shows "BLE advertising..." in serial
[ ] On Mac: System Preferences → Bluetooth shows "Datalogger-XXXX"
```

### Test 2: Web Bluetooth Connection
```
[ ] Open Chrome on Mac
[ ] Go to localhost:6969 (your web app)
[ ] Click "Connect via Bluetooth"
[ ] Chrome shows BLE device picker
[ ] Select "Datalogger-XXXX"
[ ] UI shows "Connected"
```

### Test 3: WiFi Scanning via BLE
```
[ ] After BLE connect, networks dropdown populates
[ ] Your home WiFi appears in list
[ ] ESP32 serial shows "BLE: Scan request received"
```

### Test 4: WiFi Configuration via BLE
```
[ ] Select home WiFi from dropdown
[ ] Enter password
[ ] Click "Connect to WiFi"
[ ] ESP32 connects to WiFi
[ ] BLE notifies with IP address
[ ] UI shows "Connected via WiFi: 192.168.X.X"
```

### Test 5: Full Flow
```
[ ] Power cycle ESP32
[ ] ESP32 auto-connects to saved WiFi
[ ] Web app can reach ESP32 via HTTP
[ ] Device status shows in UI
```

---

## Troubleshooting

### BLE not advertising
- Check ESP32 serial output for BLE errors
- Ensure `bluetooth` module is available in firmware
- Try: `import bluetooth; print(bluetooth.BLE())`

### Chrome doesn't show device picker
- Ensure Chrome has Bluetooth permission (System Preferences → Security & Privacy → Bluetooth)
- Try `chrome://flags` and enable "Experimental Web Platform features"
- Check if another app is connected to ESP32 BLE

### WiFi scan returns empty
- ESP32 may need antenna
- Ensure WiFi radio is active before scan
- Check for scan timeout

### WiFi connect fails
- Verify SSID spelling (case-sensitive)
- Check password
- ESP32 may be out of range

---

## Quick Reference: UUIDs

| Characteristic | UUID | Purpose |
|----------------|------|---------|
| Service | `12345678-1234-5678-1234-567812345678` | Main service |
| Networks | `12345678-1234-5678-1234-567812345001` | Read WiFi list |
| Status | `12345678-1234-5678-1234-567812345002` | WiFi state |
| Configure | `12345678-1234-5678-1234-567812345003` | Send credentials |
| Device Info | `12345678-1234-5678-1234-567812345004` | GPS/storage |

---

## Next Steps After Implementation

1. **Test on Android phone** - Same Web Bluetooth flow should work
2. **Add mDNS** - ESP32 advertises as `datalogger.local` for easier HTTP access
3. **iOS planning** - Evaluate React Native / Capacitor for native BLE wrapper
4. **Security** - Add BLE pairing with PIN for production

