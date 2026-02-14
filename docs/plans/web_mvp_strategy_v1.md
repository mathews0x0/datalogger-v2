# Racesense Web MVP Strategy (v1.0)
**Status:** Strategic Shift (Zero-Install Priority)
**Date:** 2026-02-14

## 1. The "Reverse Hotspot" Sync
Since browsers cannot programmatically switch WiFi networks, we will flip the connection logic.

### Workflow:
1. **User Action:** User opens the Racesense Web UI (Chrome on Android or Bluefy on iOS).
2. **Handshake:** User taps "Sync". Browser initiates a Web-BLE connection to the RS-Core.
3. **Provisioning:** Browser sends the **Phone's Hotspot Credentials** (stored in `localStorage`) to the ESP32 via BLE.
4. **Handoff:** The ESP32 attempts to connect to the Phone's Hotspot.
5. **Data Burst:** Once connected, the ESP32 HTTP POSTs raw CSVs directly to the Nitro 5 backend.
6. **Confirmation:** ESP32 notifies the browser via BLE when the upload is complete.

## 2. Firmware (RS-Core) Updates
- **STA Mode Priority:** Firmware must be updated to prioritize Station Mode (connecting to hotspot) during a sync event.
- **Upload Client:** Implement a robust `HttpClient` on the ESP32 to handle multipart/form-data uploads.
- **Retry Logic:** If the hotspot isn't found within 15 seconds, revert to BLE and notify the user.

## 3. Frontend (Web UI) Refinement
- **Zero-Install Compatibility:** Ensure all BLE code uses the standard `navigator.bluetooth` API.
- **Hotspot Modal:** A dedicated UI flow that says: *"Handshake successful. Please enable your hotspot [SSID: Racesense-Pit] now to start the high-speed transfer."*
- **Responsive Audit:** Ensure the 'Pit Lane' and 'Session Details' views use the new glassmorphism design system effectively on mobile viewports.

## 4. Backend (Nitro 5)
- **Direct Upload API:** Ensure `/api/upload` is hardened for direct ESP32 uploads (which may have different headers than browser-based uploads).
- **Session Auto-Processing:** As soon as an upload finishes, the backend must trigger the analysis pipeline so the results are ready when the user refreshes.

## 5. Next Steps
1. Update `firmware/ble_provisioning.py` to handle STA credentials.
2. Implement the `SyncModal.js` component in the Web UI.
3. Field test the "Reverse Hotspot" latency.
