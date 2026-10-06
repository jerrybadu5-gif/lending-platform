#!/bin/bash
# Runs once, on the first start of an empty PostgreSQL volume.
# Creates the Fineract application user and its two databases.
set -euo pipefail

# psql reads the values from the environment itself (\getenv, PostgreSQL 15+), so the password never
# appears in a process list, and quotes them (:"name" for names, :'value' for the password), so a quote
# or semicolon in .env can't change the SQL. The heredoc is quoted so the shell leaves it alone.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-'EOSQL'
  \getenv user FINERACT_DB_USER
  \getenv pass FINERACT_DB_PASS
  \getenv tenants_db FINERACT_TENANTS_DB_NAME
  \getenv default_db FINERACT_TENANT_DEFAULT_DB_NAME
  CREATE USER :"user" WITH PASSWORD :'pass';
  CREATE DATABASE :"tenants_db" OWNER :"user";
  CREATE DATABASE :"default_db" OWNER :"user";
EOSQL
