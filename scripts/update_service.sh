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

# Check if alembic_version exists
echo "Checking database state..."
VERSION_EXISTS=$(docker compose exec db psql -U garden_user -d garden_db -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version');")

if [[ $VERSION_EXISTS == *"f"* ]]; then
    echo "No version tracking table found. Initializing version tracking..."
    
    # Check if tables exist to determine starting point
    TABLES_EXIST=$(docker compose exec db psql -U garden_user -d garden_db -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'garden_supplies');")
    
    if [[ $TABLES_EXIST == *"t"* ]]; then
        echo "Tables already exist. Setting up version tracking at initial migration..."
        # Drop alembic_version if it exists (shouldn't, but just in case)
        docker compose exec db psql -U garden_user -d garden_db -c "DROP TABLE IF EXISTS alembic_version;"
        
        # First stamp at initial migration since tables exist
        docker compose exec app alembic stamp e3e3dce7551b || {
            echo "Error stamping initial version"
            exit 1
        }
        
        # Now stamp at current head to skip all migrations since tables exist
        docker compose exec app alembic stamp head || {
            echo "Error stamping at current version"
            exit 1
        }
        
        echo "Version tracking initialized at current version"
    else
        echo "Fresh database. Running all migrations..."
        docker compose exec app alembic upgrade head || {
            echo "Error running initial migrations"
            exit 1
        }
    fi
else
    echo "Version tracking exists. Running any pending migrations..."
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