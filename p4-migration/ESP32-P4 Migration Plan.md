# ESP32-P4 Migration Master Plan

## Goal

Migrate the existing ESP32-S3 MicroPython firmware to a native ESP-IDF C/C++ firmware project targeting the **Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3** hardware platform. 

The primary objective is to preserve existing backend API compatibility, server contracts, and core product behavior, while leveraging the new hardware (ESP32-P4 MCU, ESP32-C6 Wi-Fi 6 co-processor, 4.3" 480×800 IPS display, GT911 capacitive touch, and SDIO 3.0 storage).

The migration follows a strict phased workflow: preserve S3 as a baseline in `firmware_s3/`, conduct full discovery and triage before writing code, define the architecture, and then port and verify feature parity in `firmware_p4/`.

---

## Target Hardware Specification (Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3)

- **MCU**: ESP32-P4 RISC-V Dual-Core @ 400 MHz (32MB PSRAM, 32MB NOR Flash).
- **Wireless Co-Processor**: ESP32-C6-MINI (Wi-Fi 6 + Bluetooth 5 via SDIO/SPI hosted link).
- **Display & Touch**: 4.3" IPS 480×800 panel + GT911 Capacitive Touch.
- **Storage**: Native MicroSD slot via SDIO 3.0 (4-bit bus mode).
- **Power**: Onboard 3.7V Lithium battery management and power button interface.

---

## Model Selection Guidelines by Phase

| Phase | Phase Name | Primary Recommended Model | Focus |
|---|---|---|---|
| **Phase 1** | **Repository Structure & Isolation** | **Gemini 3.6 Flash** | Folder creation (`firmware_s3/`, `firmware_p4/`), asset movement, script reference updates. |
| **Phase 2** | **Discovery & Feature Inventory** | **Gemini 3.6 Flash (Medium/High)** | Ingesting all `firmware_s3/firmware/*.py` files, `docs/`, and server routes to map every feature & API contract. |
| **Phase 3** | **PM Diary Cross-Verification** | **Gemini 3.1 Pro / 3.6 Flash** | Deep document cross-referencing against `docs/pm_diary.md` to ensure no historical requirements are missed. |
| **Phase 4** | **Feature Triage & Scope Decision** | **Gemini 3.1 Pro / Claude Opus** | High-level trade-off analysis (Keep vs Retire vs Improve). |
| **Phase 5** | **ESP-IDF Target Architecture** | **Claude Sonnet / Gemini 3.1 Pro** | C/C++ FreeRTOS module design, `esp-hosted` link, SDIO 3.0 queues, and LVGL PPA architecture. |
| **Phase 6** | **Toolchain & Build Environment** | **Gemini 3.6 Flash** | Creation of `CMakeLists.txt`, `sdkconfig`, build scripts, and flashtool configuration. |
| **Phase 7** | **Core Feature Porting (C / IDF Code)** | **Claude Sonnet** | Low-level C/C++ driver code (BMI323 I2C DMA, NMEA GPS UART DMA, SDIO FATFS flusher, MbedTLS uploader). |
| **Phase 8** | **UI Refresh (LVGL 480×800)** | **Claude Sonnet / Gemini 3.6 Flash** | LVGL v8/v9 UI layout, high-DPI fonts, touch event binding. |
| **Phase 9** | **Verification & Hardware Sign-Off** | **Gemini 3.1 Pro / Claude Opus** | System verification, trace log auditing, regression checklist execution. |

---

## Migration Workflow & Phases

### Phase 1: Repository Structure & Platform Isolation
- Create two top-level platform directories in the project root:
  - `firmware_s3/` — Contains existing S3 `firmware/` and `hardware/` assets (frozen reference baseline).
  - `firmware_p4/` — Dedicated workspace with `firmware/` (ESP-IDF codebase) and `hardware/` (Waveshare BSP, 480×800 UI assets, CAD files, P4 tooling).

### Phase 2: Complete Discovery & Feature Inventory
- Audit all existing S3 firmware behavior end-to-end across actual source code and documentation:
  - Boot sequence, power hold, and safe boot window (`boot.py`, `main.py`).
  - Home screen, settings, mount calibration, and touch interaction (`lib/tft_ui.py`).
  - Sensor ingestion: 100Hz IMU (`drivers/bmi323.py`) and 10Hz NMEA GPS (`drivers/gps.py`).
  - Storage engine, CSV formatting, and marker rows `M` (`lib/session_manager.py`).
  - Sync mode, captive portal, and resumable HTTP uploader (`lib/uploader.py`).
  - Track engine and lap/sector LED feedback (`lib/track_engine.py`, `lib/led_manager.py`).
- Map all server-facing API contracts (`server/run.py`, HTTP headers `rsk_...`, upload offsets `X-Upload-Offset`) to guarantee 100% backend compatibility.

### Phase 3: Cross-Verification with Project History
- Cross-verify the compiled inventory against historical product decisions in `docs/pm_diary.md` and `docs/hardware_firmware.md`.
- Ensure core product requirements (e.g., Phase 1 "Truth Capture" 100Hz integrity, checkpoint marker rows, battery power preservation) are explicitly cataloged.

### Phase 4: Feature Triage & Scope Decision
- Categorize every feature from the inventory into three explicit buckets:
  1. **Must Preserve**: Essential product behaviors, data formats, server protocols, and safety features.
  2. **Retire / Eliminate**: Obsolete workarounds (e.g., resistive 5-point touch calibration, MicroPython framebuf limitations, legacy debug paths).
  3. **Target for Improvement**: Experience upgrades enabled by P4 (e.g., 60fps LVGL UI on 480×800 display, GT911 capacitive touch, zero-dropout SDIO 3.0 storage, deterministic FreeRTOS sensor tasks).
- Produce a finalized Triage & Scope Matrix before writing P4 code.

### Phase 5: Define ESP-IDF Target Architecture
- Design the modular C/C++ architecture inside `firmware_p4/firmware`:
  - Board Support Package (BSP): display (GT911 + 480×800 IPS), SDIO 3.0 FATFS, power/battery ADC.
  - Wireless Link: `esp-hosted` component integration for ESP32-C6 Wi-Fi 6 networking.
  - Telemetry Pipeline: FreeRTOS Core 0 hard real-time task pinning for 100Hz BMI323 (I2C DMA) and 10Hz GPS (UART DMA).
  - Storage Manager: Dual ring-buffer flusher to SDIO card.
  - UI Subsystem: LVGL v8/v9 with hardware PPA acceleration.
  - Cloud Sync: MbedTLS / HTTPS chunked uploader.

### Phase 6: Toolchain & Build Environment Setup
- Configure ESP-IDF project structure (`CMakeLists.txt`, `sdkconfig`).
- Establish flash, monitor, and debugging workflow for the Waveshare ESP32-P4 board.

### Phase 7: Core Feature Porting (Behavior Parity)
- Port features sequentially according to the triage plan:
  1. Boot, power management, and board initialization.
  2. Sensor ingestion & real-time telemetry storage.
  3. Basic UI navigation and capacitive touch integration.
  4. WiFi 6 network connectivity and cloud sync.
  5. Settings persistence and mount profile management.

### Phase 8: Experience Enhancement & UI Refresh
- Refine the 480×800 UI layout for optimal trackside readability.
- Implement hardware-accelerated animations and high-DPI font rendering.
- Optimize power management and battery diagnostics.

### Phase 9: Hardware Verification & Regression Sign-Off
- Execute a comprehensive validation checklist covering:
  - Boot-up & power-off reliability.
  - 100Hz IMU / 10Hz GPS sampling frequency and zero-dropout verification.
  - Storage integrity and file format compatibility.
  - Network upload reliability with backend server.
  - Full touch UI interaction test.

---

## Reference Documentation

- S3 Firmware Source: `firmware_s3/firmware`
- Hardware & Pinout Guide: `docs/hardware_firmware.md`
- Project History & PM Notes: `docs/pm_diary.md`
- Stack Architecture: `docs/tech_stack.md`
- Agent Governance & Memory: `.agent/memory.md`