# Racesense V2 (RS-Core) Deployment Guide

This guide is updated for the **ESP32-S3** based Racesense V2 hardware.

## ✅ **Hardware Features (V2)**
- **ESP32-S3-WROOM-1-N16R8**: Faster processor, more IO, native USB, 16MB flash, 8MB Octal PSRAM.
- **MicroSD Support**: High-speed logging to SD card.
- **Native USB**: Programming and debugging via the USB-C port (IO19/20).
- **Battery Monitoring**: Integrated ADC for voltage tracking (IO7).
- **I2C IMU**: BMI323 on IO21/39.
- **GNSS**: Neo-M8N on IO17/18.

---

## 🚀 **Deployment Script**

### Preferred MicroPython Build for This Board

For the **ESP32-S3-WROOM-1-N16R8**, keep a vetted local copy of the **ESP32_GENERIC_S3 octal-SPIRAM** firmware in the repo and flash only that local file:

- Preferred repo filename: `firmware/esp32s3-micropython-psram-oct.bin`
- Accepted fallback local filenames: `firmware/esp32s3-micropython.bin`, `firmware/micropython.bin`

The flashing tool now resolves firmware from local files only. It will not depend on any network location at flash time.

Use the `deploy.sh` script to push the firmware:

```bash
cd firmware
./deploy.sh --sync
```

**Note for Linux/Mac:** 
The ESP32-S3 usually appears as `/dev/ttyACM0` (Linux) or `/dev/cu.usbmodem*` (Mac). Update the `PORT` in `deploy.sh` if necessary.

---

## 📂 **File Structure on Device**

Your ESP32-S3 should have the following structure:

```
/
├── boot.py             # Internal bootstrapper
├── main.py             # Entry point (Starts Heartbeat thread)
├── data/
│   └── metadata/
│       ├── device.json # (Auto-generated) WiFi & API credentials
│       ├── display.json # Per-device TFT panel preset/config
│       ├── track.json  # Active track metadata
│       └── touch.json  # Per-device TFT touch calibration
├── drivers/
│   ├── gps.py          # Neo-M8N driver
│   ├── bmi323.py       # IMU driver
│   ├── sdcard.py       # SPI SD Card driver
│   ├── ili9341.py      # TFT display driver
│   └── xpt2046.py      # TFT resistive touch driver
└── lib/
    ├── wifi_manager.py # Multi-network WiFi management (Stealth)
    ├── led_manager.py  # Neopixel & Blue LED status patterns
    ├── session_manager.py # Storage abstraction (SD vs Flash)
    ├── track_engine.py # Lap/Sector logic
    ├── uploader.py      # background IoT Heartbeat & Upload thread
    ├── tft_ui.py        # ILI9341/XPT2046 rider-facing TFT UI
    ├── tft_wordmark.raw # raw RGB565 RaceSense boot wordmark asset
    ├── tft_fonts/       # generated TFT font package
    │   ├── renderer.py
    │   ├── ui.py
    │   └── data.py
    └── captive_portal.py # Magic Link provisioning portal
```

Normal firmware sync preserves `/data/metadata/`.

- Delete only `/data/metadata/display.json` if you want to force the first-boot TFT preset selection flow to run again.
- Delete only `/data/metadata/touch.json` if you want to force the second-boot TFT 5-point calibration to run again.

Clean sync must copy nested `lib` packages and raw assets. The current `flashtool.sh` and `push_to_device.sh` copy:

- `lib/*.py`
- `lib/*.raw`
- `lib/*/*.py`
- `drivers/*.py`

This is required for the TFT custom fonts, `tft_wordmark.raw`, display driver, touch driver, and SD driver. If `drivers/xpt2046.py` is missing, the TFT display now still initializes, but touch is disabled until a complete firmware sync restores the file.

The TFT boot path depends on `/lib/tft_wordmark.raw`: `boot.py` streams this full-screen RGB565 asset before `main.py` starts when `/data/metadata/display.json` already exists. If the display has not been selected yet on a fresh unit, `boot.py` skips the branded splash and `main.py` enters the TFT preset-selection flow instead.

---

## 🔧 **Configuration (Direct-to-Cloud)**

1. **Magic Link Provisioning**:
    *   Flash the device and reboot.
    *   Connect your phone to the `RS-Core-XXXX` hotspot.
    *   Navigate back to the web app (`racesense.in`) and use **Auto-Setup Device** or the captive portal.
    *   The captive portal stores `/data/metadata/device.json` on the device and then reboots.
2. **Manual Config**: (Fallback) You can manually create `/data/metadata/device.json` with the following structure:
    ```json
    {"ssid": "...", "password": "...", "api_url": "https://racesense.in/api/upload", "token": "rsk_...", "auto_log_enabled": true}
    ```

---

## 📊 **Dual-Core IoT Architecture**

Racesense V2 utilizes both cores of the ESP32-S3:
- **Core 0**: Handles time-critical tasks (GPS updates, IMU sampling, SD logging).
- **Sync Mode**: Handles background IoT services:
    - **Heartbeat**: POSTs every 15s to the cloud.
    - **Session Streamer**: Automatically uploads CSV logs to the cloud.
- **Logging Mode**: Runs with WiFi disabled and writes telemetry locally.

This ensures that network activity does not cause "gaps" in your high-frequency telemetry data.

---

## ⚡ **Troubleshooting**

### PSRAM Validation

After flashing the octal-PSRAM build, run:

```bash
cd firmware
./flashtool.sh
```

Then choose `Run PSRAM Probe`.

Expected outcome:
- boot logs show `[Memory] Boot: ... PSRAM=yes`
- the probe reports `PSRAM inference: DETECTED`
- contiguous allocation should succeed well past internal-RAM-only sizes, typically into multi-megabyte range

If the probe says `PSRAM inference: NOT DETECTED`, the board is almost certainly running the wrong MicroPython image.

### Native USB Connection
If the device is not detected, put it into **Download Mode**:
1. Hold **BOOT** button (IO0).
2. Press **RESET** button.
3. Release **BOOT** button.
4. The device will now appear as a generic ESP32-S3 USB JTAG/serial port.

### SD Mount Failure
- Check the `sdcard.py` driver and `main.py` pin settings (IO10-13).
- Ensure the SD card is formatted as FAT32.
- The system will blink **RED** if storage is unavailable or critical.
