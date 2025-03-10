from sqlalchemy import Column, Integer, String, DateTime, Date, Float, func
from sqlalchemy.orm import relationship
from .base import Base

class SeedPacket(Base):
    __tablename__ = "seed_packets"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    variety = Column(String, nullable=True)
    description = Column(String, nullable=True)
    planting_instructions = Column(String, nullable=True)
    days_to_germination = Column(Integer, nullable=True)
    spacing = Column(String, nullable=True)
    sun_exposure = Column(String, nullable=True)
    soil_type = Column(String, nullable=True)
    watering = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False)
    image_path = Column(String, nullable=True)  # Legacy field, to be migrated
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    notes = relationship("Note", backref="seed_packet")
    images = relationship("Image", secondary="seed_packet_image", back_populates="seed_packets")

    def __repr__(self):
        return f"<SeedPacket {self.name}>"