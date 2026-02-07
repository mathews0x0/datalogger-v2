# 📋 ESP32-S3 Motorcycle Datalogger - Schematic QA Report

**Project:** ESP32-S3 Motorcycle Datalogger  
**Date:** 2026-02-07  
**Schematic Version:** Final (Post-fixes)  
**Status:** ✅ APPROVED FOR PCB FABRICATION

---

## Executive Summary

This document provides a comprehensive quality assurance validation of the ESP32-S3 Motorcycle Datalogger schematic. All critical issues have been identified and resolved. The design is ready for PCB layout and fabrication.

---

## 🔧 Critical Issues - Resolution Status

### Issue #1: Battery Protection Diode (RESOLVED)

**Problem:** SS34 Schottky diode (D2) was placed in series with battery input, blocking charging current.

| Before | After |
|--------|-------|
| Batt+ → D2 (SS34) → VBAT | Batt+ → VBAT (direct) |
| Charging BLOCKED | Charging WORKS |

**Resolution:** Diode D2 removed. Battery connector now connects directly to VBAT net.

**Verification:**
- Battery Connector Pin 1 → VBAT net label
- No blocking component in charging path
- TP4054 BAT pin connects to VBAT

**Status:** ✅ FIXED

---

### Issue #2: Charging LED Circuit (RESOLVED)

**Problem:** CHRG LED was wired with anode to CHRG# (active-low open-drain), causing LED to never illuminate.

| Before | After |
|--------|-------|
| CHG_LED → LED Anode → LED → R8 → GND | 3V3 → R8 → LED Anode → LED Cathode → CHG_LED |
| LED never ON | LED ON when charging |

**Resolution:** LED circuit rewired with cathode connected to CHRG#, anode connected via resistor to 3V3.

