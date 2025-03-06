"""
Configuration module for Garden Tracker application.
Handles environment variables with proper validation.
"""
import os
import sys
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
load_dotenv()

class ConfigurationError(Exception):
    """Raised when there's an error in the application configuration."""
    pass

# Database configuration
def get_database_url():
    """Get database URL with fallbacks and validation"""
    # First try DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return database_url
    
    # Fall back to individual components
    host = os.getenv('POSTGRES_HOST', 'db')
    user = os.getenv('POSTGRES_USER')
    password = os.getenv('POSTGRES_PASSWORD')
    db = os.getenv('POSTGRES_DB')
    
    if not all([user, password, db]):
        logger.warning("Missing some database configuration values. Using defaults.")
        # Use default values as fallback
        user = user or 'garden_user'
        password = password or 'mygarden'
        db = db or 'garden_db'
    
    return f"postgresql://{user}:{password}@{host}:5432/{db}"

# API Keys
def get_mistral_api_key():
    """Get Mistral API key with validation"""
    api_key = os.getenv('MISTRAL_API_KEY')
    return api_key  # Can be None, will be checked when OCR feature is used

# Mistral API configuration
MISTRAL_OCR_MODEL = "mistral-ocr-latest"
MISTRAL_CHAT_MODEL = os.getenv('MISTRAL_CHAT_MODEL', 'mistral-small-latest')

# Function to validate essential configuration at startup
def validate_configuration():
    """Validate all required configuration settings and exit if critical ones are missing."""
    critical_errors = []
    warnings = []
    
    # Check database configuration - not critical as we have fallbacks
    database_url = get_database_url()
    if 'mygarden' in database_url:
        warnings.append("Using default database credentials. Consider setting POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB environment variables.")
    
    # Check Mistral API (warning only as this is a feature-specific requirement)
    if not get_mistral_api_key():
        warnings.append("MISTRAL_API_KEY is not set. OCR functionality for seed packets will be disabled.")
    
    # Add any other environment variables that need to be checked
    # Example: if not os.getenv('ANOTHER_REQUIRED_VAR'):
    #     critical_errors.append("ANOTHER_REQUIRED_VAR is not set.")
    
    # Handle warnings
    for warning in warnings:
        logger.warning(f"Configuration warning: {warning}")
    
    # Exit if there are any critical errors
    if critical_errors:
        for error in critical_errors:
            logger.error(f"Configuration error: {error}")
        logger.error("Application cannot start due to configuration errors.")
        sys.exit(1)
    
    return True

# Application configuration
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key_for_development_only')
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'app/static/uploads')

# Export database URL for use in other modules
SQLALCHEMY_DATABASE_URL = get_database_url()

# Validate configuration when this module is imported
validate_configuration()