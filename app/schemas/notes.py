from typing import Optional, List
from datetime import datetime
from app.schemas import GardenBaseModel
from app.schemas.images import Image

class NoteBase(GardenBaseModel):
    body: str
    image_path: Optional[str] = None  # Legacy field for backward compatibility
    plant_id: Optional[int] = None
    seed_packet_id: Optional[int] = None
    garden_supply_id: Optional[int] = None

class NoteCreate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    timestamp: datetime
    images: List[Image] = []  # New field for multiple images
    
    # Property to ensure backward compatibility with templates
    @property
    def primary_image_path(self) -> Optional[str]:
        """Returns either the legacy image_path or the path of the first image in the new images relationship."""
        if self.image_path:
            return self.image_path
        elif self.images and len(self.images) > 0:
            return self.images[0].file_path
        return None