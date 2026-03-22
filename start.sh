#!/bin/bash
# Start Datalogger V2 Server

set -e

# Ensure we are in the script's directory (dataloggerV2 root)
cd "$(dirname "$0")"

DEV_ENV_FILE="$PWD/env/development.env"
DEV_ENV_EXAMPLE="$PWD/env/development.env.example"
DEFAULT_DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:5432/racesense_dev"

# Kill existing process on port 6969
PID=$(lsof -ti:6969 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "Killing process on port 6969 (PID: $PID)..."
  kill -9 $PID
  sleep 1
fi

WORKER_PID=$(pgrep -f "worker.py" 2>/dev/null || true)
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

if [ ! -f "$DEV_ENV_FILE" ] && [ -f "$DEV_ENV_EXAMPLE" ]; then
  echo "Creating env/development.env from example..."
  cp "$DEV_ENV_EXAMPLE" "$DEV_ENV_FILE"
fi

if [ -f "$DEV_ENV_FILE" ]; then
  set -a
  . "$DEV_ENV_FILE"
  set +a
fi

if [ -z "${DATABASE_URL:-}" ] || [[ "${DATABASE_URL}" == *"CHANGE_ME"* ]]; then
  echo "Setting default DATABASE_URL in $DEV_ENV_FILE..."
  python3 - "$DEV_ENV_FILE" "$DEFAULT_DATABASE_URL" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
default_url = sys.argv[2]

if env_path.exists():
    lines = env_path.read_text().splitlines()
else:
    lines = []

updated = False
for index, line in enumerate(lines):
    if line.startswith("DATABASE_URL="):
        lines[index] = f"DATABASE_URL={default_url}"
        updated = True
        break

if not updated:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"DATABASE_URL={default_url}")

env_path.write_text("\n".join(lines) + "\n")
PY
  export DATABASE_URL="$DEFAULT_DATABASE_URL"
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL must be set in $DEV_ENV_FILE before starting RaceSense."
  exit 1
fi

echo "Ensuring local database exists..."
bash ../deploy/ensure_local_postgres.sh

echo "Applying database migrations..."
export FLASK_APP=run
flask db upgrade

echo "Starting background job worker..."
nohup python3 worker.py > worker.log 2>&1 &

echo "Starting main web server..."
python3 run.py
