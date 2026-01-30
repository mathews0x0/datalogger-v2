## Quick Answer: NO - Files need to be manually uploaded

The files in `firmware/esp32/` are **not automatically pushed** to the ESP32 device. You need to manually upload them using the deployment script.

## ✅ **Automatic Deployment Script**

The `deploy.sh` script **automatically uploads ALL Python files** in your firmware directory:

**What it uploads:**
- All `.py` files in the root (`boot.py`, `main.py`, `secrets.py`, etc.)
- All `.py` files in `drivers/` directory
- All `.py` files in `lib/` directory

**You don't need to edit the script when adding new files!** Just add your `.py` file to the appropriate directory and run `./deploy.sh`.

## What Changed Recently?

**We just removed SD card support**, so you MUST re-upload these files for the changes to take effect:

### Critical Files to Update:
- ✅ `main.py` - Removed SD card initialization
- ✅ `lib/session_manager.py` - Now uses flash-only storage
- ✅ `lib/uploader.py` - Updated for new SessionManager API
- ⚠️ `drivers/sdcard.py` - **NO LONGER NEEDED** (can skip uploading)

## Deployment Methods

### Option 1: Automated Script (Recommended)

We've created a deployment script for you:

```bash
cd firmware/esp32
./deploy.sh
```

**What it does:**
1. Checks if `ampy` is installed
2. Verifies USB port connection
3. Uploads all necessary files in correct order:
   - Boot files: `boot.py`, `main.py`, `secrets.py`
   - Creates directories: `drivers/`, `lib/`
   - Uploads drivers: `gps.py` (skips `sdcard.py`)
   - Uploads libraries: `wifi.py`, `miniserver.py`, `session_manager.py`, `uploader.py`
4. Verifies deployment

**Before running:**
- Edit `deploy.sh` and set `PORT` to your device (default: `/dev/cu.usbserial-0001`)
- Find your port with: `ls /dev/cu.*` (Mac) or `ls /dev/ttyUSB*` (Linux)

### Option 2: Manual Upload (Step-by-Step)

If you prefer manual control:

```bash
cd firmware/esp32

# Set your port (change as needed)
PORT="/dev/cu.usbserial-0001"

# 1. Upload core files
ampy --port $PORT put boot.py
ampy --port $PORT put main.py
ampy --port $PORT put secrets.py

# 2. Create directories
ampy --port $PORT mkdir drivers
ampy --port $PORT mkdir lib

# 3. Upload drivers
ampy --port $PORT put drivers/gps.py drivers/gps.py
# Skip sdcard.py - no longer needed!

# 4. Upload libraries
ampy --port $PORT put lib/wifi.py lib/wifi.py
ampy --port $PORT put lib/miniserver.py lib/miniserver.py
ampy --port $PORT put lib/session_manager.py lib/session_manager.py
ampy --port $PORT put lib/uploader.py lib/uploader.py

# 5. Verify
ampy --port $PORT ls
ampy --port $PORT ls /drivers
ampy --port $PORT ls /lib
```

### Option 3: Using Thonny IDE

1. Open Thonny IDE
2. Go to **Run > Select Interpreter > MicroPython (ESP32)**
3. Select your COM/USB port
4. Use **File > Save As** and choose "MicroPython device"
5. Upload each file to the correct directory

## Post-Deployment

### Test the Device

Connect to serial console to see boot messages:

```bash
mpremote connect /dev/cu.usbserial-0001
```

Or use `screen`:

```bash
screen /dev/cu.usbserial-0001 115200
```

**Expected output:**
```
--- ESP32 DATALOGGER BOOT ---
Storage: ONBOARD FLASH (No SD Card)
SessionManager initialized (Flash): /sessions
WiFi: Connecting to <your_network>...
WiFi: Connected! IP: 192.168.1.x
Web server running on http://192.168.1.x
Starting Logging Loop...
Recording to: /sessions/sess_12345.csv (FLASH)
```

### Verify Storage

From REPL:

```python
>>> import os
>>> os.listdir('/sessions')
[]  # Empty initially, will fill as logging runs
>>> os.statvfs('/')
# Shows flash storage stats
```

## File Structure on ESP32

After deployment, your ESP32 should have:

```
/
├── boot.py
├── main.py
├── secrets.py
├── drivers/
│   └── gps.py
└── lib/
    ├── wifi.py
    ├── miniserver.py
    ├── session_manager.py
    └── uploader.py
```

**Note:** `/sessions/` directory will be created automatically on first boot.

## Troubleshooting

### "No such file or directory: /dev/cu.usbserial-0001"

Find your actual port:
```bash
ls /dev/cu.*  # Mac
ls /dev/ttyUSB*  # Linux
```

### "ampy: command not found"

Install ampy:
```bash
pip install adafruit-ampy
```

### "Failed to connect to ESP32"

1. Hold the **BOOT** button while running the command
2. Check if another program is using the port (close Arduino IDE, Thonny, etc.)
3. Try unplugging and replugging the USB cable

### "ImportError: no module named 'drivers.gps'"

You forgot to upload the `drivers/` folder. Run the deployment script again.

### Files are outdated on device

Delete everything and re-upload:
```bash
# WARNING: This erases ALL files on ESP32
mpremote connect /dev/cu.usbserial-0001 fs rm -r /
# Then run deploy.sh again
```

## Development Workflow

For active development:

1. **Edit** files on your computer in `firmware/esp32/`
2. **Upload** only the changed file:
   ```bash
   ampy --port /dev/cu.usbserial-0001 put main.py
   ```
3. **Restart** ESP32 (press EN/RST button or Ctrl+D in REPL)
4. **Test** via serial console

## Future: OTA Updates

Once WiFi is stable, we plan to implement **Over-The-Air (OTA) updates** so you can push code wirelessly without USB connection. This is not yet implemented.

---

**Bottom Line:** After making changes to ESP32 code, you MUST run `./deploy.sh` or manually upload the files. They don't automatically sync to the device.
