#!/bin/bash
# Start Track Layout Generator

set -e

cd "$(dirname "$0")"

GENERATOR_DIR="$PWD/track-layout-generator"
PORT="${TRACK_GENERATOR_PORT:-8080}"

if [ ! -d "$GENERATOR_DIR" ]; then
  echo "track-layout-generator directory not found."
  exit 1
fi

PID=$(lsof -ti:"$PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "Killing process on port $PORT (PID: $PID)..."
  kill -9 $PID
  sleep 1
fi

echo "Starting Track Layout Generator on port $PORT..."
cd "$GENERATOR_DIR"
python3 -m http.server "$PORT"
