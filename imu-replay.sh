#!/bin/zsh
set -euo pipefail

APP_DIR="$PWD/imu-replay"
PORT="${IMU_REPLAY_PORT:-8090}"

if [ ! -d "$APP_DIR" ]; then
  echo "imu-replay directory not found."
  exit 1
fi

PIDS="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  echo "Stopping existing IMU Replay server on port $PORT..."
  echo "$PIDS" | xargs kill
  sleep 1

  STILL_RUNNING="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  if [ -n "$STILL_RUNNING" ]; then
    echo "Existing server did not stop cleanly; forcing shutdown..."
    echo "$STILL_RUNNING" | xargs kill -9
  fi
fi

cd "$APP_DIR"
echo "Starting IMU Replay Lab on port $PORT..."
echo "Open http://localhost:$PORT/"
IMU_REPLAY_PORT="$PORT" python3 server.py
