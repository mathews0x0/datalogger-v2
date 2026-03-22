#!/bin/bash

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/racesense}"
ENV_DIR="$APP_DIR/env"
ENV_FILE="$ENV_DIR/production.env"
LEGACY_ENV_FILE="$APP_DIR/.env"
DB_NAME="${RACESENSE_DB_NAME:-racesense}"
DB_USER="${RACESENSE_DB_USER:-racesense}"
DB_HOST="${RACESENSE_DB_HOST:-127.0.0.1}"
DB_PORT="${RACESENSE_DB_PORT:-5432}"

mkdir -p "$ENV_DIR"

if [ ! -f "$ENV_FILE" ] && [ -f "$LEGACY_ENV_FILE" ]; then
    cp "$LEGACY_ENV_FILE" "$ENV_FILE"
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
fi

systemctl enable --now postgresql >/dev/null 2>&1

if [[ "${DATABASE_URL:-}" == postgresql* ]] || [[ "${DATABASE_URL:-}" == postgres* ]]; then
    echo "DATABASE_URL already points to PostgreSQL; leaving it unchanged."
    exit 0
fi

DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';
    ELSE
        ALTER ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';
    END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
    sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

NEW_DATABASE_URL="postgresql+psycopg://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

python3 - "$ENV_FILE" "$NEW_DATABASE_URL" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
new_url = sys.argv[2]

if env_path.exists():
    lines = env_path.read_text().splitlines()
else:
    lines = []

updated = False
for index, line in enumerate(lines):
    if line.startswith("DATABASE_URL="):
        lines[index] = f"DATABASE_URL={new_url}"
        updated = True
        break

if not updated:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"DATABASE_URL={new_url}")

env_path.write_text("\n".join(lines) + "\n")
PY

echo "Configured PostgreSQL and updated DATABASE_URL in $ENV_FILE"
