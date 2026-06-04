#!/bin/bash
# ==============================================================================
# RaceSense Deploy — Push updates from Mac to production VPS
# ------------------------------------------------------------------------------
# Usage:
#   ./deploy.sh upgrade   — Sync latest code and restart (keeps DB intact)
#   ./deploy.sh nuke      — Full wipe + redeploy from scratch (restores DB)
#
# Tested on: macOS bash 3.2 + openrsync 2.6.9, Ubuntu 24.04 VPS
# ==============================================================================

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
SERVER="${SERVER:-rs-hostco}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/var/www/racesense}"
REMOTE_VENV="$REMOTE_APP_DIR/server/venv"
REMOTE_ENV_DIR="$REMOTE_APP_DIR/env"
REMOTE_PROD_ENV="$REMOTE_ENV_DIR/production.env"
REMOTE_LEGACY_ENV="$REMOTE_APP_DIR/.env"
BACKUP_DIR="${BACKUP_DIR:-/root/racesense_backups}"
LOCAL_ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCAL_VERSION_FILE="$LOCAL_ROOT/server/VERSION"
REMOTE_VERSION_FILE="$REMOTE_APP_DIR/server/VERSION"
DEPLOY_MACHINE_TIME="$(date '+%d/%m/%Y %I:%M%p' | sed 's/ 0/ /' | tr 'A-Z' 'a-z')"

# ─── SSH Multiplexing (cache local auth for 24h) ─────────────────────────────
SSH_CACHE_DIR="${HOME}/.cache/racesense"
mkdir -p "$SSH_CACHE_DIR"
SERVER_SLUG=$(printf '%s' "$SERVER" | tr -c '[:alnum:]._-@' '_')
SSH_SOCK="$SSH_CACHE_DIR/ssh_mux_${SERVER_SLUG}"
SSH_OPTS="-o ConnectTimeout=10 -o ControlMaster=auto -o ControlPath=$SSH_SOCK -o ControlPersist=86400"
export RSYNC_RSH="ssh $SSH_OPTS"

reset_ssh_mux_if_stale() {
    if [ -S "$SSH_SOCK" ] && ! ssh -o ControlPath="$SSH_SOCK" -O check "$SERVER" >/dev/null 2>&1; then
        rm -f "$SSH_SOCK"
    fi
}

ensure_ssh_mux() {
    reset_ssh_mux_if_stale
    if ssh -o ControlPath="$SSH_SOCK" -O check "$SERVER" >/dev/null 2>&1; then
        return
    fi

    rm -f "$SSH_SOCK"
    ssh -fN \
        -o ConnectTimeout=10 \
        -o ControlMaster=yes \
        -o ControlPath="$SSH_SOCK" \
        -o ControlPersist=86400 \
        "$SERVER"

    if ! ssh -o ControlPath="$SSH_SOCK" -O check "$SERVER" >/dev/null 2>&1; then
        fail "Failed to establish persistent SSH control connection"
    fi
}

reset_ssh_mux_if_stale

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

read_local_version() {
    if [ -f "$LOCAL_VERSION_FILE" ]; then
        tr -d '[:space:]' < "$LOCAL_VERSION_FILE"
    else
        echo "0"
    fi
}

read_remote_version() {
    remote "
        if [ -f '$REMOTE_VERSION_FILE' ]; then
            tr -d '[:space:]' < '$REMOTE_VERSION_FILE'
        else
            echo '0'
        fi
    " 2>/dev/null || echo "0"
}

bump_version() {
    local current next
    current="$(read_local_version)"
    if [[ ! "$current" =~ ^[0-9]+$ ]]; then
        fail "Invalid version format in $LOCAL_VERSION_FILE: $current"
    fi
    next="$((current + 1))"
    printf '%s\n' "$next" > "$LOCAL_VERSION_FILE"
    echo "$next"
}

remote() {
    ssh $SSH_OPTS -t "$SERVER" "$@"
}

