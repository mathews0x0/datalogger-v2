#!/bin/bash
# ==============================================================================
# RaceSense — Production Upgrade Script
# Run this on the production server (e.g. via sudo bash deploy/upgrade.sh)
# ==============================================================================

set -e

APP_DIR="/opt/racesense"
APP_USER="racesense"
BACKUP_DIR="/home/$(logname)/racesense_backups"

echo "========================================"
echo " RaceSense Production Upgrade"
echo "========================================"

# 1. Backup
echo "[1/7] Backing up database..."
mkdir -p "$BACKUP_DIR"
if [ -f "$APP_DIR/server/instance/racesense.db" ]; then
    cp "$APP_DIR/server/instance/racesense.db" "$BACKUP_DIR/racesense_$(date +%F_%H%M%S).db.bak"
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
sudo -u "$APP_USER" git fetch --all
sudo -u "$APP_USER" git reset --hard origin/main

# 4. Update Python Dependencies
echo "[4/7] Updating Python dependencies..."
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# 5. Database Migrations
echo "[5/7] Running database migrations..."
if grep -q "JWT_SECRET_KEY" "$APP_DIR/.env"; then
    SECRET=$(grep JWT_SECRET_KEY "$APP_DIR/.env" | cut -d= -f2)
else
    SECRET="placeholder"
fi

sudo -u "$APP_USER" bash -c "
    cd $APP_DIR/server && \
    source $APP_DIR/venv/bin/activate && \
    export FLASK_ENV=production && \
    export FLASK_APP=run && \
    export JWT_SECRET_KEY=$SECRET && \
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
