#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit 1
fi

# Check for .env file or environment variables
APP_PATH="$(pwd)"
ENV_FILE="${APP_PATH}/.env"
if [ -f "$ENV_FILE" ]; then
  echo "Found .env file at ${ENV_FILE}"
else
  # If .env doesn't exist, check for required environment variables
  echo "No .env file found. Checking for required environment variables..."
  
  # Check for Mistral API key
  if [ -z "${MISTRAL_API_KEY}" ]; then
    echo "ERROR: No .env file found and MISTRAL_API_KEY environment variable is not set."
    echo "Please either:"
    echo "  1. Create a .env file with MISTRAL_API_KEY=your_api_key in ${APP_PATH}, or"
    echo "  2. Set the MISTRAL_API_KEY environment variable before running this script"
    exit 1
  fi
  
  # Optional: You can check for other required environment variables here
  
  echo "Required environment variables found. Continuing with update..."
  
  # Create .env file from environment variables for the service
  echo "Creating .env file from environment variables..."
  echo "MISTRAL_API_KEY=${MISTRAL_API_KEY}" > $ENV_FILE
  chown $(logname):$(logname) $ENV_FILE
  chmod 600 $ENV_FILE
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