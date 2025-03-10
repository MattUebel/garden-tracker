from sqlalchemy import Column, Integer, String, DateTime, Table, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base

# Association table for many-to-many relationship between plants and supplies
plant_supplies = Table('plant_supplies', Base.metadata,
    Column('plant_id', Integer, ForeignKey('plants.id'), primary_key=True),
    Column('supply_id', Integer, ForeignKey('garden_supplies.id'), primary_key=True)
)

class GardenSupply(Base):
    __tablename__ = "garden_supplies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    image_path = Column(String, nullable=True)  # Legacy field, to be migrated
    description = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Relationships
    notes = relationship("Note", backref="garden_supply")
    images = relationship("Image", secondary="garden_supply_image", back_populates="garden_supplies")

    def __repr__(self):
        return f"<GardenSupply {self.name}>"