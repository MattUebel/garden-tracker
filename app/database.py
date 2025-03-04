from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
# Import all models to ensure they're registered with SQLAlchemy
from .models import Base, Plant, SeedPacket, GardenSupply, Year, Note, Harvest

load_dotenv()

# First try DATABASE_URL, fall back to individual components if not set
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    # Use localhost for local development, 'db' for Docker
    host = os.getenv('POSTGRES_HOST', 'localhost')
    user = os.getenv('POSTGRES_USER', 'garden_user')
    password = os.getenv('POSTGRES_PASSWORD', 'mygarden')
    db = os.getenv('POSTGRES_DB', 'garden_db')
    DATABASE_URL = f"postgresql://{user}:{password}@{host}:5432/{db}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()