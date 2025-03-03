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

# Create systemd service file if it doesn't exist or has changed
cat > /tmp/${SERVICE_NAME}.service << EOL
[Unit]
Description=Garden Tracker Application
Requires=docker.service
After=docker.service

[Service]
Type=simple
WorkingDirectory=${APP_PATH}
ExecStart=${DOCKER_COMPOSE_PATH} up
ExecStop=${DOCKER_COMPOSE_PATH} down
Restart=always
User=$(logname)

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

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_PATH" ]; then
  mkdir -p $BACKUP_PATH
  chown $(logname):$(logname) $BACKUP_PATH
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

# Create backup using detected docker path
${DOCKER_PATH} exec \$CONTAINER_NAME pg_dump -U postgres garden_tracker > \$BACKUP_FILE

# Remove backups older than 5 days
find \$BACKUP_PATH -name "garden_tracker_*.sql" -mtime +5 -delete
EOL

# Make backup script executable
chmod +x $BACKUP_SCRIPT

# Add backup cron job if it doesn't exist
CRON_JOB="0 0 * * * ${BACKUP_SCRIPT}"
if ! crontab -l -u $(logname) 2>/dev/null | grep -q "${BACKUP_SCRIPT}"; then
  (crontab -l -u $(logname) 2>/dev/null; echo "$CRON_JOB") | crontab -u $(logname) -
  echo "Added backup cron job"
else
  echo "Backup cron job already exists"
fi

# Create required Docker volumes if they don't exist
docker volume create garden_uploads 2>/dev/null || true
docker volume create postgres_data 2>/dev/null || true

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
echo "- View application logs: docker compose logs"