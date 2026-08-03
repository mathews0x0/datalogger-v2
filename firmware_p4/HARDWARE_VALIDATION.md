# P4 Hardware Validation Stage

This is the bring-up checklist for the supplied RaceSense P4 wiring. The
firmware now emits `[HW]` diagnostics every two seconds and performs a
non-destructive SD write/readback/remove test once at boot.

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

### BMI323

- The driver probes I²C1 at GPIO21/22 and accepts address `0x68` or `0x69`.
- Chip ID must be `0x43` and initialization must report `ok`.
- At rest, scaled acceleration magnitude should be approximately `1.0 g`.
- At rest, gyro values should be close to `0 dps`.
- Moving or rotating the module must change the raw and scaled values.

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

## Run procedure

The current project build is ready at `firmware/build/racesense_p4.bin`.
Flashing remains a manual operation:

```bash
cd firmware_p4/firmware
source /Users/mj/esp/esp-idf/export.sh
/Users/mj/esp/esp-idf/tools/idf.py -p /dev/cu.usbmodem5B901592481 flash monitor
```

Capture at least 30 seconds of `[HW]` output at rest, then repeat with the GPS
antenna connected and while gently moving the BMI323. Do not start logging
until the queue and CSV-path issues in `GAP_ANALYSIS.md` are resolved.
