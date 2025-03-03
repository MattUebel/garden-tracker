from fastapi import HTTPException
from typing import Any, Dict, Optional

class GardenBaseException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or str(status_code)
        self.details = details or {}

class ResourceNotFoundException(GardenBaseException):
    def __init__(self, resource_type: str, resource_id: Any):
        super().__init__(
            status_code=404,
            detail=f"{resource_type} with id {resource_id} not found",
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": str(resource_id)}
        )

class ValidationException(GardenBaseException):
    def __init__(self, detail: str, field_errors: Dict[str, str] = None):
        super().__init__(
            status_code=400,
            detail=detail,
            error_code="VALIDATION_ERROR",
            details={"field_errors": field_errors or {}}
        )

class FileUploadException(GardenBaseException):
    def __init__(self, detail: str, filename: Optional[str] = None):
        super().__init__(
            status_code=400,
            detail=detail,
            error_code="FILE_UPLOAD_ERROR",
            details={"filename": filename} if filename else {}
        )

class DatabaseOperationException(GardenBaseException):
    def __init__(self, operation: str, detail: str):
        super().__init__(
            status_code=500,
            detail=f"Database {operation} failed: {detail}",
            error_code="DATABASE_ERROR",
            details={"operation": operation}
        )