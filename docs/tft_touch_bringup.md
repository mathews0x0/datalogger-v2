# Compact TFT + Touch Bring-Up

The native ESP-IDF firmware supports the compact 2.8" 240x320 SPI TFT
(`ILI9341`) with resistive touch (`XPT2046`) as its secondary target. The
production baseline remains the Waveshare 4.3" board; both targets use the
same firmware project under `firmware/`.

## Compact-Board Wiring

This is the current validated mapping used by the firmware runtime:

Dedicated TFT/touch SPI bus:

| TFT/Touch Pin | RS-Core Pin |
|---|---|
| `SCK` / `CLK` | `IO15` |
| `MOSI` / `DIN` / `SDI(MOSI)` | `IO16` |
| `MISO` / `DO` / `SDO(MISO)` | `IO9` |
| `VCC` | `3V3` |
| `GND` | `GND` |

Control lines:

| TFT/Touch Pin | RS-Core Pin | Notes |
|---|---|---|
| `TFT_CS` | `IO5` | Temporarily repurposes hardware sync button pin |
| `TFT_DC` | `IO6` | Temporarily repurposes onboard NeoPixel pin |
| `TOUCH_CS` | `IO7` | Temporarily repurposes original battery ADC net |
| `TFT_RST` | `IO42` | Dedicated TFT hardware reset |
| `TOUCH_IRQ` | `IO38` | Dedicated touch IRQ input |

Battery sense is temporarily remapped to `IO14` during this TFT bring-up phase.

## Bench Wiring

Older standalone workbench scripts used the SD-card SPI bus and spare high GPIOs:

| TFT/Touch Pin | RS-Core Pin |
|---|---|
| `SCK` / `CLK` | `IO12` |
| `MOSI` / `DIN` / `SDI(MOSI)` | `IO11` |
| `MISO` / `DO` / `SDO(MISO)` | `IO13` |
| `VCC` | `3V3` |
| `GND` | `GND` |

Extra control lines:

| TFT/Touch Pin | RS-Core Pin | Notes |
|---|---|---|
| `TFT_CS` | `IO36` | Legacy bench mapping |
| `TFT_DC` | `IO37` | Legacy bench mapping |
| `TOUCH_CS` | `IO38` | Legacy bench mapping |
| `TFT_RST` | Tie to `EN` or `3V3` | No dedicated GPIO used |
| `TOUCH_IRQ` | Not connected | Optional, skipped for minimal wiring |

## Short Version

If you want both display and touch with the least firmware friction:

1. Use the dedicated TFT/touch SPI bus on `IO15/16/9`.
2. Keep SD card traffic isolated from TFT traffic.
3. Use the dedicated reset and IRQ lines; this is now the preferred architecture.

Required TFT/touch control lines:

- `IO5` for `TFT_CS`
- `IO6` for `TFT_DC`
- `IO7` for `TOUCH_CS`
- `IO42` for `TFT_RST`
- `IO38` for `TOUCH_IRQ`

## Important Constraint

This temporary mapping deliberately repurposes the hardware sync button, onboard NeoPixel, and original battery-monitor net while the rider-facing TFT path is being developed.

## First-Boot Display Selection and Calibration

The TFT path now uses two per-device metadata files:

- `/data/metadata/display.json`
- `/data/metadata/touch.json`

Current boot behavior:

- If `/data/metadata/display.json` is missing, the device enters a first-boot TFT preset selection flow.
- The screen cycles through known panel presets automatically.
- Any touch is treated as “this preset looks correct”.
- The selected display config is saved and the device reboots.
- On the next boot, if `/data/metadata/touch.json` is still missing, the device runs the 5-point touch calibration flow.
- After calibration is saved, the device reboots again.

Touch calibration is device-specific and persists with metadata.

- Calibration runs automatically on the second boot if `/data/metadata/touch.json` is missing and `/data/metadata/display.json` already exists.
- Calibration can be rerun from the TFT Settings screen via `CALIB`.
- The calibration flow uses five points:
  - top-left
  - top-right
  - bottom-right
  - bottom-left
  - center
- Normal firmware sync should preserve `/data/metadata/display.json` and `/data/metadata/touch.json`.
- Delete only `/data/metadata/display.json` if you want to force the panel-selection flow again.
- Delete only `/data/metadata/touch.json` if you want to force recalibration.

## Touch Responsiveness

The current production firmware still runs without `TOUCH_IRQ`; touch is polled in the Home/settings/sync loops.

Software responsiveness improvements currently in firmware:

- touch debounce is 110 ms
- debounce is checked before performing the expensive XPT2046 SPI read
- Home and settings screens do not redraw when visible state is unchanged
- settings renders once, then polls touch before future redraw work
- Home/settings loop delay is 30 ms
- Sync entry and WiFi search invalidate stale render caches before drawing animation frames

`TOUCH_IRQ` is now part of the validated production wiring. It reduces idle polling, but calibration quality, pressure threshold, shared SPI redraw blocking, and debounce still matter.

## Native Firmware Assets

The display controller and touch driver are selected by the ESP-IDF target
configuration. The native project uses LVGL for both the 800x480 Waveshare UI
and the compact 320x240 UI; there is no MicroPython file-sync or runtime asset
bundle to deploy.


## Home and Touch Zones

The old decision window is now Home. Home is the rider-facing landing page after the boot wordmark and the return target for Sync exits.

Current primary touch regions:

- Home bottom-left: `SYNC`
- Home bottom-center: gear/settings
- Home bottom-right: `LOG`
- Settings: `BACK`, Auto Log toggle, `WIFI`, `CALIB`
- Settings -> WiFi: `CHANGE` starts re-pairing, `EXIT` returns to Home
- Sync WiFi/search/idle/result: `EXIT` returns to Home where shown

## Test Coverage

Use the native firmware target and host tests under
[`firmware/tests/`](../firmware/tests/) for regression checks. The old Python
workbench script is retained only as historical wiring documentation.

It currently expects:

- `TFT_CS=36`
- `TFT_DC=37`
- `TOUCH_CS=38`
- `TFT_RST` tied to `EN` or `3V3`
- no `TOUCH_IRQ`

and the shared SPI bus on `11/12/13`.

The production firmware path does not use this legacy bench mapping.
