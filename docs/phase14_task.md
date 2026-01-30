# Task: Phase 14 - ESP32 Firmware Implementation

**Objective:** Build and validate the MicroPython firmware for the ESP32 Dumb Logger.

**Strategy:** Incremental buildup with validation gates.

---

### Step 1: Sanity Check (Blinky)
- [ ] Create `firmware/esp32/tests/test_blink.py`
- [ ] Logic: Toggle internal LED (Pin 2) every 500ms.
- [ ] Goal: Verify toolchain, upload capability, and boot cycle.

### Step 2: Storage Infrastructure (SD Card)
- [ ] Wiring: Determine SPI pins (MISO, MOSI, CLK, CS) for ESP32.
- [ ] Create `firmware/esp32/drivers/sd_card.py` (Import official driver).
- [ ] Create `firmware/esp32/tests/test_sd.py`:
    - Mount filesystem `/sd`.
    - Write `test.txt`.
    - Read back and verify content.
    - Measure write latency (Goal: <10ms for append).

### Step 3: Data Logging (CSV Engine)
- [ ] Create `firmware/esp32/core/logger.py`.
- [ ] Logic:
    - Open File `session_{timestamp}.csv`.
    - Buffer lines.
    - Flush to SD every N seconds.
- [ ] Test: Run for 1 hour logging dummy data at 10Hz. Check file integrity on PC.

### Step 4: Sensor Integration (GPS)
- [ ] Wiring: Define UART pins (RX/TX).
- [ ] Create `firmware/esp32/drivers/gps.py` (Minimal NMEA parser).
- [ ] Logic:
    - Read UART line.
    - Parse GNRMC/GNGGA for Lat/Lon/Speed.
    - Validate Checksum.
- [ ] Test: `test_gps.py` runs repl, prints coords.

### Step 5: The Feedback Loop (LEDs)
- [ ] Create `firmware/esp32/core/feedback.py`.
- [ ] Logic:
    - Load `track_map.json` from SD.
    - Check Geofence (Point-in-Polygon or Radius).
    - Light NeoPixel (Pin 5?).
- [ ] Test: Simulate GPS approach to sector line -> LED Change.

---

## Hardware Pinmap (Proposed ESP32 DevKit V1)

| Component | Pin | Function |
|-----------|-----|----------|
| **GPS TX** | 16 | UART RX |
| **GPS RX** | 17 | UART TX |
| **SD MOSI** | 23 | SPI MOSI |
| **SD MISO** | 19 | SPI MISO |
| **SD CLK** | 18 | SPI CLK |
| **SD CS** | 5 | SPI CS |
| **LED Data**| 4 | NeoPixel |
| **Button** | 0 | Boot/Input |

