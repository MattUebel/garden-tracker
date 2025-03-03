from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from .base import Base

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    body = Column(String, nullable=False)
    image_path = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=func.now())
    
    # Foreign Keys
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=True)
    seed_packet_id = Column(Integer, ForeignKey('seed_packets.id'), nullable=True)
    garden_supply_id = Column(Integer, ForeignKey('garden_supplies.id'), nullable=True)

    def __repr__(self):
        return f"<Note {self.id}>"