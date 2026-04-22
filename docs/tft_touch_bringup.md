# TFT + Touch Bring-Up

This board can bring up a generic 2.8" 240x320 SPI TFT (`ILI9341`) with resistive touch (`XPT2046`) on a dedicated TFT/touch SPI bus.

## Current Firmware Wiring

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
| `TFT_RST` | Tie to `EN` or `3V3` | No dedicated GPIO used |
| `TOUCH_IRQ` | Not connected | Optional, skipped for minimal wiring |

Battery sense is temporarily remapped to `IO14` during this TFT bring-up phase.

## Legacy Bench Wiring

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
3. Keep `TFT_RST` and `TOUCH_IRQ` optional if you want the fewest wires.

Required TFT/touch control lines:

- `IO5` for `TFT_CS`
- `IO6` for `TFT_DC`
- `IO7` for `TOUCH_CS`

Then either:

- tie `TFT_RST` to `EN`, or
- wire `TFT_RST` to a spare GPIO if you want software reset control.

## Important Constraint

This temporary mapping deliberately repurposes the hardware sync button, onboard NeoPixel, and original battery-monitor net while the rider-facing TFT path is being developed.

## Touch Calibration

Touch calibration is device-specific and persists with metadata.

- Calibration runs automatically once if `/data/metadata/touch.json` is missing.
- Calibration can be rerun from the TFT Settings screen via `CALIB`.
- The calibration flow uses five points:
  - top-left
  - top-right
  - bottom-right
  - bottom-left
  - center
- Normal firmware sync should preserve `/data/metadata/touch.json`.
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

`TOUCH_IRQ` is still optional and not connected in the validated wiring. Adding it later should improve first-touch detection latency, but calibration quality, pressure threshold, shared SPI redraw blocking, and debounce still matter.

## Current TFT UX Assets

The rider-facing TFT path now uses generated assets instead of scaled `framebuf.text()` for polished screens.

- `firmware/lib/tft_fonts/renderer.py` renders generated MicroPython font assets.
- `firmware/lib/tft_fonts/ui.py` is the general UI font.
- `firmware/lib/tft_fonts/data.py` is the numeric/telemetry font.
- `firmware/lib/tft_wordmark.raw` is the RaceSense boot wordmark as full-screen RGB565 data.
- `firmware/tools/generate_tft_wordmark.swift` regenerates the wordmark raw asset and preview PNG.

The boot wordmark is streamed directly to the ILI9341 window for speed. `main.py` does not redraw it after TFT UI construction; the main UI transitions from the early wordmark to Home. Do not convert it back to a thresholded 1-bit mask; that loses the edge quality and turns the artwork into a blob.

Firmware sync must copy nested font packages, `.raw` files, and all drivers. Use the current `firmware/flashtool.sh` or `firmware/push_to_device.sh`, which copy `lib/*.py`, `lib/*.raw`, `lib/*/*.py`, and `drivers/*.py`.

If `drivers/xpt2046.py` is missing on-device, the TFT display should still initialize, but touch and calibration will be disabled until a complete firmware sync restores the driver.

## Home and Touch Zones

The old decision window is now Home. Home is the rider-facing landing page after the boot wordmark and the return target for Sync exits.

Current primary touch regions:

- Home bottom-left: `SYNC`
- Home bottom-center: gear/settings
- Home bottom-right: `LOG`
- Settings: `BACK`, Auto Log toggle, `WIFI`, `CALIB`
- Settings -> WiFi: `CHANGE` starts re-pairing, `EXIT` returns to Home
- Sync WiFi/search/idle/result: `EXIT` returns to Home where shown

## Test Script

Use [hardware/workbench/tft_touch_test.py](/Users/mj/Documents/datalogger-v2/hardware/workbench/tft_touch_test.py).

It currently expects:

- `TFT_CS=36`
- `TFT_DC=37`
- `TOUCH_CS=38`
- `TFT_RST` tied to `EN` or `3V3`
- no `TOUCH_IRQ`

and the shared SPI bus on `11/12/13`.

The production firmware path does not use this legacy bench mapping.
