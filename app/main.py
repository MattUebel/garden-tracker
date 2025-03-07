from fastapi import FastAPI, Depends, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
import json
import logging
import pydantic

from . import models
from .database import SessionLocal, engine
from .logging_config import setup_logging
from .exceptions import GardenBaseException, ResourceNotFoundException, DatabaseOperationException
from .config import DEBUG

# Setup logging
logger = setup_logging()

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Import all schema modules first to make sure they're registered
from app.schemas import GardenBaseModel
from app.schemas.plants import Plant as PlantSchema
from app.schemas.notes import Note as NoteSchema 
from app.schemas.seed_packets import SeedPacket as SeedPacketSchema
from app.schemas.garden_supplies import GardenSupply as GardenSupplySchema
from app.schemas.harvests import Harvest as HarvestSchema

# Now update all forward references
from app.schemas import update_forward_refs
update_forward_refs()

# Import the router after schemas are fully loaded
from .routes import router as api_router

# Enhanced JSON encoder that handles Pydantic models and SQLAlchemy models
class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pydantic.BaseModel):
            # Convert Pydantic models to dict
            return obj.model_dump()
        if hasattr(obj, '__dict__'):
            # Get the dictionary of attributes for SQLAlchemy models
            data = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Skip SQLAlchemy internal attributes
                    try:
                        json.dumps(value)  # Test if value is JSON serializable
                        data[key] = value
                    except (TypeError, OverflowError):
                        # If value is not JSON serializable, convert it to string
                        data[key] = str(value)
            return data
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def custom_json_dumps(obj, **kwargs):
    return json.dumps(obj, cls=EnhancedJSONEncoder, **kwargs)

# Function to convert Pydantic models to JSON-safe dictionaries
def to_dict_filter(obj):
    if isinstance(obj, pydantic.BaseModel):
        return obj.model_dump()
    return obj

app = FastAPI(title="Garden Tracker API", debug=DEBUG)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")

# Set up templates with custom JSON encoder
templates = Jinja2Templates(directory="app/templates")
templates.env.policies['json.dumps_function'] = custom_json_dumps
# Register the to_dict filter properly
templates.env.filters['to_dict'] = to_dict_filter

# Exception handlers
@app.exception_handler(GardenBaseException)
async def garden_exception_handler(request: Request, exc: GardenBaseException):
    logger.error(
        f"GardenBaseException: {exc.detail}",
        extra={
            "error_code": exc.error_code,
            "details": exc.details,
            "path": request.url.path
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.detail,
                "details": exc.details
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception occurred",
        extra={"path": request.url.path}
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {"type": str(type(exc).__name__)}
            }
        }
    )

# Database session middleware
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    try:
        request.state.db = SessionLocal()
        response = await call_next(request)
        return response
    except Exception as e:
        logger.exception("Database session middleware error")
        raise
    finally:
        request.state.db.close()

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    try:
        response = await call_next(request)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() * 1000
        logger.info(
            f"Request completed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "duration_ms": duration,
                "status_code": response.status_code
            }
        )
        return response
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() * 1000
        logger.error(
            f"Request failed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "duration_ms": duration,
                "error": str(e)
            }
        )
        raise

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Include the routes from the router module
app.include_router(api_router)

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        # Get models from the database
        from app.models import Plant, Note, SeedPacket, GardenSupply
        
        # Get summary data and convert to Pydantic models
        plants = [PlantSchema.from_orm(p) for p in db.query(Plant).order_by(Plant.created_at.desc()).limit(5).all()]
        notes = [NoteSchema.from_orm(n) for n in db.query(Note).order_by(Note.timestamp.desc()).limit(5).all()]
        seed_packets = [SeedPacketSchema.from_orm(sp) for sp in db.query(SeedPacket).order_by(SeedPacket.created_at.desc()).limit(5).all()]
        supplies = [GardenSupplySchema.from_orm(s) for s in db.query(GardenSupply).order_by(GardenSupply.created_at.desc()).limit(5).all()]
        
        logger.info("Loading home dashboard")
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "recent_plants": plants,
                "recent_notes": notes,
                "recent_seed_packets": seed_packets,
                "recent_supplies": supplies,
            }
        )
    except Exception as e:
        logger.exception("Error loading home dashboard")
        raise DatabaseOperationException("query", str(e))