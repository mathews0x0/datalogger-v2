# ⚡ RaceSense ESP32-P4/S3 Firmware Flashing Guide

This document provides definitive instructions for compiling, building, and deploying the RaceSense multi-platform datalogger firmware onto target hardware devices.

---

## 🖥️ Supported Target Architecture & Hardware Profiles

The codebase leverages an adaptive **Board Support Package (BSP)** that dynamically configures GPIO mapping, memory boundaries, and LVGL display drivers based on the selected build target:

1. **Target 1: Production ESP32-P4 Platform**
   * **Hardware:** Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
   * **Display & Input:** 4.3" 800×480 Widescreen TFT via ST7701 (MIPI-DSI / Parallel RGB) with GT911 Capacitive Touch.
   * **Memory:** High-speed external DDR/PSRAM allocation for double-buffered LVGL canvas.

2. **Target 2: Development & Test Harness ESP32-S3 Platform**
   * **Hardware:** ESP32-S3 Custom Test Rig / Dev Module
   * **Display & Input:** 320×240 TFT via ILI9341 (High-speed SPI, 20MHz DMA) with XPT2046 Resistive Touch (with Affine Transformation matrix).
   * **Color Profile:** 16-bit RGB565 with hardware byte-swap enabled (`CONFIG_LV_COLOR_16_SWAP=y`).

---

## 🛠️ Environment Initialization & Build Workflow

### 1. Initialize ESP-IDF Toolchain
Before building or flashing, ensure your terminal session has sourced the official Espressif ESP-IDF v5.x environment variables:

```bash
source $HOME/esp/esp-idf/export.sh
```
*(On standard typical installations, this is located at `/Users/<username>/esp/esp-idf/export.sh` or `~/esp/esp-idf/export.sh`)*

### 2. Build the Firmware Project
Navigate into the target firmware directory and invoke the build engine:

```bash
cd firmware_p4/firmware
idf.py build
```

> [!NOTE]
> **Managed Components & Build Artifacts:**
> When running `idf.py build` for the first time, the **ESP Component Registry (IDF Component Manager)** will automatically download required external dependencies (LVGL core, ESP-IDF port abstractions, touchscreen drivers) into `managed_components/`. Both `managed_components/` and `build/` are explicitly excluded in `.gitignore` and should **not** be committed to source control.

---

## ⚡ Flashing Instructions

Due to project safety governance (**Rule 2: No Firmware Flashing by Automated Agents**), all firmware deployments must be manually executed by the user via terminal terminal command to prevent accidental overwrites or hardware bricking.

Ensure your device is plugged in via USB-C to your data transmission port.

### Method 1: Automated Deployment via `@flash_args` (Recommended)
The ESP-IDF build process generates a consolidated arguments profile inside the `build/` folder. This ensures memory offset accuracy:

```bash
cd build
python -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset write_flash "@flash_args"
cd ..
```
*(Note: Replace `--chip esp32s3` with `--chip esp32p4` when compiling for production P4 hardware).*

### Method 2: Explicit Binary Offset Mapping
To deploy binaries using manual file path addressing from the root `firmware/` folder:

```bash
python -m esptool --chip esp32s3 -b 460800 \
  --before default_reset --after hard_reset \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0     build/bootloader/bootloader.bin \
  0x8000  build/partition_table/partition-table.bin \
  0x10000 build/racesense_p4.bin
```

---

## 📡 Serial Console & Live Telemetry Monitoring

To verify successful boot execution and inspect real-time Core 0 telemetry pipelines / UI events:

```bash
idf.py monitor
```
*To exit the serial monitor, press `Ctrl + ]`.*

### Expected Boot Verification Output
When booted successfully, your console will output:
```text
I (xxx) racesense: ╔══════════════════════════════════════════╗
I (xxx) racesense: ║   RaceSense ESP32-P4 Firmware  v0.1.0  ║
I (xxx) racesense: ║   Waveshare ESP32-P4-WIFI6-LCD-4.3     ║
I (xxx) racesense: ╚══════════════════════════════════════════╝
I (xxx) ui_engine: Hardware driver abstraction ready: ILI9341 SPI + XPT2046 Touch
I (xxx) racesense: [BOOT] Registering UI event listener and launching Home Dashboard on Core 1
```

---

## 🔒 Governance & Operational Policy
* **Rule 1 (No Autonomous Changes):** All code changes and features must be approved prior to implementation.
* **Rule 2 (No Firmware Flashing):** Automated coding assistants are prohibited from initiating serial write operations (`idf.py flash` or `esptool write_flash`).
* **Rule 5 (Separate Concerns):** UI design iterations and core real-time telemetry processing logic are developed and verified independently.
