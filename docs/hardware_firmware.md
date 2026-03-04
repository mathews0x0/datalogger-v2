# 🏍️ RaceSense Hardware & Firmware (RS-Core)

This document details the physical data acquisition module (**RS-Core V2**) and the **MicroPython-based** firmware that powers it.

---

## 🛠️ Hardware Specification (V2)

The RaceSense V2 module is built on the **ESP32-S3** platform, designed for high-frequency telemetry and robust storage.

### **Core Components**
*   **MCU**: ESP32-S3-WROOM-1 (Dual-core, 240MHz).
*   **GNSS (GPS)**: Neo-M8N (Connected via UART on IO17/18). Target rate: **10Hz**.
*   **IMU (6-Axis)**: BMI323 (Connected via I2C on IO21/39). Accel + Gyro.
*   **Storage**: 
    *   **Primary**: MicroSD Card (FAT32, High-speed SPI on IO10-13).
    *   **Fallback**: Internal 16MB Flash (if SD is missing or unmounted).
*   **Battery**: ADC IO8 for voltage monitoring (VBAT-SENSE). supports 1S/2S LiPo.
*   **Indicators**: 
    *   16x LED Neopixel Matrix (Main status & lap feedback).
    *   **Blue Debug LED (GPIO 2)**:
        *   **Pairing Mode**: 3Hz blink (2s) + 1s OFF.
        *   **Connecting**: 2Hz continuous blink.
        *   **Connected**: Steady ON (Heartbeat active).
*   **Connectivity**: 
    *   Native USB-C (IO19/20) for flashing/debugging.
    *   2.4GHz WiFi with **Stealth Provisioning** (OS probe suppression for Success/204).

---

## 🧠 Firmware Architecture

The firmware is written in **MicroPython (v1.22+)** and utilizes both ESP32 cores to prevent telemetry gaps during network activity.

### **Dual-Core Task Split**
1.  **Core 0 (Telemetry Loop)**:
    *   10Hz target loop frequency.
    *   GPS updates & NMEA parsing (with `ntptime` synchronization).
    *   IMU sampling (Accel/Gyro).
    *   Track crossing detection (Lap/Sectors).
    *   Syncing to SD Card (Streaming write + `flush` every 1s).
2.  **Core 1 (Support Services)**:
    *   **IoT Background Thread**: Continuous loop (`uploader.py`) that sends a **Heartbeat Ping** every 15s to the cloud.
    *   **Asynchronous Uploader**: Automatically sweeps `data/session_logs/` and POSTs CSVs directly to `/api/upload` via `rsk_` bearer tokens.
    *   **Stealth Portal**: Captive portal logic that suppresses iOS/Android connectivity popups to maintain background pairing.

---

## 📊 Data Logging Logic

### **The State Machine (Main Loop)**
*   **SEARCHING**: GPS is looking for a lock.
*   **PAUSED**: Fixed position but velocity < 5km/h (Usually in the pits).
*   **LOGGING**: Speed > 10km/h and GPS fix is valid. Recording active.
*   **CALIBRATING**: Stationary and upright for >10s. Calibrates IMU offsets.
*   **STORAGE_CRITICAL**: Storage usage > 95%.

### **CSV Log Format**
Logs are saved in the `/sd/learning/` or `/data/learning/` directory.
Header: `time,lat,lon,alt,speed,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,vbat`
Timestamp format: Unix Epoch (synchronized via **NTP** on boot).

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
*   **IMU Orientation**: The BMI323 must be mounted flat. The auto-calibration routine (`CALIBRATING` state) expects the bike to be perfectly upright.
