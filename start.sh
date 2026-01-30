#!/bin/bash
# Start Datalogger V2 Server

# Ensure we are in the script's directory (dataloggerV2 root)
cd "$(dirname "$0")"

# Kill existing process on port 6969
PID=$(lsof -ti:6969)
if [ -n "$PID" ]; then
  echo "Killing process on port 6969 (PID: $PID)..."
  kill -9 $PID
  sleep 1
fi

echo "Starting Datalogger V2 on Port 6969..."
cd server
export PYTHONUNBUFFERED=1
python3 run.py
