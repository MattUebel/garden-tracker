from sqlalchemy import Column, Integer, func
from .base import Base

class Year(Base):
    __tablename__ = "years"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, unique=True, nullable=False, default=lambda: func.extract('year', func.current_date()))

    def __repr__(self):
        return f"<Year {self.year}>"