# Racesense Connectivity Handover & Testing Guide
**Status:** Implementation Complete (v1.1)
**Date:** 2026-02-14

## 1. Overview
We have implemented a **"Reverse Hotspot"** synchronization model to support a 100% Web UI (Zero-Install) experience. This bypasses the browser's inability to switch WiFi networks by making the ESP32 (RS-Core) join the phone's hotspot.

## 2. Platform Specifics (Rider Guide)

### macOS (MacBook Air/Pro)
- **Problem:** Device not appearing in Chrome.
- **Solution:** 
    1. Go to **System Settings > Privacy & Security > Bluetooth**.
    2. Ensure **Google Chrome** is enabled.
    3. Use the Chrome browser. Safari does NOT support Web Bluetooth.
- **Dev Note:** We now use explicit Service UUID filtering (`12345678...`) which improves visibility on macOS.

### iOS (iPhone)
- **Problem:** Safari/Chrome on iOS blocks Web Bluetooth.
- **Solution:** 
    1. Download the **Bluefy Browser** (free) from the App Store.
    2. Open your Racesense Web UI URL inside Bluefy.
- **Handshake:** Bluefy supports the standard `navigator.bluetooth` API.

### Android / Windows
- **Status:** Works out-of-the-box in Google Chrome.

## 3. The Sync Workflow
1. **Connect:** Web UI initiates BLE pairing with `Racesense-Core`.
2. **Provision:** Web UI sends phone hotspot SSID/Pass + Nitro 5 API URL over BLE.
3. **Hotspot:** User toggles "Personal Hotspot" on phone.
4. **Upload:** ESP32 joins hotspot and POSTs CSVs to `/api/upload`.
5. **Auto-Process:** Nitro 5 backend triggers `run_analysis.py` immediately upon receipt.

## 4. Technical Reference (BLE)
- **Service UUID:** `12345678-1234-5678-1234-567812345678`
- **Status Char (Notify):** `...5002` (JSON: `{"connected": true, "sync_progress": 45}`)
- **Configure Char (Write):** `...5003` (JSON: `{"ssid": "...", "password": "...", "api_url": "..."}`)

## 5. Verification Steps (Nitro Linux)
To verify the ESP32 is advertising correctly from the command line:
```bash
# Scan for Racesense-Core
sudo hcitool lescan

# Verify Service UUID advertising (requires bluez)
btmon | grep "12345678"
```

## 6. Known Limitations
- **Hotspot Frequency:** On some iPhones, the hotspot may "hide" if no devices connect quickly. The user should stay on the Hotspot settings page during the handshake.
- **Upload Speed:** Limited by the phone's signal strength and ESP32 WiFi stack (~2MB/s max).
