import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

# Create logs directory if it doesn't exist
log_dir = Path("app/logs")
log_dir.mkdir(exist_ok=True)

# Configure logging
def setup_logging(log_level=logging.INFO):
    # Create formatters
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)

    # File handlers
    app_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    app_handler.setFormatter(file_formatter)
    app_handler.setLevel(log_level)

    error_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    error_handler.setFormatter(file_formatter)
    error_handler.setLevel(logging.ERROR)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)

    # FastAPI logger configuration
    fastapi_logger = logging.getLogger("fastapi")
    fastapi_logger.setLevel(log_level)

    # SQLAlchemy logger configuration
    sqlalchemy_logger = logging.getLogger("sqlalchemy")
    sqlalchemy_logger.setLevel(logging.WARNING)  # Only log SQLAlchemy warnings and errors

    return root_logger

# Custom error response model
class ErrorResponse:
    def __init__(self, status_code: int, message: str, details: dict = None):
        self.status_code = status_code
        self.body = {
            "error": {
                "code": status_code,
                "message": message,
                "details": details or {}
            }
        }