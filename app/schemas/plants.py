from typing import Optional
from datetime import datetime
from enum import Enum
from app.schemas import GardenBaseModel
from app.models.plant import PlantingMethod

class Year(GardenBaseModel):
    year: int

class PlantBase(GardenBaseModel):
    name: str
    variety: Optional[str] = None
    planting_method: PlantingMethod
    seed_packet_id: Optional[int] = None

class PlantCreate(PlantBase):
    pass

class Plant(PlantBase):
    id: int
    year_id: int
    created_at: datetime
    updated_at: datetime 
    year: Year

class PlantInHarvest(GardenBaseModel):
    id: int
    name: str
    variety: Optional[str] = None