#!/bin/sh
# Runs on every `docker compose up`, before the McLender API starts: creates (or keeps in step) the
# McLender database and its user, so an existing install gets it without wiping the PostgreSQL volume.
# Does nothing until MCLENDER_DB_PASSWORD is set in deploy/.env (the API then keeps sign-ins in memory).
set -eu

case "${MCLENDER_DB_PASSWORD:-}" in
  ""|change-me*)
    echo "MCLENDER_DB_PASSWORD is not set: skipping the McLender database (sign-ins stay in memory)."
    exit 0 ;;
esac

export PGPASSWORD="$POSTGRES_PASSWORD"
# Values come from the environment through \getenv and are quoted by psql (:"name", :'value'), so a quote in
# .env can't change the SQL, and the password never appears in a process list.
psql -v ON_ERROR_STOP=1 -h postgresql -U "$POSTGRES_USER" -d postgres <<'EOSQL'
\getenv pass MCLENDER_DB_PASSWORD
SELECT 'CREATE ROLE mclender LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mclender')\gexec
ALTER ROLE mclender WITH LOGIN PASSWORD :'pass';
SELECT 'CREATE DATABASE mclender OWNER mclender' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mclender')\gexec
EOSQL
echo "McLender database ready."
