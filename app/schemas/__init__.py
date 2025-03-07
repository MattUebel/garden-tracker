from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List, ForwardRef

# Base Pydantic configuration
class GardenBaseModel(BaseModel):
    class Config:
        from_attributes = True

# Function to update forward references after all models are imported
def update_forward_refs():
    from app.schemas.plants import Plant
    from app.schemas.notes import Note
    from app.schemas.seed_packets import SeedPacket
    
    # Update models with forward references
    SeedPacket.model_rebuild(force=True)