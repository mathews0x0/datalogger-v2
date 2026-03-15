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

# Robust mpremote selection (avoid broken versions)
if [[ "$MPREMOTE_CMD" == *"mpremote"* ]]; then
    # Prefer Python 3.9 version if it exists, as 3.14 seems broken in this environment
    if [ -f "/Users/mj/Library/Python/3.9/bin/mpremote" ]; then
        MPREMOTE_CMD="/Users/mj/Library/Python/3.9/bin/mpremote"
    fi
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
    
    # Step 1: Delete firmware code only (preserves /data/ user data: sessions, tracks, device config)
    echo -e "${YELLOW}Wiping firmware code (keeping user data in /data/)...${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "import os
try:
    # Remove Python files in root (firmware code)
    for f in os.listdir('/'):
        if f.endswith('.py'):
            try: os.remove('/' + f)
            except: pass
    # Remove lib/ and drivers/ directories (firmware code)
    def rmtree(d):
        try:
            if os.stat(d)[0] & 0x4000:
                for f in os.listdir(d): rmtree(d+'/'+f)
                os.rmdir(d)
            else:
                os.remove(d)
        except: pass
    for d in ['/lib', '/drivers']:
        try: rmtree(d)
        except: pass
except: pass"
    sleep 1
    
    # Step 2: Create necessary filesystem structure
    $MPREMOTE_CMD connect "$PORT" mkdir /lib 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /drivers 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /data 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /data/metadata 2>/dev/null
    $MPREMOTE_CMD connect "$PORT" mkdir /sd 2>/dev/null

    # Step 3: Push all files fresh
    echo -e "${CYAN}Copying Python root files...${NC}"
    for f in *.py; do
        if [[ "$f" != "reset.py" && "$f" != "secrets.py" ]]; then
            echo "Pushing $f..."
            $MPREMOTE_CMD connect "$PORT" cp "$f" : 
        fi
    done
    
    if [ -d "lib" ]; then
        echo -e "${CYAN}Syncing lib/...${NC}"
        # Copy file by file to avoid __pycache__
        for f in lib/*.py; do
            [ -e "$f" ] || continue
            $MPREMOTE_CMD connect "$PORT" cp "$f" :lib/
        done
    fi
    
    if [ -d "drivers" ]; then
        echo -e "${CYAN}Syncing drivers/...${NC}"
        # Explicit driver list to exclude bmi270 and __pycache__
        DRIVERS_LIST=("bmi323.py" "gps.py" "sdcard.py")
        for driver in "${DRIVERS_LIST[@]}"; do
            if [ -f "drivers/$driver" ]; then
                $MPREMOTE_CMD connect "$PORT" cp "drivers/$driver" :drivers/
            fi
        done
    fi
    
    # (BMI270 library sync removed as part of BMI323 switch)
    
    # Show saved device config (WiFi creds + token)
    echo -e "${CYAN}Device Config:${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "
try:
    f=open('/data/metadata/device.json','r');print(f.read());f.close()
except:
    print('  (no device.json found — first-time setup needed)')
"
    
    # Show saved active track + TBL
    echo -e "${CYAN}Active Track:${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "
try:
    import json
    f=open('/data/metadata/track.json','r')
    d=json.load(f); f.close()
    name=d.get('track_name') or d.get('name','Unknown')
    tbl=d.get('tbl',{})
    print(f'  Track: {name}')
    if tbl and isinstance(tbl, dict):
        # Only try to print numeric indices
        for k in sorted(tbl.keys()):
            try:
                val = tbl[k]
                if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.','',1).isdigit()):
                    print(f'  S{int(k)+1}: {float(val):.3f}s')
            except: pass
    else:
        print('  (no TBL data)')
except Exception as e:
    print('  (no track.json found or invalid format)')
"

    echo -e "${GREEN}Source Sync Complete!${NC}"
}

do_sync_drivers_only() {
    echo -e "${YELLOW}Synchronizing drivers to ESP32 root...${NC}"
    DRIVERS=("bmi323.py" "gps.py" "sdcard.py")
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

    # Wipe python files like in Clean Sync to cut through busy loops
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

    sleep 1

    # Copy the test file as main
    $MPREMOTE_CMD connect "$PORT" cp "$src_file" :main.py
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully deployed main.py!${NC}"
        
        sleep 1 # Wait for USB to stabilize after file write
        
        # Install BMI270 config file library if deploying full system test
        if [[ "$src_file" == *"full_system_test"* ]]; then
            # BMI270 library install removed
            
            # Also deploy the neopixel driver just in case the OS wipe killed it
            echo -e "${MAGENTA}Ensuring neopixel library is present...${NC}"
            $MPREMOTE_CMD connect "$PORT" cp "neopixel.py" : 2>/dev/null || true
        fi
        
        echo -e "${CYAN}Rebooting device...${NC}"
        $MPREMOTE_CMD connect "$PORT" reset
    else
        echo -e "${RED}Failed to deploy $test_name.${NC}"
    fi
}


# --- 4. Backup & Purge ---
do_backup() {
    local backup_root="/Users/mj/Documents/RS-core-flashtool-backups"
    local timestamp=$(date +"%Y-%m-%d_%H%M")
    local backup_dir="$backup_root/$timestamp"

    echo -e "${YELLOW}Initiating Backup to $backup_dir...${NC}"
    mkdir -p "$backup_dir"

    # Step 1: Copy data from device
    echo -e "${CYAN}Copying /data directory...${NC}"
    $MPREMOTE_CMD connect "$PORT" cp -r :data "$backup_dir/"
    local data_status=$?

    echo -e "${CYAN}Checking for crash.log...${NC}"
    $MPREMOTE_CMD connect "$PORT" cp :crash.log "$backup_dir/" 2>/dev/null
    # crash.log might not exist, so we don't strictly fail on it

    if [ $data_status -eq 0 ] && [ -d "$backup_dir/data" ]; then
        echo -e "${GREEN}Backup successful! Verified at $backup_dir${NC}"
        
        # Step 2: Delete from device (Selective Purge)
        echo -e "${RED}Purging backed-up data (keeping /data/metadata)...${NC}"
        $MPREMOTE_CMD connect "$PORT" exec "import os
def rmtree(d):
    try:
        if os.stat(d)[0] & 0x4000:
            for f in os.listdir(d): rmtree(d+'/'+f)
            os.rmdir(d)
        else:
            os.remove(d)
    except: pass

# Delete everything in /data EXCEPT metadata
try:
    for f in os.listdir('/data'):
        if f != 'metadata':
            rmtree('/data/' + f)
except: pass

# Delete top-level crash.log
try: os.remove('/crash.log')
except: pass
"
        echo -e "${GREEN}Purge complete. Storage freed (Metadata preserved).${NC}"
    else
        echo -e "${RED}Backup FAILED or verification failed. Device data preserved.${NC}"
        # Cleanup empty directory if it failed
        [ -z "$(ls -A "$backup_dir")" ] && rmdir "$backup_dir"
    fi
}


# --- 5. Interactive Menu ---
show_menu() {
    clear
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}       RS-CORE UNIFIED FLASHTOOL          ${NC}"
    echo -e "${GREEN}==========================================${NC}"
    echo "1) First Setup (Wipe + OS + Flash Blink script)"
    echo "2) Clean Sync (Replace firmware code, keep user data)"
    echo "3) Nuke Sync (Full Wipe + Install OS + Sync latest)"
    echo "4) Backup & Purge Device Data (Internal flash only)"
    echo "5) Exit"
    echo -e "${GREEN}==========================================${NC}"
    echo -ne "Select an option [1-5]: "
}

main() {
    show_menu
    read choice
    
    # We need port for all options except 7
    if [[ "$choice" != "7" ]]; then
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
            ;;
        2)
            # Clean sync: do_sync_source wipes all user files then pushes fresh
            do_sync_source
            echo -e "${GREEN}Clean Sync Complete!${NC}"
            ;;
        3)
            do_wipe
            do_flash_os
            do_sync_source
            echo -e "${GREEN}Nuke Sync Complete!${NC}"
            ;;
        4)
            do_backup
            ;;
        5)
            echo "Exiting."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option.${NC}"
            ;;
    esac
}

# Run the menu
main
