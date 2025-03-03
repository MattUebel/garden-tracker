from sqlalchemy import Column, Integer, String, ForeignKey, Enum, DateTime, func
from sqlalchemy.orm import relationship
import enum
from .base import Base

class PlantingMethod(str, enum.Enum):
    RAISED_BED = "Raised Bed"
    SEEDLY_TRAY = "Seedly Tray"
    POT = "Pot"
    GROUND = "Ground"

    def __str__(self):
        return self.value

class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    variety = Column(String)  # New field
    planting_method = Column(Enum(PlantingMethod, native_enum=True, create_type=False), nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Foreign Keys
    year_id = Column(Integer, ForeignKey('years.year'), nullable=False)
    seed_packet_id = Column(Integer, ForeignKey('seed_packets.id'), nullable=True)
    
    # Relationships
    year = relationship("Year", backref="plants")
    seed_packet = relationship("SeedPacket", backref="plants")
    garden_supplies = relationship("GardenSupply", secondary="plant_supplies", backref="plants")
    notes = relationship("Note", backref="plant")
    harvests = relationship("Harvest", backref="plant")
    
    def __repr__(self):
        return f"<Plant {self.name}>"