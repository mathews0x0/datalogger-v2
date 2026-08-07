# 🏍️ RaceSense Hardware & Firmware (RS-Core)

This document details the physical data acquisition hardware (**RS-Core V4.2 / V2 & ESP32-P4**) and the **Native C/C++ ESP-IDF 5.x Firmware** (currently validated with ESP-IDF v5.5.5) that powers it.

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
*   **Power Architecture (V4.2)**:
    *   New board revision **RS-Core V4.2** adds a **single-switch soft-power path** using one momentary push button for both power-on and power-off intent.
    *   The same physical button momentarily powers the ESP32 through the regulator enable path on press.
    *   **IO41** is reserved as `PWR_HOLD` and is asserted early in boot so the ESP32 can keep itself powered after the button is released.
    *   A sensed copy of the same button is routed to **IO8** through a protected diode + divider network so the firmware can detect a deliberate long press without back-driving the power path.
    *   Functional split:
        *   `IO41` owns power sustain
        *   `IO8` only senses button intent
    *   This gives the board a single-user-control power model:
        *   short press to turn on
        *   firmware hold to stay on
        *   long press to request clean shutdown
*   **Indicators**: 
    *   **Feedback NeoPixel (IO4)**: 16x LED matrix. Main status & lap feedback.
    *   **Onboard NeoPixel (IO6)**: 1x LED. Mirrors Feedback NeoPixel color at all times.
    *   **Blue Debug LED (GPIO 2)**: Legacy debug indicator.
    *   **Validated Development Display**:
    *   **TFT**: Generic 2.8" 240x320 SPI TFT using **ILI9341** controller.
    *   **Touch**: Resistive touchscreen using **XPT2046** controller.
    *   **Validated dedicated SPI bus**:
        *   `TFT/T_CLK` on **IO15**
        *   `TFT/T_DIN` on **IO16**
        *   `TFT/T_OUT` on **IO9**
        *   `TFT_CS` on **IO5**
        *   `TFT_DC` on **IO6**
        *   `TOUCH_CS` on **IO7**
        *   `TFT_RST` on **IO42**
        *   `TOUCH_IRQ` on **IO38**
        *   temporary battery remap to **IO14**
    *   **Required panel ties**:
        *   `LED/BL` -> `3V3`
        *   panel reset is now driven from **IO42**, not tied high
    *   This display path is currently used for boot / Home / sync / settings / calibration / first-time setup UX while the original button / onboard NeoPixel are temporarily repurposed.
    *   The native UI uses LVGL typography and the same full RaceSense logo asset as the server landing page (`server/ui/assets/RS full logo.png`), converted to an embedded RGB565 panel image.
    *   The active firmware baseline is now **TFT-only**; the older OLED status path has been removed from the current runtime.
*   **Connectivity**: 
    *   Native USB-C (IO19/20) for flashing/debugging.
    *   2.4GHz WiFi with **Stealth Provisioning** (OS probe suppression for Success/204). Only active in Sync Mode.

---

## 🧠 Firmware Architecture (Native C/C++ ESP-IDF 5.x)

The RaceSense firmware is implemented as **native C/C++ under ESP-IDF 5.x with
FreeRTOS SMP**. The unified project provides target-aware support across the
Waveshare P4 and compact custom-board hardware profiles.

### **Dual-Target Hardware Abstraction (`bsp.h` / `bsp_display_target.h`)**
The codebase compiled under `firmware/` operates as a unified target-agnostic repository:
*   **ESP32-S3 (`idf.py set-target esp32s3`)**: Target 2 configuration for RS-Core V4.2 PCB. Automatically routes I2C0 to IO21/39, UART1 to IO17/18, Battery ADC to IO7 (CH6, 100k/100k divider @ 2.0x scale), and configures the 2.8" SPI ILI9341 (320x240) + XPT2046 resistive touch controller on dedicated SPI pins. Supports soft-power self-hold latch on **IO41** (`PWR_HOLD`) and button intent sense on **IO8** (`PWR_SENSE`).
*   **ESP32-P4 (`idf.py set-target esp32p4`)**: Target 0 configuration for the Waveshare 4.3" development board. It routes GT911 touch on I²C0 IO7/8, the external BMI323 on I²C1 IO21/22, Neo-M8N UART1 on IO3/4, and battery ADC to IO20 / ADC1 channel 4 with the schematic's 200 kΩ/100 kΩ divider (3.0× scale). SDMMC uses slot 0 on IO39–44, the active-low IO45 card switch, and the P4 LDO_VO4 I/O supply. The card currently mounts through the verified 1-bit/20 MHz fallback because the fitted board/card path fails its 4-bit SSR transfer. Display output is the 4.3" MIPI-DSI ST7701 at 800×480 landscape with GT911 capacitive touch.

