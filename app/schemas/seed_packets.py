from typing import Optional, List, ForwardRef, TYPE_CHECKING
from datetime import date, datetime
from app.schemas import GardenBaseModel

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
    fertilizer: Optional[str] = None
    package_weight: Optional[float] = None
    expiration_date: Optional[date] = None
    quantity: int
    image_path: Optional[str] = None

class SeedPacketCreate(SeedPacketBase):
    pass

class SeedPacket(SeedPacketBase):
    id: int
    created_at: datetime
    updated_at: datetime
    plants: List[PlantRef]
    notes: List[NoteRef]