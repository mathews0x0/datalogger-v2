#!/bin/bash

# listen_esp.sh - Auto-detect ESP32 and connect via mpremote
# Matches /dev/cu.usbmodem* (Internal S3) or /dev/cu.usbserial* (Bridge chips)

DEVICE=$(ls /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null | head -n 1)

if [ -z "$DEVICE" ]; then
    # Fallback search for any CU device with 'usb' in the name
    DEVICE=$(ls /dev/cu.*usb* 2>/dev/null | head -n 1)
fi

if [ -z "$DEVICE" ]; then
    echo "❌ Error: No ESP32 device detected."
    echo "Check connection and ensure device is in /dev/cu.*"
    exit 1
fi

echo "🚀 Connecting to $DEVICE..."
$HOME/Library/Python/3.9/bin/mpremote connect "$DEVICE" repl
