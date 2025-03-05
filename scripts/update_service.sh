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

# Check if tables exist but alembic_version is missing
echo "Checking database state..."
TABLES_EXIST=$(docker compose exec db psql -U garden_user -d garden_db -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'garden_supplies');")
VERSION_EXISTS=$(docker compose exec db psql -U garden_user -d garden_db -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version');")

if [[ $TABLES_EXIST == *"t"* ]] && [[ $VERSION_EXISTS == *"f"* ]]; then
    echo "Tables exist but no version tracking. Creating version tracking..."
    # Create alembic_version table and stamp at initial migration
    docker compose exec app alembic stamp e3e3dce7551b || {
        echo "Error stamping initial version"
        exit 1
    }
fi

# Now run remaining migrations
echo "Running migrations..."
docker compose exec app alembic upgrade head || {
    echo "Error running migrations"
    exit 1
}

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