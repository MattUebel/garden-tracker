from typing import Optional, Dict, Any, List
from datetime import datetime
from app.schemas import GardenBaseModel

class ImageBase(GardenBaseModel):
    file_path: str
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    ocr_processed: Optional[int] = 0

class ImageCreate(ImageBase):
    pass

class Image(ImageBase):
    id: int
    ocr_text: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None