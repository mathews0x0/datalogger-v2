# 🏍️ RaceSense Hardware & Firmware (RS-Core)

This document details the physical data acquisition module (**RS-Core V2**) and the **MicroPython-based** firmware that powers it.

---

## 🛠️ Hardware Specification (V2)

The RaceSense V2 module is built on the **ESP32-S3** platform, designed for high-frequency telemetry and robust storage.

### **Core Components**
*   **MCU**: ESP32-S3-WROOM-1-N16R8 (Dual-core, 240MHz, 16MB flash, 8MB Octal PSRAM).
*   **GNSS (GPS)**: Neo-M8N (Connected via UART on IO17/18). Target rate: **10Hz**.
*   **IMU (6-Axis)**: BMI323 (Connected via I2C on IO21/39). Accel + Gyro. Requires High Performance Mode (Power Mode 7) for reliable gyro output.
*   **Storage**: 
    *   **Primary**: MicroSD Card (FAT32, High-speed SPI on IO10-13).
    *   **Fallback**: Internal 16MB Flash. Sessions recorded here are **Auto-Copied** to SD on the next boot if a card is detected.
*   **Battery**: ADC **IO7** for voltage monitoring (VBAT-SENSE). Uses a 100k/100k resistor divider. Supports 1S/2S LiPo.
*   **User Input**:
    *   **Sync Button (IO5)**: GND-button-IO5 (active LOW, internal pull-up). Determines device mode at boot.
*   **Indicators**: 
    *   **Feedback NeoPixel (IO4)**: 16x LED matrix. Main status & lap feedback.
    *   **Onboard NeoPixel (IO6)**: 1x LED. Mirrors Feedback NeoPixel color at all times.
    *   **Blue Debug LED (GPIO 2)**: Legacy debug indicator.
*   **Validated Development Display**:
    *   **TFT**: Generic 2.8" 240x320 SPI TFT using **ILI9341** controller.
    *   **Touch**: Resistive touchscreen using **XPT2046** controller.
    *   **Validated dedicated SPI bus (temporary bring-up mapping)**:
        *   `TFT/T_CLK` on **IO15**
        *   `TFT/T_DIN` on **IO16**
        *   `TFT/T_OUT` on **IO9**
        *   `TFT_CS` on **IO5**
        *   `TFT_DC` on **IO6**
        *   `TOUCH_CS` on **IO7**
        *   temporary battery remap to **IO14**
    *   **Required panel ties**:
        *   `LED/BL` -> `3V3`
        *   `RST` -> `3V3` or `EN`
    *   This display path is currently used for boot / decision / sync / settings / calibration / first-time setup UX while the original button / onboard NeoPixel are temporarily repurposed.
    *   TFT typography uses generated MicroPython font assets under `firmware/lib/tft_fonts/` instead of scaled `framebuf.text()`.
    *   The boot logo is stored as a raw RGB565 asset at `/lib/tft_boot_logo.raw` and streamed directly to the ILI9341 window for faster startup.
*   **Connectivity**: 
    *   Native USB-C (IO19/20) for flashing/debugging.
    *   2.4GHz WiFi with **Stealth Provisioning** (OS probe suppression for Success/204). Only active in Sync Mode.

---

## 🧠 Firmware Architecture

The firmware is written in **MicroPython** and operates in one of two **exclusive modes**, selected by the hardware Sync Button (IO5) during a 10-second boot window.

### **MicroPython Build Requirement**
For this exact module, standardize on a vetted local copy of the **ESP32_GENERIC_S3 "spiram-oct"** variant and flash only from the repository.

Operationally, that means:
*   Preferred local filename: `firmware/esp32s3-micropython-psram-oct.bin`
*   Accepted local fallbacks: `firmware/esp32s3-micropython.bin`, `firmware/micropython.bin`
*   After flashing, the firmware should print a boot-time memory line with `PSRAM=yes`

