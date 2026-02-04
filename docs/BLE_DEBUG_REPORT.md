# ESP32 BLE Advertising Not Visible - Technical Investigation

## Environment
- **Board**: ESP32-D0WD-V3 (revision v3.1)
- **Crystal**: 40MHz
- **MAC Address**: 20:E7:C8:7D:BA:62
- **Firmware**: MicroPython v1.22.1 (2024-01-05)
- **Build Type**: Generic ESP32 module (`_machine='Generic ESP32 module with ESP32'`)
- **Firmware File**: micropython.bin (1,737,664 bytes)

## Problem Statement
BLE advertising initiated via `bluetooth.BLE.gap_advertise()` executes without any Python-level errors, but the device is completely invisible to BLE central devices (MacBook Pro, iPhone, Android).

## What Works
1. ✅ `bluetooth.BLE()` object creates successfully
2. ✅ `ble.active(True)` returns `True`
3. ✅ `ble.config('mac')` returns valid MAC: `(0, b'\x20\xe7\xc8\x7d\xba\x62')`
4. ✅ `ble.config('gap_name')` returns `b'MPY ESP32'`
5. ✅ `ble.gatts_register_services()` registers GATT services, returns handle tuples
6. ✅ `ble.gap_advertise(interval_us, adv_data)` returns `None` (expected)
7. ✅ WiFi works perfectly (AP mode confirmed)
8. ✅ BLE NVS namespace accessible

## What Does NOT Work
- ❌ Device never appears in any BLE scanner (Mac System Preferences, iPhone Bluetooth, nRF Connect app, LightBlue app)
- ❌ Even with WiFi completely disabled (`STA_IF.active(False)`, `AP_IF.active(False)`)
- ❌ With various advertising intervals (100ms, 200ms, 500ms, 1000ms)
- ❌ With minimal payloads (just flags + name, 12 bytes)
- ❌ With standard service UUIDs (Battery Service 0x180F)

## Test Code Used (Verified Working Format)
```python
import bluetooth
import time
import struct

ble = bluetooth.BLE()
ble.active(False)
time.sleep(1)
ble.active(True)
time.sleep(1)

# Standard advertising payload format from MicroPython examples
_ADV_TYPE_FLAGS = 0x01
_ADV_TYPE_NAME = 0x09

def advertising_payload(name):
    payload = bytearray()
    # Flags: General Discoverable, BR/EDR Not Supported
    payload += struct.pack('BBB', 2, _ADV_TYPE_FLAGS, 0x06)
    # Complete Local Name
    payload += struct.pack('BB', len(name) + 1, _ADV_TYPE_NAME) + name
    return payload

adv = advertising_payload(b'MPYTEST')
print(f'Payload: {adv.hex()}')  # Output: 02010608094d505954455354

ble.gap_advertise(100000, adv)  # 100ms interval in microseconds
time.sleep(30)  # Device should be visible for 30 seconds
ble.active(False)
```

## Diagnostic Output
```
BLE Active: True
Payload hex: 02010608094d505954455354
Payload len: 12
gap_advertise returns: None
```

## Suspected Root Causes

### 1. Firmware Build Configuration (Most Likely)
The "Generic ESP32 module" build may have BLE disabled or misconfigured at the ESP-IDF level. The `bluetooth` module provides a Python API wrapper, but the underlying NimBLE/Bluedroid stack may not be properly initialized or the RF calibration data may be missing.

**Evidence**: WiFi works fine, which uses the same radio, suggesting hardware is OK but BLE-specific configuration is missing.

### 2. NimBLE vs Bluedroid Stack Issue
MicroPython ESP32 builds can use either NimBLE or Bluedroid. If compiled with one stack but runtime configured for another, RF won't initialize.

### 3. RF Calibration / PHY Initialization
The BLE radio requires specific RF calibration data stored in eFuse. If the firmware doesn't properly read this calibration data, the radio won't transmit at the correct power/frequency.

### 4. Coexistence Controller Issue
The ESP32 has a coexistence controller for WiFi/BT sharing. Even with WiFi disabled in Python, the lower-level coex controller may not be releasing resources to BT properly.

## Requested Help
1. Is there a specific MicroPython build known to work with BLE on ESP32-D0WD-V3?
2. Is there a way to verify at the ESP-IDF level that the BLE radio is actually transmitting?
3. Should I try a different firmware source (e.g., build from source with explicit BLE enabled)?

## Files Available
- `/Users/mj/Documents/datalogger-v2/firmware/micropython.bin` - Current firmware
- `/Users/mj/Documents/datalogger-v2/firmware/diag_ultra_ble.py` - Diagnostic script
