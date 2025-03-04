#!/bin/bash

# Replace environment variables in the SQL file
envsubst < /docker-entrypoint-initdb.d/init-db.sql > /tmp/init-db-processed.sql

# Run the processed SQL file
psql -U "$POSTGRES_USER" -f /tmp/init-db-processed.sql

# Clean up
rm /tmp/init-db-processed.sql