### **Boot Sequence**
1.  5-second safe boot window (Ctrl-C to halt via mpremote).
2.  Hardware initialization (NeoPixels, SD, IMU, GPS, WDT).
3.  **Halt Opportunity**: 3 Blue Pulses confirm boot. (Ctrl-C via mpremote works here).
4.  **Auto-Copy Check**: If SD is mounted AND sessions exist on Flash:
    *   **White Flashing** LEDs.
    *   Files are moved to `/sd/sessions/` (with collision protection: `_1.csv`).
    *   Device reboots automatically after completion.
5.  **10-Second Decision Window**: Granular hardware status feedback:
    *   **Fast Green Blink**: (DECISION_ALL_OK) SD, IMU, and GPS are all OK.
    *   **Fast Red Blink**: (DECISION_IMU_SD_FAILED) IMU or SD (or both) have failed.
    *   **Solid Red**: (DECISION_GPS_FAIL) No NMEA detected. Device **holds** here indefinitely until GPS is recovered or SYNC button pressed.
    *   **Button pressed** during window → **SYNC MODE**.
    *   **TFT touch `SYNC`** during window → **SYNC MODE**.
    *   **TFT gear button** during window → Settings (`WIFI`, `CALIB`, `BACK`, Auto Log toggle).
    *   **TFT touch `LOG`** during window and GPS OK → **LOGGING MODE**.
    *   **Exit condition**: 10s passed AND GPS OK AND Auto Log enabled → **LOGGING MODE**.
    *   If Auto Log is disabled in `/data/metadata/device.json`, the rider must tap `LOG`.

### **LOGGING MODE (Default — No Radio)**
*   All WiFi radios are killed immediately.
*   **Core 0 runs exclusive 100Hz telemetry loop**: IMU every tick (100Hz), GPS every 10th tick (10Hz).
*   **Bounded double-buffer writes**: Rows are queued into an active memory buffer, swapped into a flush buffer around ~20 rows, and written out separately to reduce SD latency impact on the sampling path.
*   **Method-Driven UI Signaling**: Core 0 never touches NeoPixel hardware directly. It calls semantic methods (e.g., `led.play_logging()`) which set internal flags for the background worker.
*   **Track Engine** provides lap/sector crossing events which are overlaid via `led.trigger_event()`.
*   **Integrity markers**: The logger emits lightweight `M` rows (`LOG_OPEN`, periodic `CHECKPOINT`, `LOG_STOP`) so partial sessions are easier to recover and diagnose after resets or storage faults.
*   **Protective shutdown behavior**: Storage-critical conditions are latched. At a hard threshold the logger stops file growth deliberately instead of continuing blindly into full-disk failure.
*   **Runtime diagnostics**: The firmware tracks queue depth, dropped rows, heap low watermark, loop overruns, GPS parser health, LED thread health, and battery voltage for post-mortem diagnosis.
*   No uploader, no captive portal, no WiFi threads.

