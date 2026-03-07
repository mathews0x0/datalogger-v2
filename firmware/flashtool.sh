#!/bin/bash
# ============================================================================
# RS-CORE UNIFIED FLASHTOOL
# ============================================================================
# Interactive utility for managing ESP32 MicroPython deployment.
# Combines functionality of firstFlash.sh, deploy.sh, and sync_drivers.sh
# ============================================================================

# --- Configuration ---
BAUD="460800"
FIRMWARE_BIN="esp32s3-micropython.bin"
BLINK_SRC="../hardware/workbench/blink_simple.py"
FULL_TEST_SRC="../hardware/workbench/full_system_test.py"

# --- Color Codes ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# --- 1. Find Tools ---
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
if [[ "$ESPTOOL_CMD" == *"esptool"* && ! -x "$ESPTOOL_CMD" ]]; then
    ESPTOOL_CMD=$(find_tool esptool.py)
fi

# --- 2. Port Management ---
detect_port() {
    echo -ne "${CYAN}Detecting Port... ${NC}"
    PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)
    if [ -z "$PORT" ]; then
        # Fallback to general serial ports
        PORT=$(ls /dev/ttyUSB* /dev/tty.usbserial* /dev/tty.usbmodem* 2>/dev/null | head -n 1)
    fi

    if [ -z "$PORT" ]; then
        echo -e "${RED}FAILED${NC}"
        echo "No ESP32-S3 detected. Check USB connection."
        exit 1
    fi
    echo -e "${GREEN}FOUND: $PORT${NC}"
}

free_port() {
    echo -e "${YELLOW}Freeing serial port...${NC}"
    PIDS=$(lsof -t "$PORT" 2>/dev/null)
    if [ ! -z "$PIDS" ]; then
        kill -9 $PIDS 2>/dev/null
        sleep 1
    fi
    pkill -9 mpremote 2>/dev/null
}

# --- 3. Core Actions ---
do_wipe() {
    echo -e "${YELLOW}Erasing Flash...${NC}"
    $ESPTOOL_CMD --chip esp32s3 --port "$PORT" --before default-reset --after hard-reset erase-flash
    if [ $? -ne 0 ]; then echo -e "${RED}Erase failed!${NC}"; exit 1; fi
}

do_flash_os() {
    echo -e "${YELLOW}Flashing MicroPython ($FIRMWARE_BIN)...${NC}"
    if [ ! -f "$FIRMWARE_BIN" ]; then
        echo -e "${RED}ERROR: $FIRMWARE_BIN not found in $(pwd)${NC}"
        exit 1
    fi
    $ESPTOOL_CMD --chip esp32s3 --port "$PORT" --baud $BAUD --before default-reset --after hard-reset write-flash -z 0 "$FIRMWARE_BIN"
    if [ $? -ne 0 ]; then echo -e "${RED}Flash failed!${NC}"; exit 1; fi
    
    echo -e "${YELLOW}Because this board uses Native USB, auto-reset via RTS fails.${NC}"
    echo -e "${YELLOW}Please manually press the RESET/EN button on the ESP32 now!${NC}"
    read -p "Press Enter to continue once you have reset the board..."
    echo -e "${GREEN}Wait 5s for USB re-enumeration...${NC}"
    sleep 5
    # Re-detect port after boot
    PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)
}

do_sync_source() {
    echo -e "${YELLOW}Syncing Firmware Source Files...${NC}"
    
    # Create necessary filesystem structure
    $MPREMOTE_CMD connect "$PORT" mkdir /data 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /data/metadata 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /sd 2>/dev/null

    # Sync root files
    echo -e "${CYAN}Copying Python root files...${NC}"
    for f in *.py; do
        if [[ "$f" != "reset.py" && "$f" != "secrets.py" ]]; then
            echo "Pushing $f..."
            $MPREMOTE_CMD connect "$PORT" cp "$f" : 
        fi
    done
    
    # Sync directories recursively
    if [ -d "lib" ]; then
        echo -e "${CYAN}Syncing lib/...${NC}"
        $MPREMOTE_CMD connect "$PORT" cp -r lib :
    fi
    
    if [ -d "drivers" ]; then
        echo -e "${CYAN}Syncing drivers/...${NC}"
        $MPREMOTE_CMD connect "$PORT" cp -r drivers :
    fi
    echo -e "${GREEN}Source Sync Complete!${NC}"
    
    # Install BMI270 config file library (required for IMU initialization)
    echo -e "${MAGENTA}Installing BMI270 config library (local)...${NC}"
    $MPREMOTE_CMD connect "$PORT" mkdir /lib/micropython_bmi270 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" cp -r lib/micropython_bmi270 :/lib/micropython_bmi270
    echo -e "${GREEN}BMI270 Library Installed!${NC}"
}

