#!/bin/bash
# ============================================================================
# RS-CORE UNIFIED FLASHTOOL
# ============================================================================
# Interactive utility for managing ESP32 MicroPython deployment.
# Combines functionality of firstFlash.sh, deploy.sh, and sync_drivers.sh
# ============================================================================

# --- Configuration ---
BAUD="460800"
PREFERRED_FIRMWARE_BIN="esp32s3-micropython-psram-oct.bin"
BLINK_SRC="../hardware/workbench/blink_simple.py"
FULL_TEST_SRC="../hardware/workbench/full_system_test.py"
PSRAM_PROBE_SRC="tools/psram_probe.py"
DEVICE_MANIFEST_PATH="/data/metadata/firmware_manifest.txt"

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

resolve_firmware_bin() {
    local candidates=(
        "$PREFERRED_FIRMWARE_BIN"
        "esp32s3-micropython.bin"
        "micropython.bin"
    )
    for candidate in "${candidates[@]}"; do
        if [ -f "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# --- 3. Core Actions ---
do_wipe() {
    echo -e "${YELLOW}Erasing Flash...${NC}"
    $ESPTOOL_CMD --chip esp32s3 --port "$PORT" --before default-reset --after hard-reset erase-flash
    if [ $? -ne 0 ]; then echo -e "${RED}Erase failed!${NC}"; exit 1; fi
}

do_flash_os() {
    local firmware_bin
    firmware_bin=$(resolve_firmware_bin)
    if [ -z "$firmware_bin" ]; then
        echo -e "${RED}ERROR: No MicroPython firmware binary found in $(pwd)${NC}"
        echo -e "${YELLOW}Expected preferred local firmware: $PREFERRED_FIRMWARE_BIN${NC}"
        echo -e "${YELLOW}Accepted fallback local firmware names: esp32s3-micropython.bin, micropython.bin${NC}"
        exit 1
    fi
    echo -e "${YELLOW}Flashing MicroPython ($firmware_bin)...${NC}"
    if [ "$firmware_bin" != "$PREFERRED_FIRMWARE_BIN" ]; then
        echo -e "${MAGENTA}Warning: using fallback firmware image.${NC}"
        echo -e "${MAGENTA}For ESP32-S3-WROOM-1-N16R8, prefer: $PREFERRED_FIRMWARE_BIN${NC}"
    fi
    $ESPTOOL_CMD --chip esp32s3 --port "$PORT" --baud $BAUD --before default-reset --after hard-reset write-flash -z 0 "$firmware_bin"
    if [ $? -ne 0 ]; then echo -e "${RED}Flash failed!${NC}"; exit 1; fi
    
    echo -e "${YELLOW}Because this board uses Native USB, auto-reset via RTS fails.${NC}"
    echo -e "${YELLOW}Please manually press the RESET/EN button on the ESP32 now!${NC}"
    read -p "Press Enter to continue once you have reset the board..."
    echo -e "${GREEN}Wait 5s for USB re-enumeration...${NC}"
    sleep 5
    # Re-detect port after boot
    PORT=$(ls /dev/cu.usbmodem* /dev/tty.usbmodem* 2>/dev/null | head -n 1)
}

do_psram_probe() {
    if [ ! -f "$PSRAM_PROBE_SRC" ]; then
        echo -e "${RED}ERROR: $PSRAM_PROBE_SRC not found${NC}"
        exit 1
    fi
    echo -e "${CYAN}Running PSRAM probe on device...${NC}"
    $MPREMOTE_CMD connect "$PORT" run "$PSRAM_PROBE_SRC"
}

local_file_hash() {
    local file_path="$1"
    python3 - "$file_path" <<'PY'
import sys
path = sys.argv[1]
h = 2166136261
size = 0
with open(path, "rb") as f:
    while True:
        chunk = f.read(4096)
        if not chunk:
            break
        size += len(chunk)
        for b in chunk:
            h = ((h ^ b) * 16777619) & 0xFFFFFFFF
print(f"{h:08x}:{size}")
PY
}

remove_remote_path() {
    local remote_path="$1"
    $MPREMOTE_CMD connect "$PORT" exec "import os
path='${remote_path}'
try:
    mode = os.stat(path)[0]
    if mode & 0x4000:
        def rmtree(d):
            try:
                mode = os.stat(d)[0]
                if mode & 0x4000:
                    for name in os.listdir(d):
                        child = d.rstrip('/') + '/' + name if d != '/' else '/' + name
                        rmtree(child)
                    os.rmdir(d)
                else:
                    os.remove(d)
            except Exception:
                pass
        rmtree(path)
    else:
        os.remove(path)
except Exception:
    pass" >/dev/null 2>&1
}

build_local_sync_manifest() {
    local manifest_path="$1"
    : > "$manifest_path"

    for f in *.py; do
        [ -e "$f" ] || continue
        [[ "$f" == "reset.py" || "$f" == "secrets.py" ]] && continue
        printf "%s|/%s|%s\n" "$f" "$f" "$(local_file_hash "$f")" >> "$manifest_path"
    done

    if [ -d "lib" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] || continue
            printf "%s|/%s|%s\n" "$f" "$f" "$(local_file_hash "$f")" >> "$manifest_path"
        done < <(find lib -type f \( -name '*.py' -o -name '*.raw' \) ! -path '*/__pycache__/*' | sort)
    fi

    if [ -d "drivers" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] || continue
            printf "%s|/%s|%s\n" "$f" "$f" "$(local_file_hash "$f")" >> "$manifest_path"
        done < <(find drivers -type f -name '*.py' ! -path '*/__pycache__/*' | sort)
    fi
}

scan_remote_sync_manifest() {
    $MPREMOTE_CMD connect "$PORT" exec "import os
def emit(path):
    if path.endswith('.py') or path.endswith('.raw'):
        try:
            f=open(path,'rb')
            h=2166136261
            size=0
            while True:
                chunk=f.read(4096)
                if not chunk:
                    break
                size += len(chunk)
                for b in chunk:
                    h=((h ^ b) * 16777619) & 0xffffffff
            f.close()
            print('%s|%08x:%d' % (path, h, size))
        except Exception:
            pass
def walk(path):
    try:
        mode = os.stat(path)[0]
    except Exception:
        return
    if mode & 0x4000:
        try:
            names = os.listdir(path)
        except Exception:
            names = []
        for name in names:
            child = path.rstrip('/') + '/' + name if path != '/' else '/' + name
            walk(child)
    else:
        emit(path)
try:
    names = os.listdir('/')
except Exception:
    names = []
for name in names:
    path = '/' + name
    if name in ('lib', 'drivers'):
        walk(path)
    elif name.endswith('.py'):
        emit(path)" 2>/dev/null | tr -d '\r'
}

fetch_device_manifest() {
    local out_path="$1"
    rm -f "$out_path"
    $MPREMOTE_CMD connect "$PORT" cp ":${DEVICE_MANIFEST_PATH#/}" "$out_path" >/dev/null 2>&1
    return $?
}

write_device_manifest() {
    local manifest_path="$1"
    local normalized_manifest
    normalized_manifest=$(mktemp)
    while IFS='|' read -r col1 col2 col3; do
        [ -n "$col1" ] || continue
        if [ -n "$col3" ]; then
            printf "%s|%s\n" "$col2" "$col3" >> "$normalized_manifest"
        else
            printf "%s|%s\n" "$col1" "$col2" >> "$normalized_manifest"
        fi
    done < "$manifest_path"
    remove_remote_path "$DEVICE_MANIFEST_PATH"
    $MPREMOTE_CMD connect "$PORT" cp "$normalized_manifest" ":${DEVICE_MANIFEST_PATH#/}" >/dev/null 2>&1
    rm -f "$normalized_manifest"
}

ensure_remote_dirs_from_manifest() {
    local manifest_path="$1"
    local dir_list_file
    dir_list_file=$(mktemp)
    {
        printf "/lib\n/drivers\n/data\n/data/metadata\n/sd\n"
        cut -d'|' -f2 "$manifest_path" | while IFS= read -r remote_path; do
            [ -n "$remote_path" ] || continue
            dirname "$remote_path"
        done
    } | awk 'NF && !seen[$0]++' > "$dir_list_file"

    echo -e "${CYAN}Ensuring remote directories ($(wc -l < "$dir_list_file" | tr -d ' '))...${NC}"
    {
        echo "import os"
        echo "dirs = ["
        while IFS= read -r dir_path; do
            [ -n "$dir_path" ] || continue
            printf "    %s,\n" "'$dir_path'"
        done < "$dir_list_file"
        cat <<'PY'
]
for d in dirs:
    if not d or d == '/':
        continue
    parts = [p for p in d.split('/') if p]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            os.mkdir(current)
        except Exception:
            pass
PY
    } > "$dir_list_file.py"
    $MPREMOTE_CMD connect "$PORT" exec "$(cat "$dir_list_file.py")" >/dev/null 2>&1 || true
    rm -f "$dir_list_file" "$dir_list_file.py"
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
    for dir in lib/*; do
        [ -d "$dir" ] || continue
        [[ "$dir" == *"__pycache__"* ]] && continue
        $MPREMOTE_CMD connect "$PORT" mkdir "/$dir" 2>/dev/null
    done

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
        for f in lib/*.raw; do
            [ -e "$f" ] || continue
            $MPREMOTE_CMD connect "$PORT" cp "$f" :lib/
        done
        for f in lib/*/*.py; do
            [ -e "$f" ] || continue
            [[ "$f" == *"__pycache__"* ]] && continue
            $MPREMOTE_CMD connect "$PORT" cp "$f" ":$f"
        done
    fi
    
    if [ -d "drivers" ]; then
        echo -e "${CYAN}Syncing drivers/...${NC}"
        for f in drivers/*.py; do
            [ -e "$f" ] || continue
            $MPREMOTE_CMD connect "$PORT" cp "$f" :drivers/
        done
    fi
    local manifest_file
    manifest_file=$(mktemp)
    build_local_sync_manifest "$manifest_file"
    write_device_manifest "$manifest_file"
    rm -f "$manifest_file"
    
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
    echo -e "${CYAN}Resetting device...${NC}"
    $MPREMOTE_CMD connect "$PORT" reset >/dev/null 2>&1 || true
}

do_simple_sync() {
    echo -e "${YELLOW}Simple Sync (checksum-based selective replace)...${NC}"
    local manifest_file
    local remote_manifest_file
    local next_manifest_file
    manifest_file=$(mktemp)
    remote_manifest_file=$(mktemp)
    next_manifest_file=$(mktemp)

    echo -e "${CYAN}Building local manifest...${NC}"
    build_local_sync_manifest "$manifest_file"
    local manifest_count
    manifest_count=$(wc -l < "$manifest_file" | tr -d ' ')
    echo -e "${GREEN}Local manifest ready.${NC} files=$manifest_count"
    ensure_remote_dirs_from_manifest "$manifest_file"
    echo -e "${CYAN}Reading device manifest...${NC}"
    if fetch_device_manifest "$remote_manifest_file"; then
        echo -e "${GREEN}Device manifest loaded.${NC}"
    else
        echo -e "${MAGENTA}Device manifest missing. Running clean sync to seed manifest...${NC}"
        rm -f "$manifest_file" "$remote_manifest_file" "$next_manifest_file"
        do_sync_source
        return
    fi

    local removed=0
    local copied=0
    local skipped=0
    local stale_count=0
    local changed_count=0

    : > "$next_manifest_file"

    echo -e "${CYAN}Comparing manifests...${NC}"
    while IFS='|' read -r remote_path remote_hash; do
        [ -n "$remote_path" ] || continue
        if ! awk -F'|' -v target="$remote_path" '$2 == target { found=1; exit } END { exit(found ? 0 : 1) }' "$manifest_file"; then
            stale_count=$((stale_count + 1))
        fi
    done < "$remote_manifest_file"

    while IFS='|' read -r local_path remote_path local_hash; do
        [ -n "$local_path" ] || continue
        remote_hash=$(awk -F'|' -v target="$remote_path" '$1 == target { print $2; exit }' "$remote_manifest_file")
        if [ -z "$remote_hash" ]; then
            remote_hash="MISSING"
        fi
        if [ "$local_hash" = "$remote_hash" ]; then
            skipped=$((skipped + 1))
            printf "%s|%s\n" "$remote_path" "$local_hash" >> "$next_manifest_file"
            continue
        fi
        changed_count=$((changed_count + 1))
    done < "$manifest_file"

    echo -e "${GREEN}Diff summary:${NC} changed=$changed_count stale=$stale_count unchanged=$skipped"

    if [ "$stale_count" -gt 0 ]; then
        echo -e "${CYAN}Removing stale remote files...${NC}"
        while IFS='|' read -r remote_path remote_hash; do
            [ -n "$remote_path" ] || continue
            if ! awk -F'|' -v target="$remote_path" '$2 == target { found=1; exit } END { exit(found ? 0 : 1) }' "$manifest_file"; then
                echo -e "${MAGENTA}Removing stale remote file:${NC} $remote_path"
                remove_remote_path "$remote_path"
                removed=$((removed + 1))
            fi
        done < "$remote_manifest_file"
    fi

    if [ "$changed_count" -gt 0 ]; then
        echo -e "${CYAN}Copying changed files...${NC}"
    fi

    while IFS='|' read -r local_path remote_path local_hash; do
        [ -n "$local_path" ] || continue
        remote_hash=$(awk -F'|' -v target="$remote_path" '$1 == target { print $2; exit }' "$remote_manifest_file")
        if [ -z "$remote_hash" ]; then
            remote_hash="MISSING"
        fi
        if [ "$local_hash" = "$remote_hash" ]; then
            continue
        fi
        if [ "$remote_hash" != "MISSING" ]; then
            echo -e "${YELLOW}Replacing changed file:${NC} $remote_path"
            remove_remote_path "$remote_path"
            removed=$((removed + 1))
        else
            echo -e "${CYAN}Copying new file:${NC} $remote_path"
        fi
        if [[ "$remote_path" == /* ]]; then
            $MPREMOTE_CMD connect "$PORT" cp "$local_path" ":${remote_path#/}"
        else
            $MPREMOTE_CMD connect "$PORT" cp "$local_path" ":$remote_path"
        fi
        if [ $? -eq 0 ]; then
            copied=$((copied + 1))
            printf "%s|%s\n" "$remote_path" "$local_hash" >> "$next_manifest_file"
        else
            echo -e "${RED}Copy failed:${NC} $local_path -> $remote_path"
        fi
    done < "$manifest_file"

    write_device_manifest "$next_manifest_file"
    rm -f "$manifest_file" "$remote_manifest_file" "$next_manifest_file"
    echo -e "${GREEN}Simple Sync Complete!${NC} copied=$copied removed=$removed skipped=$skipped"
    echo -e "${CYAN}Resetting device...${NC}"
    $MPREMOTE_CMD connect "$PORT" reset >/dev/null 2>&1 || true
}

do_sync_drivers_only() {
    echo -e "${YELLOW}Synchronizing drivers to /drivers on ESP32...${NC}"
    $MPREMOTE_CMD connect "$PORT" mkdir /drivers 2>/dev/null || true
    for f in drivers/*.py; do
        if [ -e "$f" ]; then
            echo "Pushing $(basename "$f")..."
            $MPREMOTE_CMD connect "$PORT" cp "$f" :drivers/
        else
            echo -e "${RED}Warning: no driver files found!${NC}"
            break
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
        
        if [[ "$src_file" == *"full_system_test"* ]]; then
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

make_numbered_backup_dir() {
    local backup_root="$1"
    local date_prefix
    local next_num
    local candidate

    mkdir -p "$backup_root"
    date_prefix=$(date +"%Y-%m-%d")
    next_num=1

    while :; do
        candidate=$(printf "%s/%s_%03d" "$backup_root" "$date_prefix" "$next_num")
        if [ ! -e "$candidate" ]; then
            mkdir -p "$candidate"
            echo "$candidate"
            return 0
        fi
        next_num=$((next_num + 1))
    done
}

list_pending_device_session_paths() {
    $MPREMOTE_CMD connect "$PORT" exec "import os
dirs = ('/sd/sessions', '/data/learning', '/sessions')
seen = []
for directory in dirs:
    try:
        names = os.listdir(directory)
    except Exception:
        continue
    for name in names:
        if not name.endswith('.csv'):
            continue
        path = directory.rstrip('/') + '/' + name
        duplicate = False
        for existing in seen:
            if existing == path:
                duplicate = True
                break
        if duplicate:
            continue
        seen.append(path)
        print(path)" 2>/dev/null | tr -d '\r'
}

do_copy_to_backup_sessions() {
    local backup_root="/Users/mj/Documents/backupsessions"
    local backup_dir
    local copied_count=0
    local failed_count=0
    local copied_any=0

    backup_dir=$(make_numbered_backup_dir "$backup_root") || {
        echo -e "${RED}Failed to create backup directory under $backup_root${NC}"
        return 1
    }

    echo -e "${YELLOW}Copying pending device session files from SD + flash to $backup_dir...${NC}"

    while IFS= read -r remote_path; do
        [ -n "$remote_path" ] || continue
        local_name=${remote_path##*/}
        echo -e "${CYAN}Copying $remote_path...${NC}"
        if $MPREMOTE_CMD connect "$PORT" cp ":${remote_path#/}" "$backup_dir/$local_name"; then
            copied_count=$((copied_count + 1))
            copied_any=1
        else
            echo -e "${RED}Failed to copy $remote_path${NC}"
            failed_count=$((failed_count + 1))
        fi
    done < <(list_pending_device_session_paths)

    if [ "$copied_any" -eq 0 ] && [ "$failed_count" -eq 0 ]; then
        rmdir "$backup_dir" 2>/dev/null || true
        echo -e "${YELLOW}No non-archived device session files found. Nothing copied.${NC}"
        return 0
    fi

    if [ "$failed_count" -eq 0 ]; then
        echo -e "${GREEN}Copied $copied_count file(s) to $backup_dir${NC}"
    else
        echo -e "${YELLOW}Copy finished with issues: $copied_count copied, $failed_count failed. Files on device were not modified.${NC}"
    fi
}

