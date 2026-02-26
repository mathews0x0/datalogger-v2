#!/bin/bash
# ============================================================================
# ESP32-S3 FIRST FLASH AUTOMATION
# ============================================================================
#
# DESCRIPTION:
#   Automates the setup of a brand new ESP32-S3 chip.
#   1. Detects Port
#   2. Kills conflicting processes
#   3. Erases Flash
#   4. Installs MicroPython
#   5. Deploys Blink Test as main.py
# ============================================================================

# Configuration
BAUD="460800"
FIRMWARE_BIN="esp32s3-micropython.bin"
BLINK_SRC="../hardware/workbench/blink_simple.py"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}======================================"
echo "  ESP32-S3 FIRST FLASH TOOL"
echo -e "======================================${NC}"

# 1. Find Tools
find_tool() {
    local tool=$1
    local cmd=$(which "$tool" 2>/dev/null)
    if [ -z "$cmd" ]; then
        for path in "$HOME/Library/Python/3.14/bin" "$HOME/Library/Python/3.13/bin" "$HOME/Library/Python/3.12/bin" "$HOME/.local/bin"; do
            if [ -f "$path/$tool" ]; then
                cmd="$path/$tool"
                break
            fi
        done
    fi
    echo "${cmd:-$tool}"
}

MPREMOTE_CMD=$(find_tool mpremote)
ESPTOOL_CMD=$(find_tool esptool)

# 2. Port Detection
echo -ne "${YELLOW}Detecting Port... ${NC}"
PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)

if [ -z "$PORT" ]; then
    echo -e "${RED}FAILED${NC}"
    echo "No ESP32-S3 (usbmodem) detected. Check USB connection."
    exit 1
fi
echo -e "${GREEN}FOUND: $PORT${NC}"

# 3. Kill Competitors
echo -e "${YELLOW}Freeing serial port...${NC}"
PIDS=$(lsof -t "$PORT" 2>/dev/null)
if [ ! -z "$PIDS" ]; then
    kill -9 $PIDS 2>/dev/null
    sleep 1
fi
pkill -9 mpremote 2>/dev/null

# 4. Software Kick (If MicroPython is running)
echo -e "${YELLOW}Attempting to trigger Bootloader via Software...${NC}"
$MPREMOTE_CMD connect "$PORT" exec "import machine; machine.bootloader()" 2>/dev/null
sleep 2

# 5. Nuclear Wipe
echo -e "${YELLOW}Erasing Flash...${NC}"
$ESPTOOL_CMD --chip esp32s3 --port "$PORT" --before default-reset --after hard-reset erase-flash
if [ $? -ne 0 ]; then echo -e "${RED}Erase failed!${NC}"; exit 1; fi

# 6. Flash MicroPython
echo -e "${YELLOW}Flashing MicroPython ($FIRMWARE_BIN)...${NC}"
if [ ! -f "$FIRMWARE_BIN" ]; then
    echo -e "${RED}ERROR: $FIRMWARE_BIN not found in $(pwd)${NC}"
    exit 1
fi
$ESPTOOL_CMD --chip esp32s3 --port "$PORT" --baud $BAUD --before default-reset --after hard-reset write-flash -z 0 "$FIRMWARE_BIN"
if [ $? -ne 0 ]; then echo -e "${RED}Flash failed!${NC}"; exit 1; fi

echo -e "${GREEN}Wait 8s for USB re-enumeration...${NC}"
sleep 8

# 6. Provision Blink
echo -e "${YELLOW}Deploying Blink Code as main.py...${NC}"
if [ ! -f "$BLINK_SRC" ]; then
    echo -e "${RED}ERROR: $BLINK_SRC not found!${NC}"
    exit 1
fi

# Try multiple times with port re-detection if needed
for i in {1..5}; do
    echo "Attempt $i..."
    # Re-detect port in case it changed during reboot (S3 behavior)
    PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)
    if [ -z "$PORT" ]; then
        echo "No port found, waiting..."
        sleep 4
        continue
    fi
    
    # Try a soft-reset first to clear buffers
    $MPREMOTE_CMD connect "$PORT" soft-reset 2>/dev/null
    sleep 2
    
    $MPREMOTE_CMD connect "$PORT" cp "$BLINK_SRC" :main.py
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully deployed main.py!${NC}"
        $MPREMOTE_CMD connect "$PORT" reset
        break
    else
        echo -e "${YELLOW}Connection failed. Toggling port...${NC}"
        # Sometimes killing the port process helps
        PIDS=$(lsof -t "$PORT" 2>/dev/null)
        if [ ! -z "$PIDS" ]; then kill -9 $PIDS 2>/dev/null; fi
        sleep 3
    fi
    
    if [ $i -eq 5 ]; then
        echo -e "${RED}Final attempt failed. You may need to manually run: mpremote cp $BLINK_SRC :main.py${NC}"
    fi
done

echo -e "${GREEN}======================================"
echo "  SETUP COMPLETE!"
echo "  The LED on IO2 should be blinking."
echo -e "======================================${NC}"
