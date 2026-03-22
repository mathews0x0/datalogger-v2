#!/bin/bash
# ==============================================================================
# RaceSense — Production Upgrade Script
# Run this on the production server (e.g. via sudo bash deploy/upgrade.sh)
# ==============================================================================

set -e

APP_DIR="/var/www/racesense"
VENV_DIR="$APP_DIR/server/venv"
DB_PATH="$APP_DIR/server/data/racesense.db"
BACKUP_DIR="/root/racesense_backups"

echo "========================================"
echo " RaceSense Production Upgrade"
echo "========================================"

# 1. Backup
echo "[1/7] Backing up database..."
mkdir -p "$BACKUP_DIR"
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_DIR/racesense_$(date +%F_%H%M%S).db.bak"
    echo "Backup saved to $BACKUP_DIR"
else
    echo "No database found to backup, skipping..."
fi

# 2. Stop Services
echo "[2/7] Stopping application services..."
systemctl stop racesense racesense-worker || true

# 3. Pull Latest Code
echo "[3/7] Fetching latest code..."
cd "$APP_DIR"
git fetch --all
git reset --hard origin/main

# 4. Update Python Dependencies
echo "[4/7] Updating Python dependencies..."
if [ ! -x "$VENV_DIR/bin/pip" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# 5. Database Migrations
echo "[5/7] Running database migrations..."
bash -c "
    cd '$APP_DIR/server' && \
    . '$VENV_DIR/bin/activate' && \
    set -a && \
    . '$APP_DIR/.env' && \
    set +a && \
    export FLASK_APP=run && \
    flask db upgrade
"

# 6. Update System Configs
echo "[6/7] Updating system configurations..."
cp "$APP_DIR/deploy/racesense.service" /etc/systemd/system/racesense.service
cp "$APP_DIR/deploy/racesense-worker.service" /etc/systemd/system/racesense-worker.service
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/racesense
systemctl daemon-reload

# 7. Restart
echo "[7/7] Restarting services..."
nginx -t && systemctl restart nginx
systemctl start racesense racesense-worker

echo ""
echo "========================================"
echo " ✅ Upgrade complete! App is ready."
echo "========================================"
