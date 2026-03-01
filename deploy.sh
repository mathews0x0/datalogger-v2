#!/bin/bash
# ==============================================================================
# RaceSense Deploy — Push updates from Mac to production VPS
# ------------------------------------------------------------------------------
# Usage:
#   ./deploy.sh upgrade   — Sync latest code and restart (keeps DB intact)
#   ./deploy.sh nuke      — Full wipe + redeploy from scratch (restores DB)
#
# Tested on: macOS bash 3.2 + openrsync 2.6.9
# ==============================================================================

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
SERVER="root@103.189.89.142"
REMOTE_APP_DIR="/var/www/racesense"
REMOTE_VENV="$REMOTE_APP_DIR/server/venv"
REMOTE_DB="$REMOTE_APP_DIR/server/data/racesense.db"
BACKUP_DIR="/root/racesense_backups"
LOCAL_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ─── SSH Multiplexing (enter password only ONCE) ─────────────────────────────
SSH_SOCK="/tmp/racesense_deploy_$$"
SSH_OPTS="-o ConnectTimeout=10 -o ControlMaster=auto -o ControlPath=$SSH_SOCK -o ControlPersist=300"
export RSYNC_RSH="ssh $SSH_OPTS"

cleanup() {
    ssh -o ControlPath="$SSH_SOCK" -O exit "$SERVER" 2>/dev/null || true
}
trap cleanup EXIT

# ─── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Helpers ──────────────────────────────────────────────────────────────────
step()  { echo -e "\n${CYAN}${BOLD}[$1]${NC} $2"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }

remote() {
    ssh $SSH_OPTS -t "$SERVER" "$@"
}

# ─── Rsync wrapper (compatible with macOS openrsync 2.6.9) ───────────────────
# Flags used: -r recursive, -l symlinks, -t timestamps, -z compress, -q quiet
do_rsync() {
    rsync -rltzq "$@"
}

# ─── Validate Command ────────────────────────────────────────────────────────
CMD="${1:-}"
if [ "$CMD" != "upgrade" ] && [ "$CMD" != "nuke" ]; then
    echo -e "${BOLD}RaceSense Deploy${NC}"
    echo ""
    echo "Usage: ./deploy.sh <command>"
    echo ""
    echo "Commands:"
    echo "  upgrade   Sync latest code, install deps, migrate DB, restart services"
    echo "  nuke      Full wipe + fresh setup (backs up & restores DB automatically)"
    echo ""
    exit 1
fi

CMD_UPPER=$(echo "$CMD" | tr '[:lower:]' '[:upper:]')
echo -e "\n${BOLD}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  RaceSense Deploy — ${CMD_UPPER}${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════════════${NC}"