### **P4 Live Hardware Validation (2026-08-04)**

The supplied P4 assembly has passed simultaneous bench validation for the
current peripheral baseline:

*   **Display/touch:** correct 800×480 landscape rendering and accurate,
    persistent GT911 calibration.
*   **IMU:** BMI323 chip ID `0x43`; live accelerometer and gyro channels both
    produce the expected motion/lean response.
*   **GPS:** Neo-M8N obtains a clean satellite lock with approximately 10 Hz
    configured and measured output.
*   **Storage:** the nominal 8 GB SDHC card mounts, reports 7.49 GiB total and
    approximately 7.42 GiB free, and passes create/write/readback/remove. A
    verified 4 MiB test measured 0.65 MiB/s write and 0.73 MiB/s read.

This is a peripheral bring-up milestone, not a production-release declaration.
ESP32-C6 Wi-Fi transport, the sensor-to-storage queue bridge, complete CSV
session validation, recovery testing, and soak testing remain open.

### **Unified RaceSense Mark Identity**

Server and device firmware use one monotonically increasing RaceSense **Mark**
identity, referencing Tony Stark's successive Iron Man suits. It is neither a
semantic version nor a generic build label. The authoritative numeric source
is `server/VERSION`; the current release identity is **Mark 199**.

The server reads this value for its health response, admin display, local
firmware comparison, and minimum-compatible Mark release. The P4 CMake
configuration reads the same file and embeds `Mark N` in the standard ESP-IDF
application descriptor. Firmware also prints the Mark identity during boot.
Configuration fails if the shared number is absent or non-numeric, preventing
an unrelated Git hash or hardcoded placeholder from silently becoming the
device identity.

The tracked `.githooks/pre-commit` hook advances the number once per commit. An
explicitly selected jump is preserved, which is how the sequence moves from
Mark 180 to Mark 199 without being incremented again by that commit.

Mark identity and Git revision serve different purposes: Mark 199 identifies
the coordinated RaceSense release, while the Git SHA remains useful engineering
traceability.

### **Core Allocation & Deterministic Sampling (Core 0 vs Core 1)**
*   **Core 0 (Hard Real-Time Telemetry)**: Dedicated to high-frequency sensor acquisition via `sensors.c`. The FreeRTOS timer/task loop is configured for a **100 Hz** BMI323 target and **10 Hz** Neo-M8N processing. GPS cadence has been measured at approximately 10 Hz on the P4; exact 100 Hz IMU cadence and worst-case jitter under simultaneous display, SD, and future Wi-Fi load remain validation items.
*   **Core 1 (Application, UI & Storage Flush)**: Houses the top-level application state machine (`main.c`), the SDMMC storage flush task (`storage.c`), networking, and the LVGL UI. The sensor-owned queue is consumed by the storage flush task through an explicit drain barrier; live CSV-session validation remains open, and P4 networking still selects `network_stub.c`.

### **Firmware Status**
All supported boards use the native ESP-IDF project in `firmware/`; choose the
board-specific ESP-IDF target with `idf.py set-target`.

