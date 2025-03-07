from typing import Optional
from datetime import datetime
from app.schemas import GardenBaseModel

class GardenSupplyBase(GardenBaseModel):
    name: str
    description: Optional[str] = None
    image_path: Optional[str] = None

class GardenSupplyCreate(GardenSupplyBase):
    pass

class GardenSupply(GardenSupplyBase):
    id: int
    created_at: datetime
    updated_at: datetime