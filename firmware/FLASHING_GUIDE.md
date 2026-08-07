# RaceSense Firmware Build, Flash, and Monitor Guide

The supported firmware is the native ESP-IDF project in this `firmware/`
directory. The default target is the Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3;
the same project can be built for a supported compact-board target by selecting
its ESP-IDF target explicitly.

## Quick workflow

Run this from an interactive terminal so the serial monitor can attach:

```bash
cd /Users/mj/Documents/datalogger-v2/firmware
./flashtool.sh
```

The helper will source ESP-IDF when needed, build the selected target, detect a
single USB modem, ask for confirmation, flash the board, and attach the
monitor.

Useful commands:

```bash
./flashtool.sh --list
./flashtool.sh --build-only
./flashtool.sh --flash-only --port /dev/cu.usbmodemXXXX
./flashtool.sh --monitor-only --port /dev/cu.usbmodemXXXX
./flashtool.sh --no-monitor --port /dev/cu.usbmodemXXXX
./flashtool.sh --target esp32s3 --build-only
```

Use `--yes` only after verifying the selected port:

```bash
./flashtool.sh --port /dev/cu.usbmodemXXXX --yes
```

`--flash-only` flashes the existing image and exits. `--monitor-only` and the
default workflow require an interactive TTY; use `--no-monitor` for scripts or
non-interactive build agents.

## ESP-IDF environment

The helper automatically loads the default ESP-IDF installation at
`/Users/mj/esp/esp-idf/export.sh`. To load it manually instead:

```bash
source /Users/mj/esp/esp-idf/export.sh
```

Override the installation path when necessary:

```bash
IDF_EXPORT=/path/to/esp-idf/export.sh ./flashtool.sh --build-only
```

## Direct build commands

```bash
cd /Users/mj/Documents/datalogger-v2/firmware
idf.py build
```

For another supported target, select it before building:

```bash
idf.py set-target esp32s3
idf.py build
```

Build artifacts are generated under `build/` and are not source files.

## Direct flashing

The helper is the preferred workflow because it checks the target, image, port,
and serial-port ownership before flashing. The equivalent direct command is:

```bash
idf.py -p /dev/cu.usbmodemXXXX -b 460800 flash
```

The current P4 image uses these ESP-IDF flash offsets if esptool must be used
directly:

```text
0x2000  build/bootloader/bootloader.bin
0x10000 build/partition_table/partition-table.bin
0x20000 build/racesense.bin
```

Always use the generated `build/flash_args` file or `idf.py flash` when working
with another target, since partition layouts can differ.

## Serial monitoring

Attach the decoded ESP-IDF monitor from an interactive terminal:

```bash
idf.py -p /dev/cu.usbmodemXXXX -b 115200 monitor
```

Exit with `Ctrl + ]`. The helper uses 460800 baud for flashing and 115200 baud
for monitoring by default; override them with `FLASH_BAUD` and `MONITOR_BAUD`.

## Boot verification

A healthy Waveshare P4 boot includes messages for:

```text
racesense: RaceSense ESP32-P4 Firmware Mark <current>
racesense: Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3
bsp_display: Display registered: 480x800 panel, 800x480 landscape UI
ui_engine: Hardware driver abstraction ready: ST7701 MIPI-DSI (800x480) + GT911 Touch
bsp: SD mounted at /sd
bmi323: BMI323 initialized
gps: Neo-M8N GPS ready
racesense: Entering HOME_IDLE
```

The display driver may report that `swap_xy` is unsupported; the firmware
already configures the panel and UI in the verified 800x480 landscape layout.

For repeatable bring-up, confirm that SD storage is mounted, the BMI323 reports
chip ID `0x43`, GPS telemetry is approximately 10 Hz, and periodic health lines
show zero dropped sensor rows.
