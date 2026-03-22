#!/bin/bash
# ==============================================================================
# RaceSense — First-Time VPS Setup Script
# Run on a fresh Ubuntu 24.04 VPS as root
# Usage: sudo bash setup.sh
# ==============================================================================

set -e

APP_DIR="/var/www/racesense"
VENV_DIR="$APP_DIR/server/venv"
LOG_DIR="/var/log/racesense"

echo "========================================"
echo " RaceSense VPS Setup"
echo "========================================"

# --- 1. System Dependencies ---
echo "[1/6] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    ca-certificates \
    curl \
    git \
    nginx \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    build-essential \
    pkg-config

# --- 2. Validate application directory ---
echo "[2/6] Validating application directory..."
if [ ! -d "$APP_DIR/server" ]; then
    echo "Expected application files in $APP_DIR before running setup.sh"
    exit 1
fi

# --- 3. Python Virtual Environment ---
echo "[3/6] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# --- 4. Environment Configuration ---
echo "[4/6] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Generate a random JWT secret
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE_ME_TO_A_RANDOM_64_CHAR_STRING/$JWT_SECRET/" "$APP_DIR/.env"
    echo "Created .env with auto-generated JWT secret."
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║  IMPORTANT: Edit /var/www/racesense/.env to set ║"
    echo "  ║  CORS_ORIGINS to your domain before launch!     ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo ""
else
    echo ".env already exists, skipping."
fi

# --- 5. Initialize Database ---
echo "[5/6] Initializing database..."
bash -c "
    cd '$APP_DIR/server' && \
    . '$VENV_DIR/bin/activate' && \
    set -a && \
    . '$APP_DIR/.env' && \
    set +a && \
    export FLASK_APP=run && \
    flask db upgrade
"

# --- 6. Install services and Nginx ---
echo "[6/6] Installing services and Nginx..."
mkdir -p "$LOG_DIR"
cp "$APP_DIR/deploy/racesense.service" /etc/systemd/system/racesense.service
cp "$APP_DIR/deploy/racesense-worker.service" /etc/systemd/system/racesense-worker.service
systemctl daemon-reload
systemctl enable racesense racesense-worker nginx
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/racesense
ln -sf /etc/nginx/sites-available/racesense /etc/nginx/sites-enabled/racesense
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl restart racesense
systemctl restart racesense-worker

echo ""
echo "========================================"
echo " ✅ RaceSense deployed successfully!"
echo "========================================"
echo ""
echo " URL:     http://$(curl -s ifconfig.me)"
echo " Logs:    journalctl -u racesense -f  |  journalctl -u racesense-worker -f"
echo " Reload:  sudo systemctl restart racesense && sudo systemctl restart racesense-worker"
echo " Config:  nano /var/www/racesense/.env"
echo ""
