# Strategic Plan: Web-Based BLE Handshake & 'Station' Sync Workflow

## 0. Hotspot Control
**Browser Limitation:** No web browser (Chrome/Safari) can toggle a system hotspot. This is a hard security boundary.
**Solution:** The UI must guide the user with a high-visibility modal: *"RS-Core is ready to sync. Please enable your Personal Hotspot now."*

## 1. Sync Trigger UX
- When the user hits "Sync from Device," a popup appears.
- It displays the stored Hotspot Name (SSID) and Password (obfuscated).
- Buttons: "Settings Correct, Start Sync" and "Change Hotspot Info."

## 2. Credential Transfer via BLE
- **Manual Input:** The browser cannot read system WiFi settings. We require a one-time manual entry in the web app settings.
- **Storage:** Credentials stored in browser `localStorage`.
- **Transfer:** Use the existing `CHAR_CONFIGURE_UUID` in `ble_provisioning.py`.
- **Protocol:** The browser sends a JSON string `{"ssid": "...", "pass": "..."}` via Web Bluetooth `writeValue()`.

## 3. BLE Connectivity & Indicators
- **Persistence:** Keeping BLE connected 24/7 is a battery drain. Better to use **On-Demand** connection for sync.
- **UI Indicator:** A "Paddock Link" icon in the header:
    - **Gray:** Not connected.
    - **Blue (Blinking):** Scanning/Linking.
    - **Solid Blue:** BLE Handshake Active.
    - **Green:** Station Sync Active (WiFi).

## 4. Firmware Architecture (ESP32-S3)
- **Idle State:** BLE Advertising ON, WiFi OFF.
- **Handshake State:** Receive credentials via BLE.
- **Sync State:** 
    1. BLE sends "ACK" to browser.
    2. ESP32 enters Station Mode (`network.STA_IF`).
    3. Connects to Hotspot.
    4. Performs HTTP POST of CSV files to the Nitro 5 backend.
    5. After success/timeout, reverts to Idle (WiFi OFF).

## 5. Post-Sync Notifications
- **Browser side:** The backend pings the browser (via WebSocket or long-polling) when the upload is complete.
- **UI Alert:** *"Sync Complete! You can now turn off your hotspot to save battery."*

## 6. BLE-Based File Listing (Pre-Sync Check)
- **Implementation:** Create a new BLE Characteristic `CHAR_FILE_LIST_UUID`.
- **Logic:**
    1. On BLE connect, browser reads this characteristic.
    2. ESP32 returns a comma-separated list or hash of filenames in `/sessions/`.
    3. Browser compares this against its "Processed Files" list.
    4. If no new files, the "Sync" button is disabled/hidden to avoid unnecessary hotspot usage.

## Technical Tasks
1. **Firmware:** Update `ble_provisioning.py` to support `CHAR_FILE_LIST_UUID`.
2. **Firmware:** Add Station mode connection logic triggered by BLE JSON.
3. **Frontend:** Update `ble-connector.js` to handle Web Bluetooth requestDevice and characteristic mapping.
4. **Frontend:** Build the "Sync Modal" in `index.html` and `app.js`.