**Verification:**
- R8 (220Ω) high-side connected to 3V3
- R8 low-side connected to LED anode
- LED cathode connected to CHG_LED (CHRG#)
- When CHRG# sinks to GND, current flows through LED

**Status:** ✅ FIXED

---

## 📊 Circuit-Level Validation Tests

### Test 1: Power Supply Path Analysis

| Test Case | Expected | Actual | Status |
|-----------|----------|--------|--------|
| USB only (no battery, switch ON) | USB_VBUS → TP4054 VDD, LDO via VBAT | Correct path verified | ✅ PASS |
| Battery only (switch ON) | VBAT → LDO VIN → 3V3_switch → 3V3 | Direct connection | ✅ PASS |
| USB + Battery (switch ON) | Both sources on VBAT node | Parallel connection | ✅ PASS |
| USB charging (switch OFF) | USB → TP4054 → charges battery | Direct VBAT path | ✅ PASS |
| Switch OFF (any power) | 3V3_switch floating, no 3V3 | Switch open circuit | ✅ PASS |

---

### Test 2: Signal Integrity Check

| Signal | Source | Destination | Pull-up/down | Status |
|--------|--------|-------------|--------------|--------|
| I2C_SDA | BMI160, ESP32 IO21 | I2C connector | R1 (4.7kΩ) to 3V3 | ✅ PASS |
| I2C_SCL | BMI160, ESP32 IO39 | I2C connector | R2 (4.7kΩ) to 3V3 | ✅ PASS |
| RESET (EN) | ESP32 EN | Button | R5 (4.7kΩ) to 3V3 | ✅ PASS |
| BOOT (IO0) | ESP32 IO0 | Button | R4 (4.7kΩ) to 3V3 | ✅ PASS |
| SD_CD | SD Card CD | ESP32 IO3 | R13 (10kΩ) to 3V3 | ✅ PASS |
| USB_DM/DP | USB-C | ESP32 IO19/20 | ESD protected | ✅ PASS |

---

### Test 3: Decoupling Capacitor Verification

| IC | Required | Placed | Value | Status |
|----|----------|--------|-------|--------|
| TP4054 VDD | Input cap | C3 | 1µF | ✅ PASS |
| LDO VIN | Input cap | C4 | 10µF | ✅ PASS |
| LDO VOUT | Output cap | C5 | 10µF | ✅ PASS |
| BMI160 VDDIO | Decoupling | C1 | 100nF | ✅ PASS |
| BMI160 VDD | Decoupling | C2 | 100nF | ✅ PASS |
| ESP32-S3 | Internal to module | - | - | ✅ N/A |

---

### Test 4: LED Current Limiting Verification

| LED | Resistor | Value | Vf (typ) | I_LED (calc) | Status |
|-----|----------|-------|----------|--------------|--------|
| PWR (Power) | R7 | 220Ω | ~2.8V | ~2.3mA | ✅ PASS |
| CHRG1 (Charging) | R8 | 220Ω | ~2.8V | ~2.3mA | ✅ PASS |
| LED (GPIO Debug) | R9 | 220Ω | ~2.8V | ~2.3mA | ✅ PASS |

---

## 🔌 Functional Validation Tests

### Test 5: ESP32-S3 Boot Sequence

| Strapping Pin | Boot State | Circuit | Expected Behavior | Status |
|---------------|------------|---------|-------------------|--------|
| GPIO0 (IO0) | HIGH (normal) | R4 pull-up, button to GND | Normal SPI Flash boot | ✅ PASS |
| GPIO0 (IO0) | LOW (button) | Button pressed | USB Download mode | ✅ PASS |
| EN | HIGH | R5 pull-up, button to GND | Chip enabled | ✅ PASS |
| EN | LOW (button) | Button pressed | Chip reset | ✅ PASS |
| GPIO3 | HIGH/LOW | SD_CD with R13 | Affects JTAG only, boot OK | ✅ PASS |
| GPIO45 | Floating | Not connected | Default VDD_SPI = 3.3V | ✅ PASS |
| GPIO46 | Floating | Not connected | Default safe state | ✅ PASS |

---

### Test 6: USB Programming Interface

| Aspect | Test | Status |
|--------|------|--------|
| USB D+/D- to ESP32 | IO19 (D-), IO20 (D+) connected | ✅ PASS |
| CC resistors | R10, R11 = 5.1kΩ to GND | ✅ PASS |
| VBUS routing | To TP4054 VDD for charging | ✅ PASS |
| ESD protection | USBLC6-2SC6 on D+/D-, VBUS | ✅ PASS |
| Native USB boot | Supported via IO19/20 | ✅ PASS |

---

### Test 7: I2C Bus (BMI160)

| Parameter | Requirement | Actual | Status |
|-----------|-------------|--------|--------|
| SDA connection | IO21 | IO21 ✓ | ✅ PASS |
| SCL connection | IO39 | IO39 ✓ | ✅ PASS |
| SDA pull-up | 2.2-10kΩ | 4.7kΩ (R1) | ✅ PASS |
| SCL pull-up | 2.2-10kΩ | 4.7kΩ (R2) | ✅ PASS |
| BMI160 address | 0x69 (SDO=HIGH) | SDO → 3V3 | ✅ PASS |
| BMI160 mode | I2C (CSB=HIGH) | CSB → 3V3 | ✅ PASS |
| Voltage level | 3.3V | VDD, VDDIO → 3V3 | ✅ PASS |

---

### Test 8: SPI Bus (MicroSD)

| Signal | ESP32 GPIO | SD Card Pin | Status |
|--------|------------|-------------|--------|
| CS | IO10 | CD/DAT3 (Pin 2) | ✅ PASS |
| MOSI | IO11 | CMD (Pin 3) | ✅ PASS |
| SCK | IO12 | CLK (Pin 5) | ✅ PASS |
| MISO | IO13 | DAT0 (Pin 7) | ✅ PASS |
| VDD | 3V3 | VDD (Pin 4) | ✅ PASS |
| VSS | GND | VSS (Pin 6) | ✅ PASS |
| Card Detect | IO3 | CD (Pin 9) | ✅ PASS |
| CD Pull-up | R13 to 3V3 | 10kΩ | ✅ PASS |

---

### Test 9: UART Interface (GPS)

| Signal | ESP32 GPIO | Connector Pin | Direction | Status |
|--------|------------|---------------|-----------|--------|
| TX | IO17 | Pin 3 (TX) | ESP32 → GPS | ✅ PASS |
| RX | IO18 | Pin 2 (RX) | GPS → ESP32 | ✅ PASS |
| 3V3 | - | Pin 1 | Power | ✅ PASS |
| GND | - | Pin 4 | Ground | ✅ PASS |

---

### Test 10: LED Data Output (Neopixel)

| Aspect | Test | Status |
|--------|------|--------|
| Data GPIO | IO4 | ✅ PASS |
| USB-C routing | LED_DATA on DP1, DP2 | ✅ PASS |
| GND connection | Pins 1, 12 | ✅ PASS |
| RMT compatibility | IO4 supports RMT | ✅ PASS |
| 3.3V logic | Compatible with most strips | ⚠️ CONDITIONAL |

> **Note:** 3.3V logic works with most WS2812B strips but may not meet strict datasheet requirements for 5V strips.

---

### Test 11: Battery Voltage Monitoring

| Component | Value | Function | Status |
|-----------|-------|----------|--------|
| R3 | 100kΩ | VBAT to mid-point | ✅ PASS |
| R12 | 100kΩ | Mid-point to GND | ✅ PASS |
| Divider ratio | 1:2 | 4.2V → 2.1V | ✅ PASS |
| ADC input | IO35 | ESP32 ADC1_CH7 | ✅ PASS |

**Firmware Reference:**
```python
adc_value = adc.read()  # 0-4095
battery_voltage = (adc_value / 4095) * 3.3 * 2
```

---

### Test 12: Charging System

| Test Case | Expected Behavior | Verified | Status |
|-----------|-------------------|----------|--------|
| USB connected, battery attached | TP4054 charges battery | Direct VBAT connection | ✅ PASS |
| Charge current | 500mA (R6 = 1kΩ) | 1000/R = 500mA | ✅ PASS |
| Charging LED | ON when charging | 3V3 → R8 → LED → CHRG# | ✅ PASS |
| Charge complete | LED OFF (CHRG# HIGH-Z) | Open circuit, no current | ✅ PASS |

---

### Test 13: Power Switch Operation

| Switch State | 3V3_switch | 3V3 | System | Status |
|--------------|------------|-----|--------|--------|
| OPEN | LDO VOUT | Floating | OFF | ✅ PASS |
| CLOSED | LDO VOUT | Connected to 3V3_switch | ON | ✅ PASS |

---

### Test 14: GPIO Extension

| GPIO | Pin # | Connector Net | Status |
|------|-------|---------------|--------|
| IO5 | 5 | GPIOExt1 | ✅ PASS |
| IO6 | 6 | GPIOExt2 | ✅ PASS |
| IO15 | 8 | GPIOExt3 | ✅ PASS |

---

### Test 15: USB ESD Protection (USBLC6-2SC6)

| Pin | Net | Function | Status |
|-----|-----|----------|--------|
| 1 (IO1) | USB_DM | D- protection | ✅ PASS |
| 2 (GND) | GND | Ground reference | ✅ PASS |
| 3 (IO2) | USB_DP | D+ protection | ✅ PASS |
| 4 (IO2) | USB_DP | D+ protection | ✅ PASS |
| 5 (VBUS) | USB_VBUS | Clamp reference | ✅ PASS |
| 6 (IO1) | USB_DM | D- protection | ✅ PASS |

---

## 📝 Complete GPIO Pin Assignment

| ESP32 Pin | GPIO | Function | Net | Status |
|-----------|------|----------|-----|--------|
| 1 | GND | Ground | GND | ✅ Used |
| 2 | 3V3 | Power | 3V3 | ✅ Used |
| 3 | EN | Reset | RESET | ✅ Used |
| 4 | IO4 | LED Data | LED_DATA | ✅ Used |
| 5 | IO5 | GPIO Extension 1 | GPIOExt1 | ✅ Used |
| 6 | IO6 | GPIO Extension 2 | GPIOExt2 | ✅ Used |
| 7 | IO7 | - | - | ⬜ Available |
| 8 | IO15 | GPIO Extension 3 | GPIOExt3 | ✅ Used |
| 9 | IO16 | - | - | ⬜ Available |
| 10 | IO17 | UART TX | TX | ✅ Used |
| 11 | IO18 | UART RX | RX | ✅ Used |
| 12 | IO8 | - | - | ⬜ Available |
| 13 | IO19 | USB D- | USB_DM | ✅ Used |
| 14 | IO20 | USB D+ | USB_DP | ✅ Used |
| 15 | IO3 | SD Card Detect | SD_CD | ✅ Used |
| 16 | IO46 | - | - | ⬜ Available |
| 17 | IO9 | - | - | ⬜ Available |
| 18 | IO10 | SD CS | SD_CS | ✅ Used |
| 19 | IO11 | SD MOSI | SD_MOSI | ✅ Used |
| 20 | IO12 | SD SCK | SD_SCK | ✅ Used |
| 21 | IO13 | SD MISO | SD_MISO | ✅ Used |
| 22 | IO14 | - | - | ⬜ Available |
| 23 | IO21 | I2C SDA | I2C_SDA | ✅ Used |
| 24 | IO47 | - | - | ⬜ Available |
| 25 | IO48 | - | - | ⬜ Available |
| 26 | IO45 | - | - | ⬜ Available |
| 27 | IO0 | Boot Mode | BOOT | ✅ Used |
| 28 | IO35 | Battery ADC | VBAT-SENSE | ✅ Used |
| 29-35 | IO36-42 | - | - | ⬜ Available |
| 36 | RXD0 | - | - | ⬜ Available |
| 37 | TXD0 | - | - | ⬜ Available |
| 38 | IO2 | Debug LED | GPIO_LED | ✅ Used |
| 39 | IO1 | - | - | ⬜ Available |
| 40-41 | GND | Ground | GND | ✅ Used |

**Summary:** 20 GPIOs used, 17 GPIOs available for future expansion

---

## 📦 Bill of Materials Summary

| Category | Component | Quantity | LCSC Part # |
|----------|-----------|----------|-------------|
| **ICs** | ESP32-S3-WROOM-1-N16R8 | 1 | C2913202 |
| | TP4054 (Charging IC) | 1 | C45384876 |
| | AP7365-33WG-7 (LDO) | 1 | C150742 |
| | BMI160 (IMU) | 1 | C94021 |
| | USBLC6-2SC6 (ESD) | 1 | C7519 |
| **Resistors** | 4.7kΩ 0603 (R1, R2, R4, R5) | 4 | C270129 |
| | 220Ω 0603 (R7, R8, R9) | 3 | - |
| | 5.1kΩ 0603 (R10, R11) | 2 | - |
| | 100kΩ 0603 (R3, R12) | 2 | C25803 |
| | 10kΩ 0603 (R13) | 1 | C25804 |
| | 1kΩ 0603 (R6) | 1 | - |
| **Capacitors** | 100nF 0603 (C1, C2) | 2 | - |
| | 1µF 0603 (C3) | 1 | - |
| | 10µF 0603 (C4, C5) | 2 | - |
| **LEDs** | Blue LED 0603 (PWR, CHRG1, LED) | 3 | C72041 |
| **Connectors** | USB-C 16-pin | 2 | C2765186 |
| | JST SM04B-SRSS-TB (4-pin) | 4 | C160404 |
| | JST SM02B-SRSS-TB (2-pin) | 2 | C160402 |
| | MicroSD TF-PUSH | 1 | C393941 |
| **Switches** | Tactile Button (BOOT, RESET) | 2 | C9900015607 |

---

## 📊 Test Results Summary

| Category | Tests | Passed | Failed | Notes |
|----------|-------|--------|--------|-------|
| Critical Fixes | 2 | 2 | 0 | All resolved |
| Power System | 5 | 5 | 0 | |
| Signal Integrity | 6 | 6 | 0 | |
| Decoupling | 5 | 5 | 0 | |
| LED Circuits | 3 | 3 | 0 | |
| Boot Sequence | 7 | 7 | 0 | |
| USB Interface | 5 | 5 | 0 | |
| I2C Bus | 7 | 7 | 0 | |
| SPI Bus | 8 | 8 | 0 | |
| UART | 4 | 4 | 0 | |
| LED Data Output | 5 | 4 | 1* | *3.3V logic conditional |
| Battery Monitoring | 4 | 4 | 0 | |
| Charging System | 4 | 4 | 0 | |
| Power Switch | 2 | 2 | 0 | |
| GPIO Extension | 3 | 3 | 0 | |
| ESD Protection | 6 | 6 | 0 | |
| **TOTAL** | **76** | **75** | **1*** | 98.7% Pass Rate |

---

## ⚠️ Known Limitations

1. **LED Data 3.3V Logic:** ESP32 outputs 3.3V, while WS2812B datasheet specifies 3.5V minimum for HIGH. Works with most strips in practice, but not guaranteed for all.

2. **No Reverse Polarity Protection:** Battery connects directly to VBAT. Protection removed to enable charging. Recommend:
   - Use keyed JST connectors (already specified)
   - Add polarity markings on PCB silkscreen
   - Use batteries with built-in protection circuits

3. **SD Card on GPIO3:** GPIO3 is a strapping pin for JTAG. SD card insertion state may affect JTAG mode selection. Does not affect normal boot or runtime operation.

---

## ✅ Final Verdict

| Criteria | Status |
|----------|--------|
| All critical issues resolved | ✅ |
| Power system functional | ✅ |
| All ICs have proper support circuits | ✅ |
| No floating critical pins | ✅ |
| Pull-ups/pull-downs where required | ✅ |
| ESD protection on USB | ✅ |
| Decoupling capacitors present | ✅ |
| LED current limiting resistors present | ✅ |
| Boot sequence verified | ✅ |

---

# 🎉 SCHEMATIC APPROVED FOR PCB FABRICATION

**Approval Date:** 2026-02-07  
**Next Step:** Proceed to PCB layout design

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-07 | 1.0 | Initial validation - identified 2 critical issues |
| 2026-02-07 | 1.1 | Issues resolved - Final approval |
