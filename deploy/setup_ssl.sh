#!/bin/bash
# ============================================================
# RaceSense — SSL/HTTPS Setup via Certbot (Let's Encrypt)
#
# Run this on the production VPS as root:
#   sudo bash deploy/setup_ssl.sh
#
# Prerequisites:
#   - Ubuntu/Debian VPS with Nginx installed
#   - DNS for racesense.in pointing to this server
#   - Port 80 and 443 open in firewall
# ============================================================

set -e

DOMAIN="racesense.in"
WWW_DOMAIN="www.racesense.in"
NGINX_CONF="/etc/nginx/sites-available/racesense"
NGINX_ENABLED="/etc/nginx/sites-enabled/racesense"
REPO_CONF="$(dirname "$0")/../server/racesense_nginx.conf"

echo "=== RaceSense SSL Setup ==="
echo ""

# 1. Install Certbot
echo "[1/5] Installing Certbot..."
apt-get update -qq
apt-get install -y certbot python3-certbot-nginx

# 2. Copy Nginx config
echo "[2/5] Installing Nginx config..."
cp "$REPO_CONF" "$NGINX_CONF"
ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default

# 3. Test Nginx config (before SSL — temporarily comment out SSL lines)
echo "[3/5] Testing Nginx config..."
nginx -t

# 4. Obtain SSL certificate
echo "[4/5] Obtaining SSL certificate from Let's Encrypt..."
certbot --nginx -d "$DOMAIN" -d "$WWW_DOMAIN" --non-interactive --agree-tos --email admin@racesense.in --redirect

# 5. Verify auto-renewal
echo "[5/5] Verifying auto-renewal..."
certbot renew --dry-run

echo ""
echo "=== SSL Setup Complete ==="
echo "  https://$DOMAIN should now be live"
echo "  Certificates auto-renew via systemd timer"
echo ""
echo "  To verify: curl -I https://$DOMAIN"
echo ""
