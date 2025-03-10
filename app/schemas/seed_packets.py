from typing import Optional, List, ForwardRef, TYPE_CHECKING
from datetime import date, datetime
from app.schemas import GardenBaseModel
from app.schemas.images import Image

# Use conditional imports to avoid circular dependencies
if TYPE_CHECKING:
    from app.schemas.plants import Plant
    from app.schemas.notes import Note

# Forward references for circular dependencies
PlantRef = ForwardRef('Plant')
NoteRef = ForwardRef('Note')

class SeedPacketBase(GardenBaseModel):
    name: str
    variety: Optional[str] = None
    description: Optional[str] = None
    planting_instructions: Optional[str] = None
    days_to_germination: Optional[int] = None
    spacing: Optional[str] = None
    sun_exposure: Optional[str] = None
    soil_type: Optional[str] = None
    watering: Optional[str] = None
    quantity: int
    image_path: Optional[str] = None  # Legacy field for backward compatibility

class SeedPacketCreate(SeedPacketBase):
    pass

class SeedPacket(SeedPacketBase):
    id: int
    created_at: datetime
    updated_at: datetime
    plants: List[PlantRef] = []
    notes: List[NoteRef] = []
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