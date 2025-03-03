# Garden Tracker Service Setup

This directory contains scripts for setting up the Garden Tracker application as a systemd service on a Raspberry Pi.

## Prerequisites

- Raspberry Pi running a recent version of Raspberry Pi OS (or other Linux distribution with systemd)
- Docker and Docker Compose installed
- Root access (sudo)

## Setup Instructions

1. Ensure Docker is installed and running:
   ```bash
   sudo systemctl status docker
   ```

2. Clone the repository and navigate to the project directory:
   ```bash
   cd garden-tracker
   ```

3. Run the setup script as root:
   ```bash
   sudo ./scripts/setup_service.sh
   ```

## What the Setup Script Does

1. Creates a systemd service that:
   - Starts the application using Docker Compose
   - Automatically restarts on failure
   - Starts on boot
   - Runs under your user account (not root)

2. Sets up daily database backups:
   - Creates a backup script at `scripts/backup_db.sh`
   - Configures a cronjob to run at midnight daily
   - Stores backups in `/var/backups/garden-tracker/`
   - Maintains 5 days of backup history

## Verification

After running the script, you can verify the setup:

1. Check the service status:
   ```bash
   sudo systemctl status garden-tracker
   ```

2. Check that the backup directory exists:
   ```bash
   ls /var/backups/garden-tracker
   ```

3. View your crontab to confirm the backup schedule:
   ```bash
   crontab -l
   ```

## Troubleshooting

- View service logs:
  ```bash
  journalctl -u garden-tracker
  ```

- If the service fails to start, check:
  - Docker service status: `systemctl status docker`
  - Application logs: `docker compose logs`
  - File permissions in the backup directory

## Manual Backup

To manually trigger a database backup:
```bash
./scripts/backup_db.sh
```