### **Boot Sequence**
1.  **Power-hold assertion**: native startup drives **IO41** so the soft-latched V4.2 board stays on after the momentary power button is released.
2.  The native application initializes the selected BSP, persistent storage, SD, IMU, GPS, watchdog, display, and touch controller.
3.  The application restores display/touch calibration and renders the RaceSense splash before entering Home.
6.  **Home / 10-Second Auto Log Window**: Granular hardware status feedback:
    *   **Fast Green Blink**: (DECISION_ALL_OK) SD, IMU, and GPS are all OK.
    *   **Fast Red Blink**: (DECISION_IMU_SD_FAILED) IMU or SD (or both) have failed.
    *   **Solid Red**: (DECISION_GPS_FAIL) No NMEA detected. Device **holds** here indefinitely until GPS is recovered or SYNC button pressed.
    *   **Button pressed** during Home → **SYNC MODE**.
    *   **TFT touch `SYNC`** during Home → **SYNC MODE**.
    *   **TFT gear button** during Home → Settings (`WIFI`, `TRACK`, `CALIB`, `BACK`, Auto Log toggle).
    *   **Mount profile flow**: Settings now also exposes mount-profile selection / recalibration for `tank`, `tail`, `stem`, and `generic`.
    *   **TFT touch `LOG`** during Home and GPS OK → **LOGGING MODE**.
    *   **Exit condition**: 10s passed AND GPS OK AND Auto Log enabled → **LOGGING MODE**.
    *   If Auto Log is disabled in `/data/metadata/device.json`, the rider must tap `LOG`.

### **LOGGING MODE (Default — No Radio)**
*   All WiFi radios are killed immediately.
*   **Core 0 runs exclusive 100Hz telemetry loop**: IMU every tick (100Hz), GPS every 10th tick (10Hz).
*   **Field validation note (May 2026)**: Reviewed track logs did not consistently meet this target. Effective IMU cadence was closer to roughly 53-58Hz, and GPS cadence varied from roughly 4Hz to 7.3Hz in the inspected sessions. Treat the 100Hz/10Hz values above as the intended firmware contract until the logger timing path is revalidated on-device.
*   **BMI323 gyro scale watch item**: May 2026 field logs showed a likely gyro scale/config mismatch of approximately 16x. Replay tooling can repair this signature for analysis, but firmware should emit correctly scaled gyro values so downstream estimators do not depend on heuristic repair.
*   **Bounded double-buffer writes**: Rows are queued into an active memory buffer, swapped into a flush buffer around ~20 rows, and written out separately to reduce SD latency impact on the sampling path.
*   **Method-Driven UI Signaling**: Core 0 never touches NeoPixel hardware directly. It calls semantic methods (e.g., `led.play_logging()`) which set internal flags for the background worker.
*   **Track Engine** provides lap/sector crossing events which are overlaid via `led.trigger_event()`.
*   **Integrity markers**: The logger emits lightweight `M` rows (`LOG_OPEN`, periodic `CHECKPOINT`, `LOG_STOP`) so partial sessions are easier to recover and diagnose after resets or storage faults.
*   **Protective shutdown behavior**: Storage-critical conditions are latched. At a hard threshold the logger stops file growth deliberately instead of continuing blindly into full-disk failure.
*   **Soft-power hold**: The firmware reasserts `IO41` during native startup so normal runtime code preserves the V4.2 power latch after early boot.
*   **Single-switch shutdown path**: The firmware monitors **IO8** as the protected power-button sense input. If the same power button is held for roughly 3 seconds, the logger can display `SHUTDOWN`, flush storage, and release `IO41` for a controlled power-off.
*   **Single-switch user model**: There is no separate external power-off control in V4.2. The rider-facing contract is one short press to power on and one deliberate long press to power off safely.
*   **Display baseline**: Boot, Home, Sync, Settings, calibration, and logging UI are all routed through the TFT stack. There is no active OLED runtime path in the current firmware baseline.
*   **Persistent IMU profile baseline**: The device now expects a saved mount calibration profile when high-confidence arbitrary mounting is required.
*   **Logging start validation**: The first ~5 seconds of logging show an IMU validation screen instead of the normal live logging screen.
    *   Left side (`TOP VIEW`) shows the saved calibrated mount yaw relative to bike forward.
    *   Right side (`MOUNT ANGLE`) shows static `FRONT` (roll/cant) and `SIDE` (pitch/nose-up) indicators from the saved mount geometry.
    *   This screen validates mount interpretation, not dynamic lean.
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
*   **Single-switch shutdown support**: The same power button is intended to be honored globally, not just on Home. Long-press shutdown should work during rider-facing TFT screens and non-logging sync flows as well.
*   **Global Brightness**: A master `self.brightness` setting (0.0-1.0) is now applied to actual LED output, not just animation choice.
*   **Deferred Pairing Transition**: Long press (>3s) requests Pairing Mode, but the firmware now waits for active network work to quiesce before switching into AP + Captive Portal.
*   Device stays in Sync Mode indefinitely (no automatic reboot).
*   **Temporary TFT UX path**:
    *   clean RaceSense boot wordmark, with no diagnostic copy on the TFT boot screen
    *   Home landing page showing GPS / IMU / SD status icons plus active track name
    *   Home `SYNC` / gear / `LOG` touch targets
    *   settings screen with `WIFI`, `CALIB`, `BACK`, and Auto Log ON/OFF
    *   mount-profile screen for `tank`, `tail`, `stem`, and `generic`
    *   pairing and WiFi screens showing saved SSID or setup AP name where applicable
    *   WiFi search animation with SSID at the bottom and `EXIT` back to Home
    *   heartbeat screen shows a continuous red pulse while `/api/device/ping` is in flight, then switches to a green pulse for at least two beats only after the server acknowledges with `success: true`
    *   queue, single-screen upload, result, idle, and logging summary screens
    *   upload screen shows one overall progress bar, large percentage, ETA with h/m/s units, current file, file index, and chunk count
    *   per-file archive messages are suppressed on TFT; archive remains background behavior
    *   logging screens avoid showing session filenames; technical logs stay on serial output
    *   first-5-seconds IMU validation view with top-view mount direction plus static front/side mount-angle indicators
    *   boot and Home screens deliberately avoid verbose diagnostic/log noise
    *   Home/settings touch paths are optimized for no-IRQ wiring with 110 ms debounce, touch-before-redraw ordering, and state-based redraw skipping
    *   cached top bar and partial content redraws are used to reduce visible screen-turn latency
