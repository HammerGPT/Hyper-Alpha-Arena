#!/bin/bash
set -e

# Create additional database for snapshots
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create snapshots database if not exists
    SELECT 'CREATE DATABASE alpha_snapshots'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'alpha_snapshots')\gexec

    -- Grant all privileges to alpha_user
    GRANT ALL PRIVILEGES ON DATABASE alpha_snapshots TO alpha_user;
EOSQL

echo "✓ Databases initialized: alpha_arena, alpha_snapshots"
