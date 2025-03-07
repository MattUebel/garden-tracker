#!/bin/bash

# Variables
BACKUP_PATH="${BACKUP_PATH:-/var/backups/garden-tracker}"
DATE=$(date +%Y%m%d)
DB_BACKUP_FILE="${BACKUP_PATH}/garden_tracker_db_${DATE}.sql"
IMAGES_BACKUP_FILE="${BACKUP_PATH}/garden_tracker_images_${DATE}.tar.gz"

# Ensure backup directory exists
mkdir -p $BACKUP_PATH

# Backup database
echo "Creating database backup..."
docker compose exec db pg_dump -U garden_user garden_db > "$DB_BACKUP_FILE"

# Backup images
echo "Creating images backup..."
tar -czf "$IMAGES_BACKUP_FILE" -C data uploads/

# Remove backups older than 5 days
echo "Cleaning up old backups..."
find "$BACKUP_PATH" -name "garden_tracker_db_*.sql" -mtime +5 -delete
find "$BACKUP_PATH" -name "garden_tracker_images_*.tar.gz" -mtime +5 -delete

echo "Backup complete!"
echo "Database backup: $DB_BACKUP_FILE"
echo "Images backup: $IMAGES_BACKUP_FILE"