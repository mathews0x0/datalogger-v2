# 🏍️ RaceSense Hardware & Firmware (RS-Core)

This document details the physical data acquisition module (**RS-Core V2**) and the **MicroPython-based** firmware that powers it.

---

## 🛠️ Hardware Specification (V2)

The RaceSense V2 module is built on the **ESP32-S3** platform, designed for high-frequency telemetry and robust storage.

### **Core Components**
*   **MCU**: ESP32-S3-WROOM-1 (Dual-core, 240MHz).
*   **GNSS (GPS)**: Neo-M8N (Connected via UART on IO17/18). Target rate: **10Hz**.
*   **IMU (6-Axis)**: BMI270 (Connected via I2C on IO21/39). Accel + Gyro.
*   **Storage**: 
    *   **Primary**: MicroSD Card (FAT32, High-speed SPI on IO10-13).
    *   **Fallback**: Internal 16MB Flash (if SD is missing or unmounted).
*   **Battery**: ADC IO8 for voltage monitoring (VBAT-SENSE). Supports 1S/2S LiPo.
*   **User Input**:
    *   **Sync Button (IO5)**: GND-button-IO5 (active LOW, internal pull-up). Determines device mode at boot.
*   **Indicators**: 
    *   **Feedback NeoPixel (IO4)**: 16x LED matrix. Main status & lap feedback.
    *   **Onboard NeoPixel (IO6)**: 1x LED. Mirrors Feedback NeoPixel color at all times.
    *   **Blue Debug LED (GPIO 2)**: Legacy debug indicator.
*   **Connectivity**: 
    *   Native USB-C (IO19/20) for flashing/debugging.
    *   2.4GHz WiFi with **Stealth Provisioning** (OS probe suppression for Success/204). Only active in Sync Mode.

---

## 🧠 Firmware Architecture

The firmware is written in **MicroPython (v1.22+)** and operates in one of two **exclusive modes**, selected by the hardware Sync Button (IO5) during a 10-second boot window.

### **Boot Sequence**
1.  5-second safe boot window (Ctrl-C to halt via mpremote).
2.  Hardware initialization (NeoPixels, SD, IMU, GPS, WDT).
3.  **3 Blue Pulses** on both NeoPixels to confirm device is alive.
4.  **10-Second Decision Window**: NeoPixels blink fast in **Green** (SD mounted) or **Red** (SD failed).
    *   **Button pressed** during window → **SYNC MODE**.
    *   **No press** → **LOGGING MODE**.

### **LOGGING MODE (Default — No Radio)**
*   All WiFi radios are killed immediately.
*   **Core 0 runs exclusive 100Hz telemetry loop**: IMU every tick (100Hz), GPS every 10th tick (10Hz).
*   **Buffered writes**: Rows are batched in memory (~20 rows) and flushed to SD card ~5 times/sec for efficiency.
*   **Method-Driven UI Signaling**: Core 0 never touches NeoPixel hardware directly. It calls semantic methods (e.g., `led.play_logging()`) which set internal flags for the background worker.
*   **Track Engine** provides lap/sector crossing events which are overlaid via `led.trigger_event()`.
*   No uploader, no captive portal, no WiFi threads.

### **SYNC MODE (Button Press — No Logging)**
*   No telemetry logging occurs. No CSV files are created.
*   **Sequential Sequence**: Device searches for known WiFi, then performs a **Heartbeat First** handshake to verify cloud health.
*   **Single-Writer Worker (Core 1)**: All NeoPixel timing and writes are handled by a dedicated background thread. This prevents SSL handshake jitter from affecting animation fluidness.
*   **Global Brightness**: A master `self.brightness` setting (0.0-1.0) is applied to all animations, ensuring consistent intensity.
*   **Long press (>3s)** on Sync Button at any time in Sync Mode → enters **Pairing Mode** (AP + Captive Portal).
*   Device stays in Sync Mode indefinitely (no automatic reboot).

---

## 📊 Data Logging Logic

### **The State Machine (Logging Mode Only)**
*   **SEARCHING**: GPS is looking for a lock.
*   **PAUSED**: GPS fix valid but inside mapped Pit Area.
*   **LOGGING**: GPS fix valid and outside Pit Area. Recording active.
*   **CALIBRATING**: Stationary and upright for >10s in pit. Calibrates IMU offsets.
*   **STORAGE_CRITICAL**: Storage usage > 95%.

### **LED Feedback (Method-Driven)**

The `LEDManager` uses semantic methods. Direct state strings are no longer used for control.

| Event / State | Method | Animation | Color |
|---------------|--------|-----------|-------|
| Boot | 3 pulses | Blue |
| Decision Window | Fast blink | Green (SD ok) / Red (no SD) |
| SEARCHING | Slow pulse | Yellow |
| LOGGING (Casual) | Solid | Green |
| **LOGGING (Racing)**| **OFF** | **None (Stealth)** |
| PAUSED | Slow pulse | Amber |
| CALIBRATING | Fast pulse | Blue |
| **TRACK_FOUND** | **Fast blink (10Hz)** | **White (2.5s duration)** |
| **SECTOR_FAST** | **Fast blink** | **Green (2.5s duration)** |
| **SECTOR_NEUTRAL**| **Fast blink** | **Orange (2.5s duration)** |
| **SECTOR_SLOW** | **Fast blink** | **Red (2.5s duration)** |
| Sync: Searching WiFi | Slow fade | Purple |
| Sync: WiFi Found | Fast blink | Purple |
| Sync: Uploading | Fast blink | Green |
| Sync: Upload OK | Slow fade | Green |
| Sync: Upload Failed | Slow fade | Red |
| Pairing Mode | Breathing fade | Blue |

### **CSV Log Format (Dual-Rate V2)**
Logs are saved in the `/sd/learning/` or `/data/learning/` directory.
Header: `tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat`

| Row Type | Rate | Fields Populated |
|----------|------|-----------------|
| `I` (IMU) | 100 Hz | `tick_ms`, accel, gyro |
| `G` (GPS) | 10 Hz | `tick_ms`, accel, gyro, lat, lon, alt, speed, sats, vbat |

**`tick_ms`**: ESP32 monotonic clock (milliseconds). Used as the master timestamp for sensor fusion alignment.
**Buffered writes**: ~20 rows accumulated before single SD write+flush (~200ms max data loss on power failure).

---

## ⚡ Flashing & Updates

### **1. Manual Flashing (via Tool)**
In the `firmware/` directory, use the supplied shell script:
```bash
./flashtool.sh --port /dev/cu.usbmodem* --firmware micropython.bin
```
**Download Mode**: Hold **BOOT**, press **RESET**, release **BOOT**.

### **2. Script Deployment**
To update just the Python logic (`main.py`, `lib/`, etc.):
```bash
./deploy.sh --sync
```

### **3. Web OTA (Over-The-Air)**
The production server can push updates to local devices via the **UpdateManager**.
*   Server holds the latest `micropython.bin` in the `firmware/` root.
*   Device pulls the update over WiFi when triggered from the **Settings -> Update** menu in the web app.

---

## ⚠️ Hardware Precautions
*   **GPS Antenna**: Ensure a clear sky view. The Neo-M8N performance degrades significantly under carbon fiber or metal.
*   **SD Card**: Always use **Class 10** or faster cards. Slow cards can cause Core 0 to hang during long sessions.
*   **IMU Orientation**: The BMI270 must be mounted flat. The auto-calibration routine (`CALIBRATING` state) expects the bike to be perfectly upright.
