#!/bin/bash
# ==============================================================================
# RaceSense — First-Time VPS Setup Script
# Run on a fresh Ubuntu 22.04 VPS as root
# Usage: sudo bash setup.sh
# ==============================================================================

set -e

APP_DIR="/opt/racesense"
APP_USER="racesense"
REPO_URL="https://github.com/YOUR_USERNAME/datalogger-v2.git"  # <-- UPDATE THIS

echo "========================================"
echo " RaceSense VPS Setup"
echo "========================================"

# --- 1. System Dependencies ---
echo "[1/8] Installing system packages..."
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx git curl ufw

# --- 2. Create App User ---
echo "[2/8] Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --create-home --shell /bin/bash "$APP_USER"
    echo "Created user: $APP_USER"
else
    echo "User $APP_USER already exists"
fi

# --- 3. Clone Repository ---
echo "[3/8] Setting up application directory..."
if [ -d "$APP_DIR" ]; then
    echo "Directory $APP_DIR already exists. Pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --- 4. Python Virtual Environment ---
echo "[4/8] Creating Python virtual environment..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# --- 5. Environment Configuration ---
echo "[5/8] Setting up environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Generate a random JWT secret
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE_ME_TO_A_RANDOM_64_CHAR_STRING/$JWT_SECRET/" "$APP_DIR/.env"
    echo "Created .env with auto-generated JWT secret."
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║  IMPORTANT: Edit /opt/racesense/.env to set     ║"
    echo "  ║  CORS_ORIGINS to your domain before launch!     ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo ""
else
    echo ".env already exists, skipping."
fi

# --- 6. Initialize Database ---
echo "[6/8] Initializing database..."
sudo -u "$APP_USER" bash -c "
    cd $APP_DIR/server && \
    source $APP_DIR/venv/bin/activate && \
    FLASK_ENV=production \
    JWT_SECRET_KEY=\$(grep JWT_SECRET_KEY $APP_DIR/.env | cut -d= -f2) \
    python3 api/init_db.py
"

# --- 7. Log Directory ---
echo "[7/8] Setting up logs..."
mkdir -p /var/log/racesense
chown "$APP_USER:$APP_USER" /var/log/racesense

# --- 8. Systemd Service ---
echo "[8/8] Installing systemd service..."
cp "$APP_DIR/deploy/racesense.service" /etc/systemd/system/racesense.service
systemctl daemon-reload
systemctl enable racesense
systemctl start racesense

# --- Nginx ---
echo "[+] Configuring Nginx..."
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/racesense
ln -sf /etc/nginx/sites-available/racesense /etc/nginx/sites-enabled/racesense
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# --- Firewall ---
echo "[+] Configuring firewall..."
ufw allow ssh
ufw allow 'Nginx Full'
ufw --force enable

echo ""
echo "========================================"
echo " ✅ RaceSense deployed successfully!"
echo "========================================"
echo ""
echo " URL:     http://$(curl -s ifconfig.me)"
echo " Logs:    journalctl -u racesense -f"
echo " Reload:  sudo systemctl reload racesense"
echo " Config:  nano /opt/racesense/.env"
echo ""
