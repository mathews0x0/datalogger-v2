# Startup Guide: Pi Datalogger Product

This guide details how to run the system in all 4 supported modes.

## Prerequisites
All commands assume you are in the root `datalogger-product` directory.
You must have the core analysis library in your python path:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/core-analysis
```

---

## 1. Cloud Server (Processing Only)

**Purpose:** Runs the backend API that accepts uploads and processes data (simulated for dev).

1.  **Navigate:** `cd cloud-backend`
2.  **Install:** `pip install -r requirements.txt` (Create if missing)
3.  **Run:**
    ```bash
    python3 api/main.py
    ```
    *(Note: You need to implement the cloud API first, currently it's a placeholder)*

---

## 2. Pi Dumb Logger (Cloud Mode)

**Purpose:** Pi logs data and uploads to cloud. No local analysis.

1.  **Navigate:** `cd firmware/pi`
2.  **Config:** Edit `src/config.py` -> Set `MODE = "DUMB_LOGGER"` (logic needed)
3.  **Run:**
    ```bash
    # Runs ONLY the logger service
    python3 -m src.main
    ```
4.  **Sync:** Script to check WiFi and upload `output/learning/*.csv` to Cloud URL.

---

## 3. ESP32 Dumb Logger

**Purpose:** ESP32 logs data to SD card.

1.  **Flash Firmware:** Flash MicroPython to ESP32.
2.  **Upload Code:** Use `ampy` or Thonny to upload `firmware/esp32/main.py` and `boot.py`.
3.  **Run:** Hard reset ESP32. It starts logging automatically on boot.
4.  **Status:** Blue LED = Logging. Red Blink = Error/No GPS.

---

## 4. Pi Standalone (Classic)

**Purpose:** Full system on Pi (Logging + Analysis + Web UI).

1.  **Navigate:** `cd firmware/pi`
2.  **Run Logger:**
    ```bash
    python3 -m src.main &
    ```
3.  **Run Companion Server:**
    ```bash
    python3 src/api/server.py
    ```
4.  **Access:** Open browser at `http://localhost:5000`

---

## Development Notes

### "Bridging" for Local Dev
To run the **Analysis Core** natively:
```bash
python3 core-analysis/datalogger_core/run_analysis.py <path_to_csv>
```

### Shared Logic
Both **Cloud Server** (Mode 1) and **Pi Standalone** (Mode 4) use the exact same `core-analysis` library. Changes there affect both.
