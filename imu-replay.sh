#!/bin/zsh
set -euo pipefail

APP_DIR="$PWD/imu-replay"
PORT="${IMU_REPLAY_PORT:-8090}"

if [ ! -d "$APP_DIR" ]; then
  echo "imu-replay directory not found."
  exit 1
fi

cd "$APP_DIR"
echo "Starting IMU Replay Lab on port $PORT..."
echo "Open http://localhost:$PORT/"
IMU_REPLAY_PORT="$PORT" python3 server.py