do_sync_drivers_only() {
    echo -e "${YELLOW}Synchronizing drivers to ESP32 root...${NC}"
    DRIVERS=("bmi323.py" "bmi270.py" "gps.py" "sdcard.py")
    for driver in "${DRIVERS[@]}"; do
        if [ -f "drivers/$driver" ]; then
            echo "Pushing $driver..."
            $MPREMOTE_CMD connect "$PORT" cp "drivers/$driver" : 
        else
            echo -e "${RED}Warning: drivers/$driver not found!${NC}"
        fi
    done
    echo -e "${GREEN}Drivers Sync Complete!${NC}"
}

do_deploy_test() {
    local src_file=$1
    local test_name=$2
    
    echo -e "${YELLOW}Deploying $test_name as main.py...${NC}"
    if [ ! -f "$src_file" ]; then
        echo -e "${RED}ERROR: $src_file not found!${NC}"
        exit 1
    fi

    # Try Soft Reset to clear buffers
    $MPREMOTE_CMD connect "$PORT" soft-reset 2>/dev/null
    sleep 2
    
    $MPREMOTE_CMD connect "$PORT" cp "$src_file" :main.py
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully deployed main.py!${NC}"
        # Install BMI270 config file library if deploying full system test
        if [[ "$src_file" == *"full_system_test"* ]]; then
            echo -e "${MAGENTA}Installing BMI270 config library (local)...${NC}"
            $MPREMOTE_CMD connect "$PORT" mkdir /lib/micropython_bmi270 2>/dev/null
            $MPREMOTE_CMD connect "$PORT" cp -r lib/micropython_bmi270 :/lib/micropython_bmi270
            echo -e "${GREEN}BMI270 Library Installed!${NC}"
        fi
        echo -e "${CYAN}Rebooting device...${NC}"
        $MPREMOTE_CMD connect "$PORT" reset
    else
        echo -e "${RED}Failed to deploy $test_name.${NC}"
    fi
}


# --- 4. Interactive Menu ---
show_menu() {
    clear
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}       RS-CORE UNIFIED FLASHTOOL          ${NC}"
    echo -e "${GREEN}==========================================${NC}"
    echo "1) First Setup (Wipe + OS + Flash Blink script)"
    echo "2) Hardware Test (Wipe + OS + Flash Full System Test)"
    echo "3) Clean Sync (Delete all firmware on device & sync latest)"
    echo "4) Nuke Sync (Full Wipe + Install OS + Sync latest)"
    echo "5) Exit"
    echo -e "${GREEN}==========================================${NC}"
    echo -ne "Select an option [1-5]: "
}

main() {
    while true; do
        show_menu
        read choice
        
        # We need port for all options except 5
        if [[ "$choice" != "5" ]]; then
            echo ""
            detect_port
            free_port
            # Try to force bootloader state if OS or Wipe selected
            if [[ "$choice" == "1" || "$choice" == "2" || "$choice" == "4" ]]; then
                echo -e "${YELLOW}Triggering Bootloader...${NC}"
                $MPREMOTE_CMD connect "$PORT" exec "import machine; machine.bootloader()" 2>/dev/null
                sleep 2
            fi
        fi

        case $choice in
            1)
                do_wipe
                do_flash_os
                do_deploy_test "$BLINK_SRC" "Blink"
                echo -e "${GREEN}First Setup Complete!${NC}"
                read -p "Press enter to return to menu..."
                ;;
            2)
                do_wipe
                do_flash_os
                do_deploy_test "$FULL_TEST_SRC" "Full System Test"
                echo -e "${GREEN}Hardware Test Setup Complete!${NC}"
                read -p "Press enter to return to menu..."
                ;;
            3)
                # For a clean sync, we wipe the python files using mpremote instead of erasing the whole OS partition
                echo -e "${YELLOW}Deleting existing firmware files...${NC}"
                $MPREMOTE_CMD connect "$PORT" exec "import os; 
try:
    def rm(d):
        try:
            if os.stat(d)[0] & 0x4000:
                for f in os.listdir(d): rm(d+'/'+f)
                os.rmdir(d)
            else:
                os.remove(d)
        except: pass
    for f in os.listdir(): rm(f)
except: pass"
                do_sync_source
                read -p "Press enter to return to menu..."
                ;;
            4)
                do_wipe
                do_flash_os
                do_sync_source
                echo -e "${GREEN}Nuke Sync Complete!${NC}"
                read -p "Press enter to return to menu..."
                ;;
            5)
                echo "Exiting."
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option.${NC}"
                sleep 1
                ;;
        esac
    done
}

# Run the menu
main