ensure_remote_system_packages() {
    remote "
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y
        apt-get install -y \
            ca-certificates \
            curl \
            git \
            nginx \
            postgresql \
            postgresql-contrib \
            python3 \
            python3-dev \
            python3-pip \
            python3-venv \
            build-essential \
            pkg-config
        systemctl enable nginx >/dev/null 2>&1 || true
    "
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
    ensure_ssh_mux
    ok "SSH session established (all further commands reuse this connection)"

    PREV_REMOTE_VERSION="$(read_remote_version)"
    NEXT_VERSION="$(bump_version)"
    ok "Version bump prepared: ${PREV_REMOTE_VERSION} -> ${NEXT_VERSION}"
    # ── 1. Sync files ─────────────────────────────────────────────────────────
    step "1/5" "Syncing files to production..."

    # Ensure target directories exist
    remote "mkdir -p $REMOTE_APP_DIR/src $REMOTE_APP_DIR/server $REMOTE_APP_DIR/deploy $REMOTE_ENV_DIR"

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

    # Sync env templates without touching live env/*.env files on the server
    do_rsync \
        --exclude='*.env' \
        "$LOCAL_ROOT/env/" "$SERVER:$REMOTE_ENV_DIR/"
    ok "env/ synced"

    # ── 2. Backup database ────────────────────────────────────────────────────
    step "2/5" "Backing up production database..."

    BACKUP_RESULT=$(remote "
        mkdir -p $BACKUP_DIR
        if [ ! -f '$REMOTE_PROD_ENV' ] && [ -f '$REMOTE_LEGACY_ENV' ]; then
            mkdir -p '$REMOTE_ENV_DIR'
            cp -p '$REMOTE_LEGACY_ENV' '$REMOTE_PROD_ENV'
        fi
        if [ -f '$REMOTE_PROD_ENV' ]; then
            set -a
            . '$REMOTE_PROD_ENV'
            set +a
            sudo -u postgres pg_dump racesense > '$BACKUP_DIR/racesense_\$(date +%F_%H%M%S).postgres.sql'
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
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y
        apt-get install -y postgresql postgresql-contrib
        if [ ! -x '$REMOTE_VENV/bin/pip' ]; then
            python3 -m venv '$REMOTE_VENV'
        fi
        $REMOTE_VENV/bin/pip install --quiet --upgrade pip 2>&1 | tail -1
        $REMOTE_VENV/bin/pip install --quiet -r $REMOTE_APP_DIR/server/requirements.txt 2>&1 | tail -1
    "
    ok "Dependencies up to date"

    # ── 4. Run database migrations ────────────────────────────────────────────
    step "4/5" "Running database migrations..."

    remote "
        bash '$REMOTE_APP_DIR/deploy/setup_postgres.sh'
        cd $REMOTE_APP_DIR/server
        source $REMOTE_VENV/bin/activate

        # Load env vars from production env file
        if [ ! -f '$REMOTE_PROD_ENV' ] && [ -f '$REMOTE_LEGACY_ENV' ]; then
            mkdir -p '$REMOTE_ENV_DIR'
            cp -p '$REMOTE_LEGACY_ENV' '$REMOTE_PROD_ENV'
        fi
        if [ -f '$REMOTE_PROD_ENV' ]; then
            set -a
            . '$REMOTE_PROD_ENV'
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
    echo -e "  ${GREEN}↺${NC} version upgrade ${PREV_REMOTE_VERSION} -> ${NEXT_VERSION}"
    echo -e "  ${CYAN}🕒${NC} time ${DEPLOY_MACHINE_TIME}"
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
    ensure_ssh_mux
    ok "SSH session established"

    PREV_REMOTE_VERSION="$(read_remote_version)"
    NEXT_VERSION="$(bump_version)"
    ok "Version bump prepared: ${PREV_REMOTE_VERSION} -> ${NEXT_VERSION}"
    # ── 1. Backup database ────────────────────────────────────────────────────
    step "1/6" "Backing up production database..."

    BACKUP_RESULT=$(remote "
        mkdir -p $BACKUP_DIR
        if [ ! -f '$REMOTE_PROD_ENV' ] && [ -f '$REMOTE_LEGACY_ENV' ]; then
            mkdir -p '$REMOTE_ENV_DIR'
            cp -p '$REMOTE_LEGACY_ENV' '$REMOTE_PROD_ENV'
        fi
        if [ -f '$REMOTE_PROD_ENV' ]; then
            set -a
            . '$REMOTE_PROD_ENV'
            set +a
            STAMP=\$(date +%F_%H%M%S)
            sudo -u postgres pg_dump racesense > '$BACKUP_DIR/nuke_backup_'\$STAMP'.postgres.sql'
            echo '$BACKUP_DIR/nuke_backup_'\$STAMP'.postgres.sql' > /tmp/racesense_last_backup
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

    # ── 2. Preserve production env ────────────────────────────────────────────
    step "2/6" "Preserving production env configuration..."

    ENV_RESULT=$(remote "
        if [ ! -f '$REMOTE_PROD_ENV' ] && [ -f '$REMOTE_LEGACY_ENV' ]; then
            mkdir -p '$REMOTE_ENV_DIR'
            cp -p '$REMOTE_LEGACY_ENV' '$REMOTE_PROD_ENV'
        fi
        if [ -f '$REMOTE_PROD_ENV' ]; then
            cp -p '$REMOTE_PROD_ENV' '/tmp/racesense_env_backup'
            echo 'ENV_OK'
        else
            echo 'NO_ENV'
        fi
    " 2>/dev/null) || true
    if echo "$ENV_RESULT" | grep -q 'ENV_OK'; then
        ok "production env preserved"
    else
        warn "No production env found"
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
        --exclude='*.env' \
        "$LOCAL_ROOT/env/" "$SERVER:$REMOTE_ENV_DIR/"
    ok "env/ deployed"

    # ── 5. Rebuild environment on server ──────────────────────────────────────
    step "5/6" "Rebuilding server environment..."

    ensure_remote_system_packages

    remote "
        mkdir -p '$REMOTE_ENV_DIR'

        # Restore production env (or create from template)
        if [ -f '/tmp/racesense_env_backup' ]; then
            cp -p '/tmp/racesense_env_backup' '$REMOTE_PROD_ENV'
            rm -f '/tmp/racesense_env_backup'
        elif [ -f '$REMOTE_ENV_DIR/production.env.example' ]; then
            cp '$REMOTE_ENV_DIR/production.env.example' '$REMOTE_PROD_ENV'
        fi

        if [ -f '$REMOTE_PROD_ENV' ] && grep -q '^JWT_SECRET_KEY=CHANGE_ME' '$REMOTE_PROD_ENV'; then
            JWT_SECRET=\$(python3 -c 'import secrets; print(secrets.token_hex(32))')
            sed -i \"s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=\$JWT_SECRET/\" '$REMOTE_PROD_ENV'
        fi

        # Recreate venv and install deps
        python3 -m venv $REMOTE_VENV
        $REMOTE_VENV/bin/pip install --quiet --upgrade pip 2>&1 | tail -1
        $REMOTE_VENV/bin/pip install --quiet -r $REMOTE_APP_DIR/server/requirements.txt 2>&1 | tail -1

        # Ensure data directory exists
        mkdir -p $REMOTE_APP_DIR/server/data
        mkdir -p $REMOTE_APP_DIR/server/instance

        # Restore database backup path for later
        BACKUP_PATH=\$(cat /tmp/racesense_last_backup 2>/dev/null || echo '')

        bash '$REMOTE_APP_DIR/deploy/setup_postgres.sh'

        # Run migrations
        cd $REMOTE_APP_DIR/server
        source $REMOTE_VENV/bin/activate
        if [ -f '$REMOTE_PROD_ENV' ]; then
            set -a
            . '$REMOTE_PROD_ENV'
            set +a
        fi
        export FLASK_APP=run
        flask db upgrade

        if [[ \"\$BACKUP_PATH\" == *.postgres.sql ]] && [ -f \"\$BACKUP_PATH\" ]; then
            sudo -u postgres psql racesense < \"\$BACKUP_PATH\"
        fi

        # Ensure log directory exists
        mkdir -p /var/log/racesense
        systemctl enable nginx >/dev/null 2>&1 || true
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
    echo -e "  ${GREEN}↺${NC} version upgrade ${PREV_REMOTE_VERSION} -> ${NEXT_VERSION}"
    echo -e "  ${CYAN}🕒${NC} time ${DEPLOY_MACHINE_TIME}"
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
