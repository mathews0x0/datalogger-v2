#!/bin/bash
# ============================================================================
# ESP32-S3 DRIVER SYNC TOOL
# ============================================================================

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Find Tools
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

# Port Detection
echo -ne "${YELLOW}Detecting Port... ${NC}"
PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)

if [ -z "$PORT" ]; then
    echo -e "${RED}FAILED${NC}"
    exit 1
fi
echo -e "${GREEN}FOUND: $PORT${NC}"

# Sync Drivers
echo -e "${YELLOW}Synchronizing drivers from firmware/drivers/ to ESP32 root...${NC}"
DRIVERS=("bmi323.py" "bmi270.py" "gps.py" "sdcard.py")

for driver in "${DRIVERS[@]}"; do
    if [ -f "drivers/$driver" ]; then
        echo "Pushing $driver..."
        $MPREMOTE_CMD connect "$PORT" cp "drivers/$driver" : 
    else
        echo -e "${RED}Warning: drivers/$driver not found!${NC}"
    fi
done

echo -e "${GREEN}Sync Complete!${NC}"
