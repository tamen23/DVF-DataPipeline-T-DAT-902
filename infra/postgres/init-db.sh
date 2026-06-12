#!/bin/bash
# Runs once on first boot of the postgres container.
# Creates the PostGIS extension on the serving DB and a separate
# database for the Airflow metadata.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS postgis;

    CREATE USER $AIRFLOW_DB_USER WITH PASSWORD '$AIRFLOW_DB_PASSWORD';
    CREATE DATABASE $AIRFLOW_DB_NAME OWNER $AIRFLOW_DB_USER;
EOSQL