*   **Touch calibration**:
    *   Runs on the second boot after a TFT preset has been selected, if `/data/metadata/touch.json` is missing.
    *   Can be rerun from Settings -> `CALIB`.
    *   Uses five points: top-left, top-right, bottom-right, bottom-left, center.
    *   Calibration is per-device and should be preserved with other metadata.
    *   Display preset selection is also per-device and is stored in `/data/metadata/display.json`.
    *   Touch and calibration are initialized by the selected native BSP target; there is no partial firmware-sync state to repair.
*   **IMU mount profile calibration**:
    *   Stored under device metadata and intended to persist across normal firmware sync.
    *   Current flow captures `STATIC`, `ENGINE`, `LEAN LEFT`, `LEAN RIGHT`, and `PUSH`.
    *   Produces a saved `rotation_matrix`, `gyro_bias`, `gravity_vector`, vibration metrics, and mount-angle summary.
    *   Profiles are selected once at the device level and then reused for logging until changed or recalibrated.

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
- `IO42`: dedicated `TFT_RST`
- `IO38`: dedicated `TOUCH_IRQ`

To preserve battery monitoring during this phase, the firmware currently remaps battery sensing to `IO14`.

This is a development-time wiring compromise, not the final production pinout.

### **CSV Log Format (Dual-Rate V2)**
Logs are saved in the `/sd/learning/` or `/data/learning/` directory.
Header: `tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat`

| Row Type | Rate | Fields Populated |
|----------|------|-----------------|
| `I` (IMU) | 100 Hz | `tick_ms`, accel, gyro |
| `G` (GPS) | 10 Hz | `tick_ms`, accel, gyro, lat, lon, alt, speed, sats, vbat |
| `M` (Marker) | Sparse / event-driven | session integrity + operational marker data, including IMU profile / validation metadata |

