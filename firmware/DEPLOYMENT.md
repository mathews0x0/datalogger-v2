# Racesense V2 (RS-Core) Deployment Guide

This guide is updated for the **ESP32-S3** based Racesense V2 hardware.

## ✅ **Hardware Features (V2)**
- **ESP32-S3-WROOM-1**: Faster processor, more IO, native USB.
- **MicroSD Support**: High-speed logging to SD card.
- **Native USB**: Programming and debugging via the USB-C port (IO19/20).
- **Battery Monitoring**: Integrated ADC for voltage tracking (IO35).
- **I2C IMU**: BMI323 on IO21/39.
- **GNSS**: Neo-M8N on IO17/18.

---

## 🚀 **Deployment Script**

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
├── boot.py             # Quick status blink
├── main.py             # Main logging loop (Core 0)
├── secrets.py          # WiFi and API configuration
├── drivers/
│   ├── gps.py          # Neo-M8N driver
│   ├── bmi323.py       # IMU driver
│   └── sdcard.py       # SPI SD Card driver
└── lib/
    ├── wifi_manager.py # Multi-network WiFi management
    ├── led_manager.py  # Neopixel animations
    ├── session_manager.py # Storage abstraction (SD vs Flash)
    ├── track_engine.py # Lap/Sector logic
    ├── miniserver.py   # Web API (Core 1)
    └── ble_provisioning.py # BLE Setup
```

---

## 🔧 **Configuration**

1. **WiFi**: Edit `secrets.py` with your credentials or use the BLE/Web Setup.
2. **SD Card**: Ensure a FAT32 formatted MicroSD card is inserted. If missing, the system will fallback to Internal Flash (`/data/learning`).

---

## 📊 **Dual-Core Architecture**

Racesense V2 utilizes both cores of the ESP32-S3:
- **Core 0**: Handles time-critical tasks (GPS updates, IMU sampling, SD logging).
- **Core 1**: Handles connectivity and management (Web Server, API requests).

This ensures that network activity does not cause "gaps" in your high-frequency telemetry data.

---

## ⚡ **Troubleshooting**

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