do_view_boot_history() {
    echo -e "${CYAN}Current Boot State:${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "
try:
    f=open('/data/metadata/boot_state.json','r')
    print(f.read())
    f.close()
except Exception as e:
    print('  (boot_state.json not found)')
"

    echo ""
    echo -e "${CYAN}Recent Boot Failure History:${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "
try:
    f=open('/data/metadata/boot_history.json','r')
    print(f.read())
    f.close()
except Exception as e:
    print('  (boot_history.json not found)')
"
}

do_reset_display_calibration() {
    echo -e "${YELLOW}Removing saved display/touch calibration files...${NC}"
    $MPREMOTE_CMD connect "$PORT" exec "import os
for path in (
    '/data/metadata/display.json',
    '/data/metadata/touch.json',
):
    try:
        os.remove(path)
        print('removed', path)
    except Exception:
        print('missing', path)
" 
    echo -e "${CYAN}Resetting device...${NC}"
    $MPREMOTE_CMD connect "$PORT" reset >/dev/null 2>&1 || true
    echo -e "${GREEN}Calibration metadata cleared. Next boot will re-enter display/touch calibration.${NC}"
}


# --- 5. Interactive Menu ---
show_menu() {
    clear
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}       RS-CORE UNIFIED FLASHTOOL          ${NC}"
    echo -e "${GREEN}==========================================${NC}"
    echo "1) First Setup (Wipe + OS + Flash Blink script)"
    echo "2) Clean Sync (Replace firmware code, keep user data)"
    echo "3) Simple Sync (Replace only changed firmware files)"
    echo "4) Nuke Sync (Full Wipe + Install OS + Sync latest)"
    echo "5) Backup & Purge Device Data (Internal flash only)"
    echo "6) Copy to backupSessions (Non-archived SD + flash files)"
    echo "7) View Boot Diagnostics"
    echo "8) Reset Display Calibration"
    echo "9) Run PSRAM Probe"
    echo "10) Exit"
    echo -e "${GREEN}==========================================${NC}"
    echo -ne "Select an option [1-10]: "
}

main() {
    show_menu
    read choice
    
    # We need a port for all menu actions except exit
    if [[ "$choice" != "10" ]]; then
        echo ""
        detect_port
        free_port
        # Only force ROM bootloader for actions that actually reflash the OS.
        if [[ "$choice" == "1" || "$choice" == "4" ]]; then
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
            do_simple_sync
            echo -e "${GREEN}Simple Sync Complete!${NC}"
            ;;
        4)
            do_wipe
            do_flash_os
            do_sync_source
            echo -e "${GREEN}Nuke Sync Complete!${NC}"
            ;;
        5)
            do_backup
            ;;
        6)
            do_copy_to_backup_sessions
            ;;
        7)
            do_view_boot_history
            ;;
        8)
            do_reset_display_calibration
            ;;
        9)
            do_psram_probe
            ;;
        10)
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