**`tick_ms`**: ESP32 monotonic clock (milliseconds). Used as the master timestamp for sensor fusion alignment.
**`vbat`**: Battery voltage (Volts). Calibrated via `read_uv()` with a 2.0x software multiplier for the 100k/100k divider.
**Write queueing**: ~20 rows accumulated before a buffer swap and SD write+flush.
**Queue protection**: The logger tracks queue overflow and dropped-row counts so SD bottlenecks can be measured.
**Checkpointing**: Marker rows provide recovery breadcrumbs when a file is interrupted before clean completion.
**Profile propagation**: Marker rows now also carry `IMU_PROFILE` and `IMU_VALIDATION` payloads so backend session processing can consume the selected mount profile directly.
**Fusion input rule**: `G` rows also contain accel/gyro values and should be treated as valid IMU samples by analysis tools unless a session-quality check rejects them.
**Lean estimation caution**: Accelerometer-only tilt should not be used as dynamic motorcycle lean during riding. Cornering, braking, acceleration, bumps, and vibration change the measured specific force. Current replay research uses gyro-primary attitude integration with gated accel drift correction and GPS curvature lean as an external comparison signal.

---

## ⚡ Flashing & Updates

### **1. Build and flash the native image**
From the repository root:

```bash
cd firmware
idf.py set-target esp32p4
idf.py build
idf.py flash monitor
```

Use `idf.py set-target esp32s3` when working with a compact custom board. See
[`firmware/FLASHING_GUIDE.md`](../firmware/FLASHING_GUIDE.md) for the manual
flash procedure and target-specific notes.

### **2. OTA status**
Native binary OTA can be added once the ESP-IDF device-side OTA contract is
finalized. Current firmware updates use the build-and-flash workflow in
[`firmware/FLASHING_GUIDE.md`](../firmware/FLASHING_GUIDE.md).

---

## 🏎️ ESP32-P4 & S3 Native C/C++ UI & Telemetry Architecture

With Phase 8 implementation, RaceSense utilizes a dual-core architectural split under native ESP-IDF 5.x:
* **Core 0 (PRO_CPU):** Dedicated to high-frequency hardware sensor ingestion through the timer-driven acquisition task (100 Hz target over I²C1 for the BMI323 and approximately 10 Hz over UART1 for the Neo-M8N GPS). Telemetry rows are pushed into a sensor queue without waiting for UI or SD filesystem access.
* **Core 1 (APP_CPU):** Manages the application state machine (`main.c`), the storage flush task (`storage.c`), and the LVGL graphical interface suite (`ui.c`). The P4 storage task now consumes the sensor-owned queue and waits for a producer/consumer drain acknowledgement before closing a session; live-session CSV writing is still awaiting hardware proof.

### **Thread-Safe LVGL Synchronization**
To eliminate thread deadlocks and memory corruption during simultaneous Core 0 telemetry reporting and Core 1 capacitive/resistive input handling:
* All UI view updates and widget mutations wrap their execution blocks in `ui_lock()` and `ui_unlock()`.
* These wrapper functions interface directly with ESP-IDF's master display lock via `lvgl_port_lock(timeout_ms)` and `lvgl_port_unlock()` (from `esp_lvgl_port.h`).

### **Complete Interactive Screen Topology**
* **Screen 1 (Boot Splash):** High-contrast startup verification.
* **Screen 2 (Home Dashboard):** Real-time battery, storage, satellite, and IMU operational status with touch launch targets for Logging, Sync, and Setup.
* **Screen 3 (Live Logging Cockpit):** Large hero lap timer clock, live ground speed (`km/h`), real-time lean angle tracking (`LEAN: xx.x° L/R`), and lap delta metrics with instant return navigation.
* **Screens 6–9 (Cloud Sync Suite):** WiFi scanning, progress reporting, and transmission summaries with abort action docks.
* **Screens 10–12 (Settings & Calibration Wizards):** Interactive configuration panel launching the SoftAP Captive Portal (`http://192.168.4.1/`) and a 6-stage guided IMU orientation wizard with live vibration noise monitoring.

---

## ⚠️ Hardware Precautions
*   **GPS Antenna**: Ensure a clear sky view. The Neo-M8N performance degrades significantly under carbon fiber or metal.
*   **SD Card**: Always use **Class 10** or faster cards. Slow cards can cause Core 0 to hang during long sessions.
*   **IMU Orientation**: Flat mounting is no longer a hard product requirement. The current firmware direction is arbitrary mounting with a saved per-profile calibration. The important rule is that the rider must calibrate the actual mount orientation being used. Note that BMI323 uses word-based I2C communication and a different register map (0x20/0x21 for conf) compared to the legacy BMI270.
