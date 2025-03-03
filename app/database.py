from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Import all models to ensure they're registered with SQLAlchemy
from .models import Base, Plant, SeedPacket, GardenSupply, Year, Note, Harvest

load_dotenv()

# Use localhost for local development, 'db' for Docker
host = os.getenv('DB_HOST', 'localhost')
SQLALCHEMY_DATABASE_URL = f"postgresql://garden_user:garden_password@{host}:5432/garden_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()