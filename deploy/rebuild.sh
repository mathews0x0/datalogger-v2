#!/bin/bash
# ==============================================================================
# RaceSense — Nuke and Rebuild Script
# Run this on the production server to completely rebuild the app from scratch.
# IT WILL BACKUP YOUR DATABASE AUTOMATICALLY.
# ==============================================================================

set -e

APP_DIR="/var/www/racesense"
VENV_DIR="$APP_DIR/server/venv"
DB_PATH="$APP_DIR/server/data/racesense.db"
BACKUP_DIR="/root/racesense_backups"
TIMESTAMP=$(date +%F_%H%M%S)
DB_BACKUP="$BACKUP_DIR/nuke_backup_$TIMESTAMP.db.bak"

echo "========================================"
echo " RaceSense Nuke & Rebuild"
echo "========================================"

# 1. Backup DB
echo "[1/5] Backing up critical database..."
mkdir -p "$BACKUP_DIR"
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$DB_BACKUP"
    echo "Database saved to $DB_BACKUP"
else
    echo "No existing database found to backup."
fi

# 2. Demolish app
echo "[2/5] Stopping services and removing app directory..."
systemctl stop racesense racesense-worker || true
systemctl disable racesense racesense-worker || true
rm -rf "$APP_DIR"

# 3. Download and Run setup.sh
echo "[3/5] Running fresh setup.sh..."
wget -qO- https://raw.githubusercontent.com/mathews0x0/datalogger-v2/main/deploy/setup.sh | bash

# 4. Restore database and fast-forward schema
echo "[4/5] Restoring old data and reapplying migrations..."
systemctl stop racesense racesense-worker

if [ -f "$DB_BACKUP" ]; then
    mkdir -p "$(dirname "$DB_PATH")"
    cp "$DB_BACKUP" "$DB_PATH"

    bash -c "
        cd '$APP_DIR/server' && \
        . '$VENV_DIR/bin/activate' && \
        set -a && \
        . '$APP_DIR/.env' && \
        set +a && \
        export FLASK_APP=run && \
        flask db upgrade
    "
else
    echo "No backup found to restore. Starting with fresh DB."
fi

# 5. Restart
echo "[5/5] Restarting application..."
systemctl start racesense racesense-worker

echo ""
echo "========================================"
echo " ✅ Rebuild complete! Your app is back online."
echo "========================================"
