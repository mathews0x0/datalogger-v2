#!/bin/bash
# Start Datalogger V2 Server

# Ensure we are in the script's directory (dataloggerV2 root)
cd "$(dirname "$0")"

DEV_ENV_FILE="$PWD/env/development.env"

# Kill existing process on port 6969
PID=$(lsof -ti:6969)
if [ -n "$PID" ]; then
  echo "Killing process on port 6969 (PID: $PID)..."
  kill -9 $PID
  sleep 1
fi

WORKER_PID=$(pgrep -f "worker.py")
if [ -n "$WORKER_PID" ]; then
  echo "Killing existing worker processes..."
  kill -9 $WORKER_PID
  sleep 1
fi

echo "Starting Datalogger V2 on Port 6969..."
cd server
export PYTHONUNBUFFERED=1
if [ -d "venv" ]; then
  source venv/bin/activate
fi

if [ -f "$DEV_ENV_FILE" ]; then
  set -a
  . "$DEV_ENV_FILE"
  set +a
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL must be set in $DEV_ENV_FILE before starting RaceSense."
  exit 1
fi

echo "Starting background job worker..."
nohup python3 worker.py > worker.log 2>&1 &

echo "Starting main web server..."
python3 run.py
