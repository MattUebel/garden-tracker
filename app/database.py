from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import os
import logging
from dotenv import load_dotenv
# Import all models to ensure they're registered with SQLAlchemy
from .models import Base, Plant, SeedPacket, GardenSupply, Year, Note, Harvest

load_dotenv()
logger = logging.getLogger(__name__)

def get_database_url():
    """Get database URL with fallbacks and validation"""
    # First try DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return database_url
    
    # Fall back to individual components
    host = os.getenv('POSTGRES_HOST', 'db')
    user = os.getenv('POSTGRES_USER')
    password = os.getenv('POSTGRES_PASSWORD')
    db = os.getenv('POSTGRES_DB')
    
    if not all([user, password, db]):
        logger.error("Missing required database configuration. Check environment variables.")
        # Use default values as last resort
        user = user or 'garden_user'
        password = password or 'mygarden'
        db = db or 'garden_db'
    
    return f"postgresql://{user}:{password}@{host}:5432/{db}"

# Configure SQLAlchemy engine with retry logic
engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,  # Enable connection health checks
)

# Add connection debugging
@event.listens_for(engine, 'connect')
def receive_connect(dbapi_connection, connection_record):
    logger.info("Database connection established")

@event.listens_for(engine, 'checkout')
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug("Database connection checked out")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Database session dependency with improved error handling"""
    db = SessionLocal()
    try:
        # Test the connection
        db.execute("SELECT 1")
        yield db
    except OperationalError as e:
        logger.error(f"Database connection error: {str(e)}")
        raise
    finally:
        db.close()