### **SYNC MODE (Button Press — No Logging)**
*   No telemetry logging occurs. No CSV files are created.
*   **Sequential Sequence**: Device searches for known WiFi, then performs a **Heartbeat First** handshake to verify cloud health.
*   **Single-Writer Worker (Core 1)**: All NeoPixel timing and writes are handled by a dedicated background thread.
*   **Zero-Allocation Pipeline**: The system uses `color_animations.py` as a theme engine with pre-allocated GRB buffers. The `LEDManager` writes directly to the hardware buffer (`buf[:] = LOOKUP`) to prevent heap fragmentation during Wi-Fi/SSL operations.
*   **High-Speed Batch Uploads**: Session uploads stream adaptive reads into large `512KB` HTTP POST payloads over persistent SSL connections. On PSRAM-backed builds the read ceiling is raised to `16KB`, giving more upload headroom without returning to the older fragmentation failures seen on small-heap builds.
*   **Resumable Upload Safety**: If horizontal scaling or network instability drops a request mid-batch, the device queries the server and seamlessly resumes the upload from the exact byte offset (`X-Upload-Offset`) instead of restarting the whole file.
*   **Recovered handshake path**: If the initial cloud handshake fails, later heartbeat recovery can still trigger uploads in the same sync session.
*   **Power-aware sync**: Under weak battery voltage, LED brightness and WiFi TX power are reduced. At critical battery voltage the uploader may be deferred to avoid brownouts.
*   **Global Brightness**: A master `self.brightness` setting (0.0-1.0) is now applied to actual LED output, not just animation choice.
*   **Deferred Pairing Transition**: Long press (>3s) requests Pairing Mode, but the firmware now waits for active network work to quiesce before switching into AP + Captive Portal.
*   Device stays in Sync Mode indefinitely (no automatic reboot).
*   **Temporary TFT UX path**:
    *   clean RaceSense boot logo, with no diagnostic copy on the TFT boot screen
    *   simplified decision screen showing GPS / IMU / SD status icons plus active track name
    *   sync decision `SYNC` / gear / `LOG` touch targets
    *   settings screen with `WIFI`, `CALIB`, `BACK`, and Auto Log ON/OFF
    *   pairing and WiFi screens showing saved SSID or setup AP name where applicable
    *   WiFi search animation with SSID at the bottom
    *   heartbeat screen shown as rider-facing red/green heart status
    *   queue, single-screen upload, result, idle, and logging summary screens
    *   upload screen shows one overall progress bar, large percentage, ETA with h/m/s units, current file, file index, and chunk count
    *   per-file archive messages are suppressed on TFT; archive remains background behavior
    *   logging screens avoid showing session filenames; technical logs stay on serial output
    *   boot and decision screens deliberately avoid battery/RAM/log noise
*   **Touch calibration**:
    *   Runs once if `/data/metadata/touch.json` is missing.
    *   Can be rerun from Settings -> `CALIB`.
    *   Uses five points: top-left, top-right, bottom-right, bottom-left, center.
    *   Calibration is per-device and should be preserved with other metadata.

---

## 📊 Data Logging Logic

### **The State Machine (Logging Mode Only)**
*   **SEARCHING**: GPS is looking for a lock.
*   **LOGGING**: GPS fix valid and recording active.
*   **STORAGE_CRITICAL**: Storage usage > 90% and warning is latched.
*   **HARD_STOP**: Logging growth is stopped near full storage (~98%) to preserve filesystem integrity and diagnostics headroom.

### **LED Feedback (Method-Driven)**

The `LEDManager` uses semantic methods. Direct state strings are no longer used for control.

| Event / State | Method | Animation | Color |
|---------------|--------|-----------|-------|
| Boot | 3 pulses | Blue |
| Decision: ALL OK | Fast blink | Green (SD+IMU+GPS ok) |
| Decision: HW FAIL | Fast blink | Red (SD/IMU failed, GPS ok) |
| Decision: GPS FAIL| Solid | Red (GPS module/comms failure) |
| **AUTO_COPY** | **Fast blink (5Hz)** | **White (until reboot)** |
| SEARCHING | Slow pulse | Yellow (Warm Amber) |
| LOGGING (Casual) | Solid | Green |
| **LOGGING (Racing)**| **OFF** | **None (Stealth)** |
| **TRACK_FOUND** | **Fast blink (10Hz)** | **White (3s duration)** |
| **SECTOR_FAST** | **Fast blink** | **Green (3s duration)** |
| **SECTOR_NEUTRAL**| **Fast blink** | **Orange (3s duration)** |
| **SECTOR_SLOW** | **Fast blink** | **Red (3s duration)** |
| Sync: Searching WiFi | Slow fade | Purple |
| Sync: WiFi Found | Fast blink | Purple |
| Sync: Uploading | **Max Speed Flash** | **Green (25Hz)** |
| Sync: Upload OK | Slow fade | Green |
| Sync: Upload Failed | Slow fade | Red |
| Sync: Low Battery | Reduced brightness + reduced TX power | Existing sync state colors, dimmed |
| Pairing Mode | Breathing fade | Blue |
| **SETUP_NEEDED** | **Balanced Rainbow**| **Complex Blends (no primary RGB)** |

