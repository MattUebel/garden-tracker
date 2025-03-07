from typing import Optional
from datetime import datetime
from app.schemas import GardenBaseModel

class NoteBase(GardenBaseModel):
    body: str
    image_path: Optional[str] = None
    plant_id: Optional[int] = None
    seed_packet_id: Optional[int] = None
    garden_supply_id: Optional[int] = None

class NoteCreate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    timestamp: datetime