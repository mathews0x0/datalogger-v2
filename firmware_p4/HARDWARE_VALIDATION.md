# P4 Hardware Validation Stage

This is the bring-up checklist for the supplied RaceSense P4 wiring. The
firmware now emits `[HW]` diagnostics every two seconds and performs a
non-destructive SD write/readback/remove test once at boot.

## Validated hardware baseline — 2026-08-04

| Subsystem | Bench result |
|---|---|
| ST7701 display | Pass — correct 800×480 landscape rendering |
| GT911 touch | Pass — calibration and touch positioning verified across the display |
| BMI323 | Pass — chip ID `0x43`; accelerometer and gyro both produce live lean response |
| Neo-M8N GPS | Pass — clean satellite lock and approximately 10 Hz configured/measured output |
| microSD | Pass — correct capacity, mount, write/readback, and runtime persistence in 1-bit/20 MHz mode |

This closes the initial P4 peripheral bring-up stage. It does not close the
separate production gaps for ESP32-C6 Wi-Fi, end-to-end session logging,
fault injection, or long-duration soak testing.

## Wiring under test

| Function | P4 connection |
|---|---|
| GPS RX | GPIO3 / UART1 TX |
| GPS TX | GPIO4 / UART1 RX |
| GPS power | 3.3 V and GND |
| BMI323 SDA | GPIO21 / I2C1 SDA |
| BMI323 SCL | GPIO22 / I2C1 SCL |
| BMI323 power | 3.3 V and GND |
| Battery ADC | `BAT → 200 kΩ → BAT_ADC → 100 kΩ → GND`, BAT_ADC at GPIO20 |
| SDMMC | P4 SDMMC host slot 0, CLK 43, CMD 44, D0–D3 39–42, LDO_VO4 I/O supply, active-low card power switch on GPIO45 |

## Acceptance checks

### Battery ADC

The divider ratio is 3.0, so the measured ADC pin voltage should be two-thirds
of the battery voltage:

| Battery | BAT_ADC target |
|---:|---:|
| 4.20 V | 2.80 V |
| 3.70 V | 2.47 V |
| 3.30 V | 2.20 V |

The serial trace must show a non-zero GPIO20 reading, and the reported battery
voltage should agree with a DMM within the divider/ADC calibration tolerance.

### GPS / NMEA

- UART1 must report TX=3 and RX=4.
- `lines`, `RMC`, and `GGA` counters must increase.
- `checksum_fail` should remain zero or explain any errors.
- The `last=` field should contain a raw `$GPRMC` or `$GPGGA` sentence.
- With antenna reception, `fix=valid`, latitude/longitude, and satellite count
  must become non-zero.

Validated result: the Neo-M8N obtains a clean satellite lock. UART transport,
UBX baud/rate configuration, NMEA checksums, satellite count, and the measured
approximately 10 Hz update rate all pass on the supplied hardware.

### BMI323

- The driver probes I²C1 at GPIO21/22 and accepts address `0x68` or `0x69`.
- Chip ID must be `0x43` and initialization must report `ok`.
- At rest, scaled acceleration magnitude should be approximately `1.0 g`.
- At rest, gyro values should be close to `0 dps`.
- Moving or rotating the module must change the raw and scaled values.

Validated result: the fitted BMI323 reports chip ID `0x43`, approximately 1 g
at rest, and responsive accelerometer and gyro values. Both channels drive the
live lean/motion diagnostics correctly while GT911 touch is active on its
separate I²C bus.

### Display and touch

- ST7701 must render the full 800×480 landscape UI with correct orientation.
- GT911 touch points must correspond to the displayed controls across corners,
  edges, and center.
- Saved calibration must reload after reboot without requiring recalibration.
- Repeated Home, Settings, and Hardware Debug navigation must remain usable.

Validated result: the display is correctly oriented and rendered, GT911 touch
calibration is accurate across the screen, calibration persists, and normal
screen navigation is operational.

### SD card

- Boot must report the card mounted at `/sd` and print card information.
- The boot validation must report `SD validation: write/readback/remove OK`.
- Usage must be a valid percentage rather than `-1`.
- The card must remain mounted after the validation test.

Validated bench result: selecting P4 host slot 0 and enabling LDO_VO4 allows
the 7.5 GB SDHC card to initialize. This board/card still fails the 4-bit SSR
read, so firmware automatically retries in 1-bit mode at 20 MHz. The fallback
mount reports valid card metadata and usage, and the boot create/write/read/
remove validation passes. The card remained mounted during runtime telemetry.

A verified 4 MiB sequential benchmark measured 0.65 MiB/s write and 0.73 MiB/s
read in 1-bit/20 MHz mode. The filesystem reports 8,044,675,072 total bytes
(7.49 GiB) and 7.42 GiB free. The benchmark file was removed afterward.

The Home UI now queries FATFS directly instead of showing the former hardcoded
`18.5 GB FREE` placeholder. A nominal 8 GB card showing 7.49 GiB is expected
because manufacturers advertise decimal GB while the UI reports binary GiB,
with a small additional filesystem overhead.

## Run procedure

The current project build is ready at
`firmware_p4/firmware/build/racesense_p4.bin`.
Flashing remains a manual operation:

```bash
cd firmware_p4/firmware
source /Users/mj/esp/esp-idf/export.sh
/Users/mj/esp/esp-idf/tools/idf.py -p /dev/cu.usbmodem5B901592481 flash monitor
```

Capture at least 30 seconds of `[HW]` output at rest, then repeat with the GPS
antenna connected and while gently moving the BMI323. Do not start logging
until the queue and CSV-path issues in `GAP_ANALYSIS.md` are resolved.