### **Temporary TFT Bring-Up Notes**

The current validated display/touch bring-up on PSRAM firmware deliberately repurposes three original RS-Core pins:

- `IO5`: used as `TFT_CS` instead of hardware sync button
- `IO6`: used as `TFT_DC` instead of onboard NeoPixel
- `IO7`: used as `TOUCH_CS` instead of the original battery ADC net

To preserve battery monitoring during this phase, the firmware currently remaps battery sensing to `IO14`.

This is a development-time wiring compromise, not the final production pinout.

### **CSV Log Format (Dual-Rate V2)**
Logs are saved in the `/sd/learning/` or `/data/learning/` directory.
Header: `tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat`

| Row Type | Rate | Fields Populated |
|----------|------|-----------------|
| `I` (IMU) | 100 Hz | `tick_ms`, accel, gyro |
| `G` (GPS) | 10 Hz | `tick_ms`, accel, gyro, lat, lon, alt, speed, sats, vbat |
| `M` (Marker) | Sparse / event-driven | session integrity + operational marker data |

**`tick_ms`**: ESP32 monotonic clock (milliseconds). Used as the master timestamp for sensor fusion alignment.
**`vbat`**: Battery voltage (Volts). Calibrated via `read_uv()` with a 2.0x software multiplier for the 100k/100k divider.
**Write queueing**: ~20 rows accumulated before a buffer swap and SD write+flush.
**Queue protection**: The logger tracks queue overflow and dropped-row counts so SD bottlenecks can be measured.
**Checkpointing**: Marker rows provide recovery breadcrumbs when a file is interrupted before clean completion.

---

## ⚡ Flashing & Updates

### **1. Manual Flashing (via Tool)**
In the `firmware/` directory, use the supplied shell script:
```bash
./flashtool.sh --port /dev/cu.usbmodem* --firmware micropython.bin
```
**Download Mode**: Hold **BOOT**, press **RESET**, release **BOOT**.

For the `ESP32-S3-WROOM-1-N16R8`, the repository flashing flow prefers `esp32s3-micropython-psram-oct.bin` and only uses local firmware files already present in `firmware/`.

### **2. Script Deployment**
To update just the Python logic (`main.py`, `lib/`, etc.):
```bash
./deploy.sh --sync
```

### **3. Web OTA (Over-The-Air)**
The production server can push updates to local devices via the **UpdateManager**.
*   Server holds the latest `micropython.bin` in the `firmware/` root.
*   Device pulls the update over WiFi when triggered from the **Settings -> Update** menu in the web app.
*   Backend hosting is now a self-managed public VPS behind DNS + Nginx; this infrastructure change does **not** change the device-side sync or OTA protocol, but it makes cloud endpoint management explicit in operations.

### **4. PSRAM Validation**
After flashing, validate the memory layout before trusting the build in the field:

```bash
cd firmware
./flashtool.sh
```

Choose `Run PSRAM Probe`.

Pass criteria:
*   Boot log shows `[Memory] Boot: ... PSRAM=yes`
*   `tools/psram_probe.py` reports `PSRAM inference: DETECTED`
*   Large contiguous `bytearray` allocations succeed into the multi-megabyte range

---

## ⚠️ Hardware Precautions
*   **GPS Antenna**: Ensure a clear sky view. The Neo-M8N performance degrades significantly under carbon fiber or metal.
*   **SD Card**: Always use **Class 10** or faster cards. Slow cards can cause Core 0 to hang during long sessions.
*   **IMU Orientation**: The BMI323 must be mounted flat. The auto-calibration routine (`CALIBRATING` state) expects the bike to be perfectly upright. Note that BMI323 uses word-based I2C communication and a different register map (0x20/0x21 for conf) compared to the legacy BMI270.
