#!/bin/bash
# Runs once, on the first start of an empty PostgreSQL volume.
# Creates the Fineract application user and its two databases.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
  CREATE USER ${FINERACT_DB_USER} WITH PASSWORD '${FINERACT_DB_PASS}';
  CREATE DATABASE ${FINERACT_TENANTS_DB_NAME} OWNER ${FINERACT_DB_USER};
  CREATE DATABASE ${FINERACT_TENANT_DEFAULT_DB_NAME} OWNER ${FINERACT_DB_USER};
EOSQL
