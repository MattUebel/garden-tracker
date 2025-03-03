from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, func
from .base import Base

class Harvest(Base):
    __tablename__ = "harvests"

    id = Column(Integer, primary_key=True)
    weight_oz = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=func.now())
    
    # Foreign Key
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=False)

    def __repr__(self):
        return f"<Harvest {self.id} - {self.weight_oz}oz>"