# ==============================================================================
#   UPGRADE — Incremental update, keeps DB intact
# ==============================================================================
do_upgrade() {
    # ── 0. Establish SSH connection (password prompt happens here, ONCE) ────
    step "0/5" "Connecting to server..."
    remote "echo 'SSH OK'"
    ok "SSH session established (all further commands reuse this connection)"

    # ── 1. Sync files ─────────────────────────────────────────────────────────
    step "1/5" "Syncing files to production..."

    # Ensure target directories exist
    remote "mkdir -p $REMOTE_APP_DIR/src $REMOTE_APP_DIR/server $REMOTE_APP_DIR/deploy"

    # Sync server/ (no --delete because excluded dirs like ios/android may exist on remote)
    do_rsync \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='data' \
        --exclude='instance' \
        --exclude='ui/ios' \
        --exclude='ui/android' \
        --exclude='ui/www' \
        --exclude='ui/node_modules' \
        --exclude='ui/capacitor.config.json' \
        --exclude='ui/package-lock.json' \
        --exclude='ui/package.json' \
        --exclude='tests' \
        --exclude='.git' \
        --exclude='.gitignore' \
        --exclude='.DS_Store' \
        --exclude='worker.log' \
        "$LOCAL_ROOT/server/" "$SERVER:$REMOTE_APP_DIR/server/"
    ok "server/ synced"

    # Sync src/ (--delete is safe here, simple directory)
    do_rsync --delete \
        --exclude='__pycache__' \
        "$LOCAL_ROOT/src/" "$SERVER:$REMOTE_APP_DIR/src/"
    ok "src/ synced"

    # Sync deploy/ configs (--delete is safe here)
    do_rsync --delete \
        "$LOCAL_ROOT/deploy/" "$SERVER:$REMOTE_APP_DIR/deploy/"
    ok "deploy/ synced"

    # Sync .env.example
    do_rsync "$LOCAL_ROOT/.env.example" "$SERVER:$REMOTE_APP_DIR/"
    ok ".env.example synced"

    # ── 2. Backup database ────────────────────────────────────────────────────
    step "2/5" "Backing up production database..."

    BACKUP_RESULT=$(remote "
        mkdir -p $BACKUP_DIR
        if [ -f '$REMOTE_DB' ]; then
            cp -p '$REMOTE_DB' '$BACKUP_DIR/racesense_\$(date +%F_%H%M%S).db.bak'
            echo 'BACKUP_OK'
        else
            echo 'NO_DB'
        fi
    " 2>/dev/null) || true
    if echo "$BACKUP_RESULT" | grep -q 'BACKUP_OK'; then
        ok "Database backed up"
    else
        warn "No existing database found"
    fi

    # ── 3. Install dependencies ───────────────────────────────────────────────
    step "3/5" "Installing Python dependencies..."

    remote "
        $REMOTE_VENV/bin/pip install --quiet --upgrade pip 2>&1 | tail -1
        $REMOTE_VENV/bin/pip install --quiet -r $REMOTE_APP_DIR/server/requirements.txt 2>&1 | tail -1
    "
    ok "Dependencies up to date"

    # ── 4. Run database migrations ────────────────────────────────────────────
    step "4/5" "Running database migrations..."

    remote "
        cd $REMOTE_APP_DIR/server
        source $REMOTE_VENV/bin/activate

        # Load env vars from .env file
        if [ -f '$REMOTE_APP_DIR/.env' ]; then
            set -a
            . '$REMOTE_APP_DIR/.env'
            set +a
        fi

        export FLASK_APP=run
        flask db upgrade
    "
    ok "Migrations applied"

    # ── 5. Update configs & restart services ──────────────────────────────────
    step "5/5" "Restarting services..."

    remote "
        # Update systemd service files
        cp $REMOTE_APP_DIR/deploy/racesense.service /etc/systemd/system/racesense.service
        cp $REMOTE_APP_DIR/deploy/racesense-worker.service /etc/systemd/system/racesense-worker.service
        systemctl daemon-reload

        # Update nginx config
        cp $REMOTE_APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/racesense
        ln -sf /etc/nginx/sites-available/racesense /etc/nginx/sites-enabled/racesense
        nginx -t 2>&1 && systemctl reload nginx

        # Restart app services
        systemctl restart racesense
        systemctl restart racesense-worker

        # Quick health check
        sleep 3
        if systemctl is-active --quiet racesense; then
            echo 'SERVICE_OK'
        else
            echo 'SERVICE_FAIL'
            journalctl -u racesense --no-pager -n 20
        fi
    "

    echo -e "\n${GREEN}${BOLD}  ✅ Upgrade complete!${NC}"
    echo -e "  ${CYAN}→${NC} https://racesense.in"
}

# ==============================================================================
#   NUKE — Full wipe + fresh redeploy (preserves database)
# ==============================================================================
do_nuke() {
    echo -e "\n${RED}${BOLD}  ⚠  WARNING: This will completely wipe the production app directory!${NC}"
    echo -e "  ${YELLOW}The database will be backed up and restored automatically.${NC}"
    echo ""
    read -p "  Type 'NUKE' to confirm: " confirm
    if [ "$confirm" != "NUKE" ]; then
        echo "Aborted."
        exit 0
    fi

    # ── 0. Establish SSH connection ───────────────────────────────────────────
    step "0/6" "Connecting to server..."
    remote "echo 'SSH OK'"
    ok "SSH session established"

    # ── 1. Backup database ────────────────────────────────────────────────────
    step "1/6" "Backing up production database..."

    BACKUP_RESULT=$(remote "
        mkdir -p $BACKUP_DIR
        if [ -f '$REMOTE_DB' ]; then
            STAMP=\$(date +%F_%H%M%S)
            cp -p '$REMOTE_DB' '$BACKUP_DIR/nuke_backup_'\$STAMP'.db.bak'
            echo '$BACKUP_DIR/nuke_backup_'\$STAMP'.db.bak' > /tmp/racesense_last_backup
            echo 'BACKUP_OK'
        else
            echo 'NO_DB'
        fi
    " 2>/dev/null) || true
    if echo "$BACKUP_RESULT" | grep -q 'BACKUP_OK'; then
        ok "Database backed up"
    else
        warn "No existing database to backup"
    fi

    # ── 2. Preserve .env ──────────────────────────────────────────────────────
    step "2/6" "Preserving .env configuration..."

    ENV_RESULT=$(remote "
        if [ -f '$REMOTE_APP_DIR/.env' ]; then
            cp -p '$REMOTE_APP_DIR/.env' '/tmp/racesense_env_backup'
            echo 'ENV_OK'
        else
            echo 'NO_ENV'
        fi
    " 2>/dev/null) || true
    if echo "$ENV_RESULT" | grep -q 'ENV_OK'; then
        ok ".env preserved"
    else
        warn "No .env found"
    fi

    # ── 3. Stop services & wipe ──────────────────────────────────────────────
    step "3/6" "Stopping services and wiping app directory..."

    remote "
        systemctl stop racesense racesense-worker || true
        rm -rf $REMOTE_APP_DIR
        mkdir -p $REMOTE_APP_DIR
    "
    ok "Clean slate ready"

    # ── 4. Deploy fresh code ──────────────────────────────────────────────────
    step "4/6" "Deploying fresh code from local machine..."

    do_rsync \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='venv' \
        --exclude='data' \
        --exclude='instance' \
        --exclude='ui/ios' \
        --exclude='ui/android' \
        --exclude='ui/www' \
        --exclude='ui/node_modules' \
        --exclude='ui/capacitor.config.json' \
        --exclude='ui/package-lock.json' \
        --exclude='ui/package.json' \
        --exclude='tests' \
        --exclude='.git' \
        --exclude='.gitignore' \
        --exclude='.DS_Store' \
        --exclude='worker.log' \
        "$LOCAL_ROOT/server/" "$SERVER:$REMOTE_APP_DIR/server/"
    ok "server/ deployed"

    do_rsync \
        --exclude='__pycache__' \
        "$LOCAL_ROOT/src/" "$SERVER:$REMOTE_APP_DIR/src/"
    ok "src/ deployed"

    do_rsync \
        "$LOCAL_ROOT/deploy/" "$SERVER:$REMOTE_APP_DIR/deploy/"
    ok "deploy/ deployed"

    do_rsync \
        "$LOCAL_ROOT/.env.example" "$SERVER:$REMOTE_APP_DIR/"
    ok ".env.example deployed"

    # ── 5. Rebuild environment on server ──────────────────────────────────────
    step "5/6" "Rebuilding server environment..."

    remote "
        # Restore .env (or create from template)
        if [ -f '/tmp/racesense_env_backup' ]; then
            cp -p '/tmp/racesense_env_backup' '$REMOTE_APP_DIR/.env'
            rm -f '/tmp/racesense_env_backup'
        elif [ -f '$REMOTE_APP_DIR/.env.example' ]; then
            cp '$REMOTE_APP_DIR/.env.example' '$REMOTE_APP_DIR/.env'
        fi

        # Recreate venv and install deps
        python3 -m venv $REMOTE_VENV
        $REMOTE_VENV/bin/pip install --quiet --upgrade pip 2>&1 | tail -1
        $REMOTE_VENV/bin/pip install --quiet -r $REMOTE_APP_DIR/server/requirements.txt 2>&1 | tail -1

        # Ensure data directory exists
        mkdir -p $REMOTE_APP_DIR/server/data
        mkdir -p $REMOTE_APP_DIR/server/instance

        # Restore database backup
        BACKUP_PATH=\$(cat /tmp/racesense_last_backup 2>/dev/null || echo '')
        if [ -n \"\$BACKUP_PATH\" ] && [ -f \"\$BACKUP_PATH\" ]; then
            cp -p \"\$BACKUP_PATH\" '$REMOTE_DB'
        fi

        # Run migrations
        cd $REMOTE_APP_DIR/server
        source $REMOTE_VENV/bin/activate
        if [ -f '$REMOTE_APP_DIR/.env' ]; then
            set -a
            . '$REMOTE_APP_DIR/.env'
            set +a
        fi
        export FLASK_APP=run
        flask db upgrade

        # Ensure log directory exists
        mkdir -p /var/log/racesense
    "
    ok "Environment rebuilt"

    # ── 6. Install configs & start services ───────────────────────────────────
    step "6/6" "Installing system configs and starting services..."

    remote "
        # Install systemd services
        cp $REMOTE_APP_DIR/deploy/racesense.service /etc/systemd/system/racesense.service
        cp $REMOTE_APP_DIR/deploy/racesense-worker.service /etc/systemd/system/racesense-worker.service
        systemctl daemon-reload
        systemctl enable racesense racesense-worker

        # Install nginx config
        cp $REMOTE_APP_DIR/deploy/nginx.conf /etc/nginx/sites-available/racesense
        ln -sf /etc/nginx/sites-available/racesense /etc/nginx/sites-enabled/racesense
        rm -f /etc/nginx/sites-enabled/default
        nginx -t 2>&1 && systemctl reload nginx

        # Start app
        systemctl start racesense racesense-worker

        # Verify
        sleep 3
        if systemctl is-active --quiet racesense; then
            echo 'SERVICE_OK'
        else
            echo 'SERVICE_FAIL'
            journalctl -u racesense --no-pager -n 20
        fi
    "

    echo -e "\n${GREEN}${BOLD}  ✅ Nuke & rebuild complete!${NC}"
    echo -e "  ${CYAN}→${NC} https://racesense.in"
}

# ─── Dispatch ─────────────────────────────────────────────────────────────────
case "$CMD" in
    upgrade) do_upgrade ;;
    nuke)    do_nuke ;;
esac

echo -e "\n${BOLD}Useful commands:${NC}"
echo -e "  ${CYAN}ssh $SERVER 'journalctl -u racesense -f'${NC}          — Live app logs"
echo -e "  ${CYAN}ssh $SERVER 'journalctl -u racesense-worker -f'${NC}   — Worker logs"
echo -e "  ${CYAN}ssh $SERVER 'systemctl status racesense'${NC}          — Service status"
echo ""
