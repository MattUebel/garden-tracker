from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.schemas import GardenBaseModel
from app.models.plant import PlantingMethod
from app.schemas.images import Image

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
    images: List[Image] = []  # New field for multiple images
    
    # Property to ensure backward compatibility with templates
    @property
    def primary_image_path(self) -> Optional[str]:
        """Returns the path of the first image in the images relationship if any."""
        if self.images and len(self.images) > 0:
            return self.images[0].file_path
        return None

class PlantInHarvest(GardenBaseModel):
    id: int
    name: str
    variety: Optional[str] = None