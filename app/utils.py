import os
import logging
from fastapi import UploadFile, HTTPException
from pathlib import Path
import shutil
from uuid import uuid4
from typing import Optional, Dict, Any
from datetime import datetime
import imghdr
from sqlalchemy.orm import Query
from .exceptions import FileUploadException, ValidationException
from .config import UPLOAD_FOLDER

logger = logging.getLogger(__name__)

# Use the upload folder from config
UPLOAD_DIR = Path(UPLOAD_FOLDER)
ALLOWED_IMAGE_TYPES = {"jpeg", "jpg", "png", "gif"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def validate_image(file: UploadFile) -> bool:
    """
    Validate that the uploaded file is actually an image
    Raises FileUploadException if validation fails
    """
    try:
        # Check content type
        content_type = file.content_type
        if not content_type.startswith("image/"):
            raise FileUploadException(
                detail="File must be an image",
                filename=file.filename
            )
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if size > MAX_FILE_SIZE:
            raise FileUploadException(
                detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE/1024/1024}MB",
                filename=file.filename
            )
        
        # Read first chunk to validate actual file content
        contents = file.file.read(1024)  # Read first 1KB
        file.file.seek(0)  # Reset file pointer
        
        # Use imghdr to detect actual file type
        image_type = imghdr.what(None, h=contents)
        if not image_type or image_type not in ALLOWED_IMAGE_TYPES:
            raise FileUploadException(
                detail=f"Invalid image type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}",
                filename=file.filename
            )
        
        logger.debug(f"Image validation successful", extra={
            "filename": file.filename,
            "content_type": content_type,
            "size": size,
            "image_type": image_type
        })
        return True
        
    except FileUploadException:
        raise
    except Exception as e:
        logger.error(f"Error validating image", extra={
            "filename": file.filename,
            "error": str(e)
        })
        raise FileUploadException(
            detail="Error validating image file",
            filename=file.filename
        )

def ensure_upload_dir():
    """
    Ensure upload directory exists and is writable.
    Creates the directory if it doesn't exist.
    """
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        test_file = UPLOAD_DIR / ".test"
        test_file.touch()
        test_file.unlink()
        logger.debug("Upload directory verified", extra={"path": str(UPLOAD_DIR)})
    except Exception as e:
        logger.error(f"Error with upload directory", extra={
            "path": str(UPLOAD_DIR),
            "error": str(e)
        })
        raise FileUploadException(
            detail="Server is not properly configured for file uploads"
        )

def save_upload_file(file: UploadFile) -> Optional[str]:
    """
    Save an uploaded file to the filesystem
    Returns the relative path to the file, or None if save failed or no file provided
    """
    try:
        if not file or not file.filename:
            return None
            
        ensure_upload_dir()
        validate_image(file)
        
        # Generate unique filename with original extension
        ext = Path(file.filename).suffix if file.filename else ".jpg"
        filename = f"{uuid4()}{ext}"
        file_path = UPLOAD_DIR / filename
        
        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        relative_path = f"/static/uploads/{filename}"
        logger.info("File uploaded successfully", extra={
            "original_filename": file.filename,
            "saved_path": relative_path
        })
        return relative_path
        
    except FileUploadException:
        raise
    except Exception as e:
        logger.error("Error saving file", extra={
            "filename": file.filename if file else None,
            "error": str(e)
        })
        raise FileUploadException(
            detail="Error saving uploaded file",
            filename=file.filename if file else None
        )

def delete_upload_file(file_path: str) -> bool:
    """
    Delete a file from the filesystem
    Returns True if successful, False otherwise
    """
    try:
        if not file_path:
            return True
        
        # Convert URL path to filesystem path
        abs_path = Path("app") / file_path.lstrip("/")
        if abs_path.exists():
            abs_path.unlink()
            logger.info("File deleted successfully", extra={"path": file_path})
            return True
            
        logger.warning("File not found for deletion", extra={"path": file_path})
        return True
        
    except Exception as e:
        logger.error("Error deleting file", extra={
            "path": file_path,
            "error": str(e)
        })
        return False

def apply_filters(query: Query, model: Any, filters: Dict[str, Any]) -> Query:
    """
    Apply filters to a SQLAlchemy query based on a dictionary of filter parameters.
    Handles None values by skipping those filters.
    """
    try:
        for field, value in filters.items():
            if value is not None:
                if isinstance(value, list):
                    query = query.filter(getattr(model, field).in_(value))
                elif isinstance(value, (datetime, int, str)):
                    query = query.filter(getattr(model, field) == value)
                elif field.endswith('_min'):
                    actual_field = field[:-4]
                    query = query.filter(getattr(model, actual_field) >= value)
                elif field.endswith('_max'):
                    actual_field = field[:-4]
                    query = query.filter(getattr(model, actual_field) <= value)
        
        logger.debug("Filters applied successfully", extra={
            "model": model.__name__,
            "filters": filters
        })
        return query
        
    except Exception as e:
        logger.error("Error applying filters", extra={
            "model": model.__name__ if model else None,
            "filters": filters,
            "error": str(e)
        })
        raise ValidationException(
            detail="Error applying filters",
            field_errors={"filters": str(e)}
        )