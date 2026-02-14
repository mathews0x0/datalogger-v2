# Racesense Connectivity Setup Plan (v1.0)

## 1. Problem Statement
The current connectivity between the Racesense Core (ESP32-S3) and the Web UI has the following points of failure:
- **macOS/iOS Visibility:** The device is often not listed in the browser's Bluetooth picker due to OS-level security and lack of explicit service filtering.
- **WiFi Friction:** Mobile browsers cannot programmatically switch WiFi networks, forcing a clunky manual "leave browser -> join ESP32 -> return to browser" flow.
- **Platform Fragmentation:** Safari on iOS does not support Web Bluetooth, requiring a specialized browser (Bluefy) without a clear user guide.

## 2. The Solution: "Reverse Hotspot" + Explicit Filtering
We will move to a **"Zero-Install" Web-BLE** model that handles the data transfer by turning the ESP32 into a client (Station) rather than an Access Point.

### Core Architectural Changes:
1. **Explicit BLE Advertising:** The ESP32 will advertise specifically with our Service UUID (`12345678-1234-5678-1234-567812345678`) and a friendly name (`Racesense-Core`).
2. **Reverse Hotspot Sync:** The browser will use BLE to send the **Phone's Hotspot credentials** to the ESP32. The ESP32 will then join the phone's internet to upload files.
3. **Sync Wizard UI:** A step-by-step guide in the Web UI to handle pairing, platform detection (iOS/macOS), and the hotspot toggle.

## 3. Implementation Plan

### Task 1: Firmware Update (BLE & WiFi)
- [ ] Rename advertising name to `Racesense-Core`.
- [ ] Ensure Service UUID is included in the advertising payload (fixing macOS visibility).
- [ ] Implement `STA_CONNECT` command logic: receive JSON `{"ssid": "...", "pass": "...", "target_url": "..."}`.
- [ ] Implement robust `uploader.py` to POST CSV files to the Nitro backend.

### Task 2: Web UI "Sync Wizard"
- [ ] Implement `BleService.js` using `navigator.bluetooth.requestDevice({ filters: [{ services: [SERVICE_UUID] }] })`.
- [ ] Create a responsive `SyncModal` component with:
    - Platform detection (Shows "Use Bluefy" for iOS, "Check Permissions" for macOS).
    - Pairing trigger.
    - Hotspot credential entry/storage.
    - Real-time progress bar synced via BLE `CHAR_STATUS`.

### Task 3: Backend Hardening
- [ ] Update `/api/upload` to handle multipart/form-data from the ESP32 client.
- [ ] Implement auto-trigger for `run_analysis.py` upon successful upload.

## 4. Test Cases

| ID | Case | Expected Result |
| :--- | :--- | :--- |
| **TC-01** | **Discovery (Linux/macOS)** | Chrome picker lists `Racesense-Core` within 3s of scan. |
| **TC-02** | **Pairing** | Browser successfully connects and reads battery/status chars. |
| **TC-03** | **Provisioning** | Hotspot credentials sent via BLE are successfully stored on ESP32 flash. |
| **TC-04** | **Handshake** | ESP32 successfully joins the Phone/Nitro hotspot. |
| **TC-05** | **Burst Upload** | A 5MB CSV is uploaded to Nitro in < 15s with 100% data integrity. |
| **TC-06** | **Auto-Refresh** | Web UI automatically detects "Upload Done" and refreshes the session list. |

## 5. Dev Handover & Testing Guide
Once implemented, a `CONNECTIVITY_HANDOVER.md` will be generated with:
- Troubleshooting steps for macOS Privacy settings.
- Bluefy setup guide for iOS.
- Linux `btmon` logs for verifying the advertising packet structure.
