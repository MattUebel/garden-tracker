#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit 1
fi

# Check if Docker and Docker Compose are available
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not running. Please start Docker first."
    exit 1
fi

# Set variables
SERVICE_NAME="garden-tracker"
APP_PATH="$(pwd)"

echo "Updating Garden Tracker service..."

# Stop the service
echo "Stopping service..."
systemctl stop $SERVICE_NAME

# Update code from repository
echo "Pulling latest code..."
# Switch to current user to avoid git permission issues
sudo -u $(logname) git pull

# Ensure Docker Compose services are running
echo "Ensuring Docker services are running..."
if ! docker compose ps --status running | grep -q "app"; then
    echo "Starting Docker services..."
    docker compose up -d
    # Wait for app to be ready
    sleep 10
fi

# Run database migrations
echo "Running database migrations..."

# First check if garden_supplies table exists to determine if this is a pre-existing database
TABLES_EXIST=$(docker compose exec db psql -U garden_user -d garden_db -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'garden_supplies');")

if [[ $TABLES_EXIST == *"t"* ]]; then
    echo "Existing database detected. Checking schema..."
    
    # Drop alembic_version if it exists to ensure clean state
    docker compose exec db psql -U garden_user -d garden_db -c "DROP TABLE IF EXISTS alembic_version;"
    
    # Add missing columns if they don't exist
    echo "Adding any missing columns..."
    docker compose exec db psql -U garden_user -d garden_db -c "
        DO \$\$
        BEGIN
            BEGIN
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS variety VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS description VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS planting_instructions VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS days_to_germination INTEGER;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS spacing VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS sun_exposure VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS soil_type VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS watering VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS fertilizer VARCHAR;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS package_weight FLOAT;
                ALTER TABLE seed_packets ADD COLUMN IF NOT EXISTS expiration_date DATE;
            EXCEPTION WHEN OTHERS THEN
                -- If there's an error, log it but continue
                RAISE NOTICE 'Error adding columns: %', SQLERRM;
            END;
        END \$\$;"
    
    # Now stamp at head since we've ensured all columns exist
    docker compose exec app alembic stamp head || {
        echo "Error stamping database version"
        exit 1
    }
    
    echo "Migration state initialized and schema updated"
else
    echo "Fresh database. Running all migrations..."
    docker compose exec app alembic upgrade head || {
        echo "Error running migrations"
        exit 1
    }
fi

# Start the service (which will rebuild due to --build flag in setup)
echo "Starting service..."
systemctl start $SERVICE_NAME

# Wait a moment for the service to start
sleep 5

# Check service status
echo "Checking service status..."
systemctl status $SERVICE_NAME --no-pager

echo ""
echo "Update complete!"
echo "Use 'journalctl -u ${SERVICE_NAME} -f' to follow the logs"