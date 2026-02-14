# Technical Specification: Web-BLE Hotspot Sync (v1.0)

## 1. Overview
The goal is a "Zero-Install" synchronization method where the browser handles the handshake with the RS-Core (ESP32-S3) and triggers a data offload using the phone's mobile hotspot as a bridge to the Nitro 5 backend.

## 2. BLE Protocol Definition
We will use the existing `SERVICE_UUID` (12345678-1234-5678-1234-567812345678).

### 2.1 Characteristics
| Characteristic | UUID | Property | Data Type | Description |
|----------------|------|----------|-----------|-------------|
| CHAR_STATUS | ...5002 | Read/Notify | JSON | wifi_status, sync_progress, battery_v |
| CHAR_CONFIGURE | ...5003 | Write | JSON | {"ssid": "...", "pass": "...", "url": "..."} |
| CHAR_FILE_LIST | ...5005 | Read | JSON | List of filenames in /sessions/ |

## 3. UI/UX Workflow (Web App)
1. **Paddock Link State:** A persistent icon in the header shows BLE status (Disconnected/Scanning/Linked).
2. **Sync Trigger:** User taps "Sync". 
   - **Step A:** Browser requests BLE connection.
   - **Step B:** Browser reads `CHAR_FILE_LIST`.
   - **Step C:** Compare against `localStorage.processed_files`.
   - **Step D:** If new files exist, show **Hotspot Modal**:
     - *"New data found! Please enable your hotspot [SSID: Racesense-Pit] now."*
     - Button: "I've turned it on - START SYNC".
3. **Execution:** 
   - Browser writes credentials + Nitro URL to `CHAR_CONFIGURE`.
   - Browser enters "Syncing..." state, listening to `CHAR_STATUS` notifications.
4. **Completion:**
   - Modal updates: *"Sync Complete! 12 Laps uploaded. You can turn off your hotspot."*
   - Browser updates `processed_files` index.

## 4. Firmware Requirements (ESP32-S3)
1. **Dual Mode Handling:** ESP32 must support BLE and WiFi STA simultaneously.
2. **File Offloader Module:**
   - Iterate through `/sessions/*.csv`.
   - For each file: Open, read chunks, and HTTP POST to `url/api/upload`.
   - On 200 OK: Move file to `/archive/` or delete (based on settings).
3. **Status Reporting:**
   - `{"state": "WIFI_CONNECTING"}`
   - `{"state": "SYNCING", "progress": 45, "file": "sess_1.csv"}`
   - `{"state": "IDLE"}`

## 5. Security & Persistence
- **Credentials:** Browser stores hotspot info in `localStorage`. 
- **Encryption:** (Optional for V1) Obfuscate credentials sent over BLE.
- **Backend URL:** The mobile app must pass the current Cloudflare Tunnel URL to the ESP32 so it knows where to POST.

## 6. Development Priorities
1. **Firmware:** Update `ble_provisioning.py` with `CHAR_FILE_LIST` and Station Mode logic.
2. **Backend:** Ensure `/api/upload` is robust to direct ESP32 POSTs (multipart/form-data or raw body).
3. **Frontend:** Implement Web Bluetooth GATT connection and Modal UI.
