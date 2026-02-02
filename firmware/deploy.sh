#!/bin/bash
# ============================================================================
# ESP32 PRO DEPLOYMENT TOOL
# ============================================================================
#
# DESCRIPTION:
#   A comprehensive utility for managing ESP32 MicroPython deployment.
#   It handles low-level flash management, core firmware installation,
#   dependency management, and source code synchronization.
#
# MAIN FUNCTIONS:
#   - wipe_flash:     Erases the entire flash chip (Nuclear wipe).
#   - flash_firmware: Installs MicroPython OS (micropython.bin) to the device.
#   - install_libs:   Uses 'mpremote mip' to install 3rd party libraries.
#   - sync_source:    Synchronizes local .py files and subdirectories (lib/, drivers/).
#   - kill_serial_users: Automatically frees the serial port from other processes.
#
# FLAGS:
#   --full:  Wipe -> Flash -> Install Libs -> Sync Source (Best for new devices)
#   --wipe:  Erase flash only
#   --flash: Install MicroPython only
#   --libs:  Install dependencies only
#   --sync:  Synchronize code only (Default)
#
# REQUIREMENTS:
#   Requires 'esptool' and 'mpremote' (automatically discovered in Python bin).
# ============================================================================

# Configuration
PORT="/dev/cu.SLAB_USBtoUART"
BAUD="460800"
FIRMWARE_BIN="micropython.bin"
SOURCE_DIR="$(pwd)"

# MicroPython Libraries to install via mip
LIBS=("logging" "requests" "json")

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}======================================"
echo "  ESP32 PRO DEPLOYMENT TOOL"
echo -e "======================================${NC}"

# Find Tools
find_tool() {
    local tool=$1
    local cmd=$(which "$tool" 2>/dev/null)
    if [ -z "$cmd" ]; then
        # Check common Python user bin paths
        for path in "$HOME/Library/Python/3.9/bin" "$HOME/Library/Python/3.10/bin" "$HOME/Library/Python/3.11/bin" "$HOME/.local/bin"; do
            if [ -f "$path/$tool" ]; then
                cmd="$path/$tool"
                break
            fi
        done
    fi
    echo "${cmd:-$tool}"
}

MPREMOTE_CMD=$(find_tool mpremote)
# Try both esptool and esptool.py
ESPTOOL_CMD=$(find_tool esptool)
if [[ "$ESPTOOL_CMD" == "esptool" ]]; then
    ESPTOOL_CMD=$(find_tool esptool.py)
fi

check_port() {
    if [ ! -e "$PORT" ]; then
        echo -e "${RED}ERROR: Port $PORT not found.${NC}"
        ls /dev/cu.*
        exit 1
    fi
}

kill_serial_users() {
    PIDS=$(lsof -t $PORT 2>/dev/null)
    if [ ! -z "$PIDS" ]; then
        echo "Freeing $PORT (Killing PIDs: $PIDS)..."
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
}

wipe_flash() {
    echo -e "${YELLOW}Wiping Flash...${NC}"
    $ESPTOOL_CMD --port $PORT erase_flash
}

flash_firmware() {
    if [ ! -f "$FIRMWARE_BIN" ]; then
        echo -e "${RED}ERROR: $FIRMWARE_BIN not found!${NC}"
        return 1
    fi
    echo -e "${YELLOW}Flashing MicroPython Firmware...${NC}"
    $ESPTOOL_CMD --chip esp32 --port $PORT --baud $BAUD write_flash -z 0x1000 $FIRMWARE_BIN
}

install_libs() {
    echo -e "${YELLOW}Installing MicroPython Libraries...${NC}"
    for lib in "${LIBS[@]}"; do
        echo "Installing $lib..."
        $MPREMOTE_CMD connect $PORT mip install $lib
    done
}

sync_source() {
    echo -e "${YELLOW}Syncing Source Files...${NC}"
    
    # Create necessary filesystem structure
    echo "Creating directories..."
    $MPREMOTE_CMD connect $PORT mkdir /data
    $MPREMOTE_CMD connect $PORT mkdir /data/metadata
    $MPREMOTE_CMD connect $PORT mkdir /sd

    # Sync root files
    for f in *.py; do
        if [[ "$f" != "reset.py" && "$f" != "secrets.py" ]]; then
            echo "Pushing $f..."
            $MPREMOTE_CMD connect $PORT cp $f : 
        fi
    done
    
    # Sync directories recursively
    # Force clean remote directories first to ensure updates are applied
    if [ -d "lib" ]; then
        echo "Syncing lib/ (Force clean)..."
        $MPREMOTE_CMD connect $PORT exec "import os; 
try:
    def rm(d):
        try:
            if os.stat(d)[0] & 0x4000:
                for f in os.listdir(d): rm(d+'/'+f)
                os.rmdir(d)
            else:
                os.remove(d)
        except: pass
    rm('/lib')
except: pass"
        $MPREMOTE_CMD connect $PORT cp -r lib :
    fi
    
    if [ -d "drivers" ]; then
        echo "Syncing drivers/ (Force clean)..."
        $MPREMOTE_CMD connect $PORT exec "import os; 
try:
    def rm(d):
        try:
            if os.stat(d)[0] & 0x4000:
                for f in os.listdir(d): rm(d+'/'+f)
                os.rmdir(d)
            else:
                os.remove(d)
        except: pass
    rm('/drivers')
except: pass"
        $MPREMOTE_CMD connect $PORT cp -r drivers :
    fi
}

show_help() {
    echo "Usage: ./deploy.sh [flag]"
    echo "  --wipe      Erase flash only"
    echo "  --flash     Flash micropython.bin only"
    echo "  --libs      Install libraries via WiFi/mip"
    echo "  --sync      Sync local source files only (Default)"
    echo "  --full      Everything: Wipe -> Flash -> Libs -> Sync"
    echo "  --help      Show this help"
}

# Main Logic
check_port
kill_serial_users

case "$1" in
    --wipe)
        wipe_flash
        ;;
    --flash)
        flash_firmware
        ;;
    --libs)
        echo "No libraries to install (v2 cleanup)"
        ;;
    --sync|"")
        sync_source
        ;;
    --full)
        wipe_flash
        flash_firmware
        echo "Waiting for reboot..."
        sleep 5
        # install_libs # Unused
        sync_source
        ;;
    --help)
        show_help
        ;;
    *)
        echo "Unknown option: $1"
        show_help
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
