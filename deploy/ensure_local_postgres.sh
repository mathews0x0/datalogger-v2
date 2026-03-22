#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/env/development.env}"

if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL must be set in $ENV_FILE"
    exit 1
fi

eval "$(
python3 - "$DATABASE_URL" <<'PY'
import shlex
import sys
from urllib.parse import urlparse, unquote

database_url = sys.argv[1]
parsed = urlparse(database_url)

if parsed.scheme not in {"postgresql", "postgres", "postgresql+psycopg"}:
    raise SystemExit(0)

db_name = parsed.path.lstrip("/")
if not db_name:
    raise SystemExit("DATABASE_URL must include a database name")

values = {
    "DB_HOST": parsed.hostname or "127.0.0.1",
    "DB_PORT": str(parsed.port or 5432),
    "DB_USER": unquote(parsed.username or "postgres"),
    "DB_PASSWORD": unquote(parsed.password or ""),
    "DB_NAME": unquote(db_name),
}

for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

if ! command -v psql >/dev/null 2>&1; then
    echo "psql is required to ensure the local PostgreSQL database exists."
    exit 1
fi

if ! command -v createdb >/dev/null 2>&1; then
    echo "createdb is required to create the local PostgreSQL database."
    exit 1
fi

export PGPASSWORD="$DB_PASSWORD"

if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
    echo "Database '$DB_NAME' already exists."
else
    createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
    echo "Created database '$DB_NAME'."
fi
