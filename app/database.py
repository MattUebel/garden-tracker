from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import logging

# Import all models to ensure they're registered with SQLAlchemy
from .models import Base, Plant, SeedPacket, GardenSupply, Year, Note, Harvest
from .config import SQLALCHEMY_DATABASE_URL

logger = logging.getLogger(__name__)

# Configure SQLAlchemy engine with retry logic
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
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