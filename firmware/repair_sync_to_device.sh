#!/bin/zsh
set -euo pipefail

PORT="${1:-/dev/cu.usbmodem11401}"
MPREMOTE_CMD="/Users/mj/Library/Python/3.9/bin/mpremote"

cd /Users/mj/Documents/datalogger-v2/firmware

for dir in /lib /drivers /data /data/metadata /sd; do
    "$MPREMOTE_CMD" connect "$PORT" mkdir "$dir" 2>/dev/null || true
done

for f in *.py; do
    if [[ "$f" != "reset.py" && "$f" != "secrets.py" ]]; then
        "$MPREMOTE_CMD" connect "$PORT" cp "$f" :
    fi
done

for f in lib/*.py; do
    [[ -e "$f" ]] || continue
    "$MPREMOTE_CMD" connect "$PORT" cp "$f" :lib/
done

for f in drivers/*.py; do
    [[ -e "$f" ]] || continue
    "$MPREMOTE_CMD" connect "$PORT" cp "$f" :drivers/
done

echo "Repair sync complete on $PORT"
