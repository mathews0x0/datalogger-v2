# TFT + Touch Bring-Up

This board can bring up a generic 2.8" 240x320 SPI TFT (`ILI9341`) with resistive touch (`XPT2046`) by reusing the existing SD-card SPI bus.

## Temporary Bench Wiring

This is the current temporary mapping for the quickest bring-up using spare GPIOs:

Shared SPI bus:

| TFT/Touch Pin | RS-Core Pin |
|---|---|
| `SCK` / `CLK` | `IO12` |
| `MOSI` / `DIN` / `SDI(MOSI)` | `IO11` |
| `MISO` / `DO` / `SDO(MISO)` | `IO13` |
| `VCC` | `3V3` |
| `GND` | `GND` |

Control lines:

| TFT/Touch Pin | RS-Core Pin | Notes |
|---|---|---|
| `TFT_CS` | `IO36` | Temporary bench mapping |
| `TFT_DC` | `IO37` | Temporary bench mapping |
| `TOUCH_CS` | `IO38` | Temporary bench mapping |
| `TFT_RST` | Tie to `EN` or `3V3` | No dedicated GPIO used |
| `TOUCH_IRQ` | Not connected | Optional, skipped for minimal wiring |

## Recommended Minimal Wiring

Shared SPI bus:

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
| `TFT_CS` | `IO14` | Free GPIO, good chip-select choice |
| `TFT_DC` | `IO15` | Broken out as GPIO extension |
| `TFT_RST` | `IO16` | Optional if tied to `EN` or pulled up |
| `TOUCH_CS` | `IO9` | Required for XPT2046 |
| `TOUCH_IRQ` | `IO8` | Optional but useful |

## Short Version

If you want both display and touch with the least firmware friction:

1. Share `IO11/12/13` with the SD-card SPI bus.
2. Add separate chip selects for TFT and touch.
3. Keep `TFT_RST` and `TOUCH_IRQ` optional if you want the fewest wires.

That reduces the mandatory extra GPIO count to three:

- `IO14` for `TFT_CS`
- `IO15` for `TFT_DC`
- `IO9` for `TOUCH_CS`

Then either:

- tie `TFT_RST` to `EN`, or
- wire `TFT_RST` to `IO16` if you want software reset control.

## Important Constraint

This temporary mapping avoids stealing the current button, LED, and battery-monitor pins.

## Test Script

Use [hardware/workbench/tft_touch_test.py](/Users/mj/Documents/datalogger-v2/hardware/workbench/tft_touch_test.py).

It currently expects:

- `TFT_CS=36`
- `TFT_DC=37`
- `TOUCH_CS=38`
- `TFT_RST` tied to `EN` or `3V3`
- no `TOUCH_IRQ`

and the shared SPI bus on `11/12/13`.
