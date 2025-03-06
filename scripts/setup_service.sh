#!/bin/bash

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit 1
fi

# Set variables
SERVICE_NAME="garden-tracker"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
APP_PATH="$(pwd)"
BACKUP_PATH="/var/backups/${SERVICE_NAME}"
BACKUP_SCRIPT="${APP_PATH}/scripts/backup_db.sh"
CURRENT_USER=$(logname)

# Check for .env file or environment variables
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
  
  echo "Required environment variables found. Continuing with setup..."
  
  # Create .env file from environment variables for the service
  echo "Creating .env file from environment variables..."
  echo "MISTRAL_API_KEY=${MISTRAL_API_KEY}" > $ENV_FILE
  chown $CURRENT_USER:$CURRENT_USER $ENV_FILE
  chmod 600 $ENV_FILE
fi

# Find docker and docker compose executables
DOCKER_PATH=$(which docker)
if [ -z "$DOCKER_PATH" ]; then
    echo "Docker not found. Please install Docker first."
    exit 1
fi

DOCKER_COMPOSE_PATH="${DOCKER_PATH} compose"
if ! $DOCKER_PATH compose version >/dev/null 2>&1; then
    echo "Docker Compose not found. Please install Docker Compose first."
    exit 1
fi

echo "Setting up Garden Tracker service..."
echo "Using Docker from: $DOCKER_PATH"

# Create systemd service file
cat > /tmp/${SERVICE_NAME}.service << EOL
[Unit]
Description=Garden Tracker Application
Requires=docker.service
After=docker.service

[Service]
Type=simple
WorkingDirectory=${APP_PATH}
# Use sudo for Docker commands
ExecStart=/usr/bin/sudo ${DOCKER_COMPOSE_PATH} up --build
ExecStop=/usr/bin/sudo ${DOCKER_COMPOSE_PATH} down
Restart=always
User=${CURRENT_USER}

[Install]
WantedBy=multi-user.target
EOL

# Only update service file if it's different
if ! cmp -s /tmp/${SERVICE_NAME}.service $SERVICE_PATH; then
  mv /tmp/${SERVICE_NAME}.service $SERVICE_PATH
  echo "Service file updated"
  RELOAD_NEEDED=true
else
  rm /tmp/${SERVICE_NAME}.service
  echo "Service file unchanged"
fi

# Configure sudo to allow docker compose without password
SUDOERS_FILE="/etc/sudoers.d/garden-tracker"
cat > $SUDOERS_FILE << EOL
# Allow garden-tracker service to use docker compose without password
${CURRENT_USER} ALL=(ALL) NOPASSWD: ${DOCKER_PATH} compose *
EOL
chmod 440 $SUDOERS_FILE

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_PATH" ]; then
  mkdir -p $BACKUP_PATH
  chown $CURRENT_USER:$CURRENT_USER $BACKUP_PATH
  echo "Created backup directory"
fi

# Create backup script
cat > $BACKUP_SCRIPT << EOL
#!/bin/bash

# Variables
BACKUP_PATH="${BACKUP_PATH}"
CONTAINER_NAME="${SERVICE_NAME}-db-1"
DATE=\$(date +%Y%m%d)
BACKUP_FILE="\${BACKUP_PATH}/garden_tracker_\${DATE}.sql"

# Ensure backup directory exists
mkdir -p \$BACKUP_PATH

# Create backup using sudo and detected docker path
sudo ${DOCKER_PATH} exec \$CONTAINER_NAME pg_dump -U postgres garden_tracker > \$BACKUP_FILE

# Remove backups older than 5 days
find \$BACKUP_PATH -name "garden_tracker_*.sql" -mtime +5 -delete
EOL

# Make backup script executable
chmod +x $BACKUP_SCRIPT
chown $CURRENT_USER:$CURRENT_USER $BACKUP_SCRIPT

# Configure sudo for backup script
cat >> $SUDOERS_FILE << EOL

# Allow garden-tracker backup script to use docker without password
${CURRENT_USER} ALL=(ALL) NOPASSWD: ${DOCKER_PATH} exec ${SERVICE_NAME}-db-1 pg_dump *
EOL

# Add backup cron job if it doesn't exist
CRON_JOB="0 0 * * * ${BACKUP_SCRIPT}"
if ! crontab -l -u $CURRENT_USER 2>/dev/null | grep -q "${BACKUP_SCRIPT}"; then
  (crontab -l -u $CURRENT_USER 2>/dev/null; echo "$CRON_JOB") | crontab -u $CURRENT_USER -
  echo "Added backup cron job"
else
  echo "Backup cron job already exists"
fi

# Create required Docker volumes if they don't exist
sudo $DOCKER_PATH volume create garden_uploads 2>/dev/null || true
sudo $DOCKER_PATH volume create postgres_data 2>/dev/null || true

# Setup service
if [ "$RELOAD_NEEDED" = true ] || ! systemctl is-active --quiet $SERVICE_NAME; then
  systemctl daemon-reload
  systemctl enable $SERVICE_NAME
  systemctl restart $SERVICE_NAME
  echo "Service restarted"
else
  echo "Service already running, no restart needed"
fi

echo ""
echo "Setup complete!"
echo "Service is running and will start automatically on boot"
echo "Database backups will run daily at midnight and keep 5 days of history in ${BACKUP_PATH}"
echo ""
echo "Useful commands:"
echo "- Check service status: systemctl status ${SERVICE_NAME}"
echo "- View logs: journalctl -u ${SERVICE_NAME}"
echo "- Start service: systemctl start ${SERVICE_NAME}"
echo "- Stop service: systemctl stop ${SERVICE_NAME}"
echo "- Restart service: systemctl restart ${SERVICE_NAME}"
echo "- View application logs: sudo docker compose logs"