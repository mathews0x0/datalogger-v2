#!/bin/zsh
set -euo pipefail

PORT="${1:-/dev/cu.usbmodem11401}"
MPREMOTE_CMD="/Users/mj/Library/Python/3.9/bin/mpremote"

cd /Users/mj/Documents/datalogger-v2/firmware

"$MPREMOTE_CMD" connect "$PORT" exec "import os
try:
    for f in os.listdir('/'):
        if f.endswith('.py'):
            try:
                os.remove('/' + f)
            except:
                pass
    def rmtree(d):
        try:
            if os.stat(d)[0] & 0x4000:
                for f in os.listdir(d):
                    rmtree(d + '/' + f)
                os.rmdir(d)
            else:
                os.remove(d)
        except:
            pass
    for d in ['/lib', '/drivers']:
        try:
            rmtree(d)
        except:
            pass
except:
    pass"

for dir in /lib /drivers /data /data/metadata /sd /lib/tft_fonts; do
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

for f in lib/*.raw; do
    [[ -e "$f" ]] || continue
    "$MPREMOTE_CMD" connect "$PORT" cp "$f" :lib/
done

for f in lib/*/*.py; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *"__pycache__"* ]] && continue
    "$MPREMOTE_CMD" connect "$PORT" cp "$f" ":$f"
done

for f in drivers/*.py; do
    [[ -e "$f" ]] || continue
    "$MPREMOTE_CMD" connect "$PORT" cp "$f" :drivers/
done

echo "Firmware source sync complete on $PORT"
