#!/bin/bash
# ==============================================================================
# RaceSense — Deploy Latest Code (Hot Reload)
# Run from your local machine or on the VPS
# Usage: bash deploy.sh [vps-ip]
# ==============================================================================

set -e

APP_DIR="/opt/racesense"

# If running locally with a VPS IP argument, SSH in and execute remotely
if [ -n "$1" ]; then
    echo "🚀 Deploying to $1..."
    ssh "racesense@$1" "bash $APP_DIR/deploy/deploy.sh"
    exit $?
fi

# --- Running on the VPS ---
echo "========================================"
echo " RaceSense — Deploying Latest Code"
echo "========================================"

cd "$APP_DIR"

# Pull latest code
echo "[1/3] Pulling latest code..."
git pull origin main

# Install any new dependencies
echo "[2/3] Installing dependencies..."
source "$APP_DIR/venv/bin/activate"
pip install -r server/requirements.txt --quiet

# Graceful reload (zero downtime)
echo "[3/3] Reloading server..."
sudo systemctl reload racesense

echo ""
echo "✅ Deployed at $(date)"
echo "   Check logs: journalctl -u racesense -f"
echo ""
