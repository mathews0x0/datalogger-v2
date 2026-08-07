#!/bin/bash
# RaceSense native firmware build, flash, and monitor helper.
#
# Safe default: build first, show the selected target/port, ask for flash
# confirmation, then attach the ESP-IDF monitor after a successful flash.

set -e

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEFAULT_IDF_EXPORT="/Users/mj/esp/esp-idf/export.sh"
IDF_EXPORT="${IDF_EXPORT:-$DEFAULT_IDF_EXPORT}"
TARGET="${IDF_TARGET:-}"
PORT="${PORT:-}"
FLASH_BAUD="${FLASH_BAUD:-460800}"
MONITOR_BAUD="${MONITOR_BAUD:-115200}"
DO_BUILD=1
DO_FLASH=1
DO_MONITOR=1
ASSUME_YES=0

usage() {
    cat <<'EOF'
Usage: ./flashtool.sh [options]

Build, flash, and monitor the native RaceSense ESP-IDF firmware.

Options:
  --port PORT       Serial device, e.g. /dev/cu.usbmodem5B901592481
  --target TARGET   ESP-IDF target (default: sdkconfig target or esp32p4)
  --no-build        Skip the build step
  --build-only      Build but do not flash or monitor
  --flash-only      Flash the existing build without rebuilding
  --monitor-only    Attach monitor without building or flashing
  --no-monitor      Flash and exit without attaching monitor
  --yes             Skip the flash confirmation prompt
  --list            List detected USB modem ports and exit
  -h, --help        Show this help

Environment:
  IDF_EXPORT        ESP-IDF export.sh path
  PORT              Default serial port
  IDF_TARGET        Default ESP-IDF target
  FLASH_BAUD        Flash baud rate (default: 460800)
  MONITOR_BAUD      Monitor baud rate (default: 115200)

Examples:
  ./flashtool.sh
  ./flashtool.sh --port /dev/cu.usbmodem5B901592481 --yes
  ./flashtool.sh --target esp32s3
  ./flashtool.sh --build-only
EOF
}

die() {
    echo "flashtool: $*" >&2
    exit 1
}

list_ports() {
    local found=0
    local candidate
    for candidate in /dev/cu.usbmodem* /dev/tty.usbmodem*; do
        if [ -e "$candidate" ]; then
            echo "$candidate"
            found=1
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "No USB modem ports detected." >&2
        return 1
    fi
}

detect_port() {
    local candidates=()
    local candidate
    for candidate in /dev/cu.usbmodem*; do
        if [ -e "$candidate" ]; then
            candidates[${#candidates[@]}]="$candidate"
        fi
    done

    if [ "${#candidates[@]}" -eq 0 ]; then
        die "No /dev/cu.usbmodem* device found. Connect the board or pass --port PORT."
    fi
    if [ "${#candidates[@]}" -gt 1 ]; then
        echo "Multiple USB modem ports detected:" >&2
        printf '  %s\n' "${candidates[@]}" >&2
        die "Pass the intended device explicitly with --port PORT."
    fi
    PORT="${candidates[0]}"
}

check_port_available() {
    if [ ! -e "$PORT" ]; then
        die "Serial port does not exist: $PORT"
    fi
    if command -v lsof >/dev/null 2>&1; then
        local owner
        owner="$(lsof -t "$PORT" 2>/dev/null || true)"
        if [ -n "$owner" ]; then
            die "Serial port is busy (PID $owner): $PORT. Stop the existing monitor first."
        fi
    fi
}

check_monitor_tty() {
    if [ ! -t 0 ] || [ ! -t 1 ]; then
        die "Serial monitor requires an interactive terminal. Run from a TTY or use --no-monitor."
    fi
}

target_from_sdkconfig() {
    if [ -f "$SCRIPT_DIR/sdkconfig" ]; then
        sed -n 's/^CONFIG_IDF_TARGET="\([^"]*\)".*$/\1/p' "$SCRIPT_DIR/sdkconfig" | head -n 1
    fi
}

confirm_flash() {
    if [ "$ASSUME_YES" -eq 1 ]; then
        return
    fi
    echo
    echo "About to flash native RaceSense firmware:"
    echo "  target: $TARGET"
    echo "  port:   $PORT"
    printf 'Continue? [y/N] '
    read answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) die "Flash cancelled." ;;
    esac
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --port)
            [ "$#" -ge 2 ] || die "--port requires a value"
            PORT="$2"
            shift 2
            ;;
        --target)
            [ "$#" -ge 2 ] || die "--target requires a value"
            TARGET="$2"
            shift 2
            ;;
        --no-build)
            DO_BUILD=0
            shift
            ;;
        --build-only)
            DO_BUILD=1
            DO_FLASH=0
            DO_MONITOR=0
            shift
            ;;
        --flash-only)
            DO_BUILD=0
            DO_FLASH=1
            DO_MONITOR=0
            shift
            ;;
        --monitor-only)
            DO_BUILD=0
            DO_FLASH=0
            DO_MONITOR=1
            shift
            ;;
        --no-monitor)
            DO_MONITOR=0
            shift
            ;;
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --list)
            list_ports
            exit 0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1 (use --help for usage)"
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    TARGET="$(target_from_sdkconfig)"
fi
TARGET="${TARGET:-esp32p4}"

# Source the ESP-IDF environment only when idf.py is not already available.
if ! command -v idf.py >/dev/null 2>&1; then
    [ -f "$IDF_EXPORT" ] || die "idf.py not found and ESP-IDF export script is missing: $IDF_EXPORT"
    # shellcheck disable=SC1090
    . "$IDF_EXPORT"
fi
command -v idf.py >/dev/null 2>&1 || die "idf.py is unavailable. Source ESP-IDF export.sh first."

cd "$SCRIPT_DIR"

if [ "$DO_BUILD" -eq 1 ]; then
    CURRENT_TARGET="$(target_from_sdkconfig)"
    if [ "$CURRENT_TARGET" = "$TARGET" ]; then
        echo "[1/3] ESP-IDF target already selected: $TARGET"
    else
        echo "[1/3] Selecting ESP-IDF target: $TARGET"
        idf.py set-target "$TARGET"
    fi
    echo "[2/3] Building firmware"
    idf.py build
else
    echo "Skipping build."
fi

if [ "$DO_FLASH" -eq 0 ]; then
    if [ "$DO_MONITOR" -eq 1 ]; then
        [ -n "$PORT" ] || detect_port
        check_port_available
        check_monitor_tty
        exec idf.py -p "$PORT" -b "$MONITOR_BAUD" monitor
    fi
    echo "Build complete."
    exit 0
fi

[ -f "$SCRIPT_DIR/build/racesense.bin" ] || die "Missing build/racesense.bin. Run without --no-build first."
[ -n "$PORT" ] || detect_port
check_port_available

if [ "$DO_MONITOR" -eq 1 ]; then
    check_monitor_tty
fi

confirm_flash

echo "[3/3] Flashing $PORT"
if [ "$DO_MONITOR" -eq 1 ]; then
    idf.py -p "$PORT" -b "$FLASH_BAUD" flash
    exec idf.py -p "$PORT" -b "$MONITOR_BAUD" monitor
else
    idf.py -p "$PORT" -b "$FLASH_BAUD" flash
    echo "Flash complete."
fi
