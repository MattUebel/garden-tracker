#!/usr/bin/env python3
"""
Migration Utility Script for Garden Tracker

This script provides a convenient way to manage database migrations when running
the application in Docker containers. It handles common migration operations like:
- Creating new migrations based on model changes
- Applying migrations to the database
- Showing current migration status
- Rolling back migrations

Usage:
    python scripts/migration_tool.py <command> [options]

Commands:
    generate <message>  - Generate a new migration with the given message
    upgrade [revision]  - Apply migrations (to the specified revision, or "head" by default)
    downgrade <revision> - Rollback migrations to the specified revision
    status              - Show current migration status
    history             - Show migration history
    current             - Show current migration revision
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Ensure we're in the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

def check_docker_running():
    """Check if Docker is running and the required containers are up."""
    # First check if Docker service is running
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Docker is not running or not installed.")
        print("Please make sure Docker is installed and running.")
        sys.exit(1)
    
    # Check if our containers are running
    result = subprocess.run(
        ["docker", "compose", "ps", "--services", "--filter", "status=running"],
        capture_output=True,
        text=True
    )
    
    if "app" not in result.stdout:
        print("Error: The app container is not running.")
        print("Please start the containers with 'docker compose up -d' first.")
        sys.exit(1)
        
    if "db" not in result.stdout:
        print("Error: The database container is not running.")
        print("Please start the containers with 'docker compose up -d' first.")
        sys.exit(1)
    
    print("Docker is running and containers are up!")

def run_in_docker(command):
    """Run a command in the Docker container and return its output."""
    docker_cmd = [
        "docker", "compose", "exec",
        "-T",  # Disable pseudo-TTY allocation
        "app", "bash", "-c", command
    ]
    
    print(f"Running in Docker: {command}")
    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error executing command: {command}")
        print(f"STDERR: {result.stderr}")
        sys.exit(result.returncode)
    
    return result.stdout.strip()

def generate_migration(message):
    """Generate a new migration based on model changes."""
    # Clean __pycache__ directories to ensure up-to-date models are used
    run_in_docker("find . -name '__pycache__' -exec rm -rf {} +")
    
    # Generate the migration
    output = run_in_docker(f"alembic revision --autogenerate -m '{message}'")
    print(output)
    
    print("\nMigration file created successfully!")
    print("Don't forget to review the migration file before applying it.")

def upgrade(revision="head"):
    """Apply migrations to the database."""
    output = run_in_docker(f"alembic upgrade {revision}")
    print(output)
    print("\nDatabase upgraded successfully!")

def downgrade(revision):
    """Roll back migrations to a specific revision."""
    output = run_in_docker(f"alembic downgrade {revision}")
    print(output)
    print(f"\nDatabase downgraded to {revision} successfully!")

def show_status():
    """Show current migration status."""
    output = run_in_docker("alembic current")
    current = output.strip()
    
    history = run_in_docker("alembic history")
    
    print("Current revision:", current)
    print("\nMigration History:")
    print(history)

def show_history():
    """Show migration history."""
    output = run_in_docker("alembic history --verbose")
    print(output)

def show_current():
    """Show current migration revision."""
    output = run_in_docker("alembic current")
    print("Current revision:", output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garden Tracker Migration Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Generate command
    generate_parser = subparsers.add_parser("generate", help="Generate a new migration")
    generate_parser.add_argument("message", help="Migration message")
    
    # Upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Apply migrations")
    upgrade_parser.add_argument("revision", nargs="?", default="head", help="Target revision (default: head)")
    
    # Downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Rollback migrations")
    downgrade_parser.add_argument("revision", help="Target revision")
    
    # Status command
    subparsers.add_parser("status", help="Show migration status")
    
    # History command
    subparsers.add_parser("history", help="Show migration history")
    
    # Current command
    subparsers.add_parser("current", help="Show current revision")
    
    args = parser.parse_args()
    
    # Make sure Docker is running before proceeding
    check_docker_running()
    
    # Run the appropriate command
    if args.command == "generate":
        generate_migration(args.message)
    elif args.command == "upgrade":
        upgrade(args.revision)
    elif args.command == "downgrade":
        downgrade(args.revision)
    elif args.command == "status":
        show_status()
    elif args.command == "history":
        show_history()
    elif args.command == "current":
        show_current()
    else:
        parser.print_help()