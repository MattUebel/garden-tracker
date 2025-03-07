from typing import Optional
from datetime import datetime
from app.schemas import GardenBaseModel
from app.schemas.plants import PlantInHarvest

class HarvestBase(GardenBaseModel):
    weight_oz: float
    plant_id: int

class HarvestCreate(HarvestBase):
    pass

class Harvest(HarvestBase):
    id: int
    timestamp: datetime
    plant: PlantInHarvest