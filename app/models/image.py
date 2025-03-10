from sqlalchemy import Column, Integer, String, ForeignKey, Table, Text, JSON, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

# Association tables for many-to-many relationships
seed_packet_image = Table(
    'seed_packet_image',
    Base.metadata,
    Column('seed_packet_id', Integer, ForeignKey('seed_packets.id', ondelete="CASCADE"), primary_key=True),
    Column('image_id', Integer, ForeignKey('images.id', ondelete="CASCADE"), primary_key=True)
)

plant_image = Table(
    'plant_image',
    Base.metadata,
    Column('plant_id', Integer, ForeignKey('plants.id', ondelete="CASCADE"), primary_key=True),
    Column('image_id', Integer, ForeignKey('images.id', ondelete="CASCADE"), primary_key=True)
)

garden_supply_image = Table(
    'garden_supply_image',
    Base.metadata,
    Column('garden_supply_id', Integer, ForeignKey('garden_supplies.id', ondelete="CASCADE"), primary_key=True),
    Column('image_id', Integer, ForeignKey('images.id', ondelete="CASCADE"), primary_key=True)
)

note_image = Table(
    'note_image',
    Base.metadata,
    Column('note_id', Integer, ForeignKey('notes.id', ondelete="CASCADE"), primary_key=True),
    Column('image_id', Integer, ForeignKey('images.id', ondelete="CASCADE"), primary_key=True)
)

class Image(Base):
    """Model representing an image with metadata."""
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_size = Column(Integer)
    content_type = Column(String(50))
    
    # OCR related fields
    ocr_processed = Column(Integer, default=0)  # 0=not processed, 1=processed, 2=processing failed
    ocr_text = Column(Text)
    structured_data = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    seed_packets = relationship("SeedPacket", secondary=seed_packet_image, back_populates="images")
    plants = relationship("Plant", secondary=plant_image, back_populates="images")
    garden_supplies = relationship("GardenSupply", secondary=garden_supply_image, back_populates="images")
    notes = relationship("Note", secondary=note_image, back_populates="images")