# ESP32 First-Time Setup Guide

## 1. Hardware Required
- ESP32 Development Board (DevKit V1 recommended)
- Micro-USB Data Cable (Make sure it handles data, not just charge!)
- Computer (Mac/Linux/Windows)

## 2. Software Tools
We need two main tools:
1.  **esptool**: To wipe the chip and flash MicroPython.
2.  **ampy** or **mpremote**: To upload our `.py` files.

### Install via PIP
```bash
pip install esptool adafruit-ampy mpremote
```

## 3. Flash MicroPython Firmware

### A. Download Firmware
1.  Go to [MicroPython ESP32 Downloads](https://micropython.org/download/ESP32_GENERIC/).
2.  Download the latest "Stable" `.bin` file (e.g., `v1.22.1.bin`).

### B. Identify Serial Port
- **Mac:** `ls /dev/cu.*` (Look for `/dev/cu.usbserial-0001` or `/dev/cu.SLAB_USBtoUART`)
- **Note on Drivers:** If you see `usbserial-0001` and flashing fails, you are using the buggy Apple Driver.
    - **Fix:** Install [Silicon Labs CP210x VCP Driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers).
    - After install, you should see `/dev/cu.SLAB_USBtoUART`. Use that one.

- **Linux:** `ls /dev/ttyUSB*`
- **Windows:** Check Device Manager (COM3, COM4...)

*Note: If no port appears, install the CP210x or CH340 drivers.*

### C. Erase Flash (Critical Step!)
```bash
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 erase_flash
```

### D. Write Firmware
```bash
esptool.py --chip esp32 --port /dev/cu.usbserial-0001 --baud 460800 write_flash -z 0x1000 esp32-2023xxxx-v1.xx.bin
```

## 4. Verify Installation
1.  Open a serial terminal (e.g., `screen` or `mpremote`).
    ```bash
    mpremote repl
    ```
2.  You should see `>>>`. Type `print("Hello ESP32")`.
3.  Exit with `Ctrl+]` (for mpremote) or `Ctrl-A, K` (for screen).

## 5. Upload Code (Workflow)
We use `ampy` to push files from our `firmware/esp32` folder.

```bash
cd firmware/esp32
# List files on board
ampy --port /dev/cu.usbserial-0001 ls

# Upload main.py
ampy --port /dev/cu.usbserial-0001 put main.py

# Soft Reset (Ctrl-D in REPL) to run
```

---

## Troubleshooting
- **Failed to connect?** Hold the "BOOT" button on the ESP32 when you see "Connecting..." in output.
- **Permission denied?** `sudo chmod 666 /dev/ttyUSB0` (Linux).
- **ImportError in Python?** Ensure you are running the `esptool` command in the environment where you installed it.
