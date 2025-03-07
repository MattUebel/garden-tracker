from fastapi import FastAPI, Depends, HTTPException, Query, Request, File, UploadFile, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional, ForwardRef
import logging
from datetime import datetime, date
import json
import os
from . import models
from .database import SessionLocal, engine
from .logging_config import setup_logging
from .exceptions import GardenBaseException, ResourceNotFoundException, ValidationException, FileUploadException, DatabaseOperationException
from pydantic import BaseModel
import enum
from .utils import save_upload_file, delete_upload_file, apply_filters
from .models.plant import PlantingMethod

# Import configuration
from .config import get_mistral_api_key, DEBUG, UPLOAD_FOLDER, MISTRAL_OCR_MODEL, MISTRAL_CHAT_MODEL

# Import MistralAI for OCR and chat completion
from mistralai import Mistral

# Setup logging
logger = setup_logging()

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Custom JSON encoder for SQLAlchemy models
class SQLAlchemyJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            # Get the dictionary of attributes
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
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

def custom_json_dumps(obj, **kwargs):
    return json.dumps(obj, cls=SQLAlchemyJSONEncoder, **kwargs)

app = FastAPI(title="Garden Tracker API", debug=DEBUG)

# Mount static files and templates with custom JSON encoder
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.policies['json.dumps_function'] = custom_json_dumps

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

# Form classes first
class NoteCreateForm:
    def __init__(
        self,
        body: str = Form(...),
        image: UploadFile = File(None),
        plant_id: Optional[int] = Form(None),
        seed_packet_id: Optional[int] = Form(None),
        garden_supply_id: Optional[int] = Form(None)
    ):
        self.body = body
        self.image = image
        self.plant_id = plant_id
        self.seed_packet_id = seed_packet_id
        self.garden_supply_id = garden_supply_id

class SeedPacketCreateForm:
    def __init__(
        self,
        name: str = Form(...),
        variety: str = Form(None),
        description: str = Form(None),
        planting_instructions: str = Form(None),
        days_to_germination: int = Form(None),
        spacing: str = Form(None),
        sun_exposure: str = Form(None),
        soil_type: str = Form(None),
        watering: str = Form(None),
        fertilizer: str = Form(None),
        package_weight: float = Form(None),
        expiration_date: str = Form(None),
        quantity: int = Form(...),
        image: UploadFile = File(None)
    ):
        self.name = name
        self.variety = variety
        self.description = description
        self.planting_instructions = planting_instructions
        self.days_to_germination = days_to_germination
        self.spacing = spacing
        self.sun_exposure = sun_exposure
        self.soil_type = soil_type
        self.watering = watering
        self.fertilizer = fertilizer
        self.package_weight = package_weight
        self.expiration_date = datetime.strptime(expiration_date, "%Y-%m-%d").date() if expiration_date else None 
        self.quantity = quantity
        self.image = image

class GardenSupplyCreateForm:
    def __init__(
        self,
        name: str = Form(...),
        description: str = Form(None),
        image: UploadFile = File(None)
    ):
        self.name = name
        self.description = description
        self.image = image

# Forward references for circular dependencies
PlantRef = ForwardRef('Plant')
NoteRef = ForwardRef('Note')

# Pydantic models with updated config
class Year(BaseModel):
    year: int

    class Config:
        from_attributes = True

class PlantInHarvest(BaseModel):
    id: int
    name: str
    variety: Optional[str] = None

    class Config:
        from_attributes = True

class NoteBase(BaseModel):
    body: str
    image_path: Optional[str] = None
    plant_id: Optional[int] = None
    seed_packet_id: Optional[int] = None
    garden_supply_id: Optional[int] = None

class NoteCreate(NoteBase):
    pass

class Note(NoteBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class PlantBase(BaseModel):
    name: str
    variety: Optional[str] = None
    planting_method: PlantingMethod
    seed_packet_id: Optional[int] = None

class PlantCreate(PlantBase):
    pass

class Plant(PlantBase):
    id: int
    year_id: int
    created_at: datetime
    updated_at: datetime 
    year: Year

    class Config:
        from_attributes = True

class SeedPacketBase(BaseModel):
    name: str
    variety: Optional[str] = None
    description: Optional[str] = None
    planting_instructions: Optional[str] = None
    days_to_germination: Optional[int] = None
    spacing: Optional[str] = None
    sun_exposure: Optional[str] = None
    soil_type: Optional[str] = None
    watering: Optional[str] = None
    fertilizer: Optional[str] = None
    package_weight: Optional[float] = None
    expiration_date: Optional[date] = None
    quantity: int
    image_path: Optional[str] = None

    class Config:
        from_attributes = True

class SeedPacketCreate(SeedPacketBase):
    pass

class SeedPacket(SeedPacketBase):
    id: int
    created_at: datetime
    updated_at: datetime
    plants: List[PlantRef]
    notes: List[NoteRef]

    class Config:
        from_attributes = True

# Update forward refs
Plant.update_forward_refs()
SeedPacket.update_forward_refs()

class GardenSupplyBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_path: Optional[str] = None

class GardenSupplyCreate(GardenSupplyBase):
    pass

class GardenSupply(GardenSupplyBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class HarvestBase(BaseModel):
    weight_oz: float
    plant_id: int

class HarvestCreate(HarvestBase):
    pass

class Harvest(HarvestBase):
    id: int
    timestamp: datetime
    plant: PlantInHarvest

    class Config:
        from_attributes = True

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        # Get summary data and convert to Pydantic models
        plants = [Plant.from_orm(p) for p in db.query(models.Plant).order_by(models.Plant.created_at.desc()).limit(5).all()]
        notes = [Note.from_orm(n) for n in db.query(models.Note).order_by(models.Note.timestamp.desc()).limit(5).all()]
        seed_packets = [SeedPacket.from_orm(sp) for sp in db.query(models.SeedPacket).order_by(models.SeedPacket.created_at.desc()).limit(5).all()]
        supplies = [GardenSupply.from_orm(s) for s in db.query(models.GardenSupply).order_by(models.GardenSupply.created_at.desc()).limit(5).all()]
        
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

# Plant endpoints
@app.post("/plants/", response_model=Plant)
def create_plant(plant: PlantCreate, db: Session = Depends(get_db)):
    try:
        logger.info("Creating new plant", extra={"plant_data": plant.dict()})
        
        current_year = db.query(models.Year).filter(
            models.Year.year == extract('year', datetime.now())
        ).first()
        
        if not current_year:
            current_year = models.Year(year=datetime.now().year)
            db.add(current_year)
            db.commit()
            db.refresh(current_year)

        # Create plant data dict and remove seed_packet_id if it's empty
        plant_data = plant.dict()
        if not plant_data.get('seed_packet_id'):
            plant_data.pop('seed_packet_id', None)

        db_plant = models.Plant(**plant_data, year_id=current_year.year)
        db.add(db_plant)
        db.commit()
        db.refresh(db_plant)
        
        logger.info("Plant created successfully", extra={"plant_id": db_plant.id})
        return db_plant
        
    except Exception as e:
        logger.exception("Failed to create plant")
        raise DatabaseOperationException("create", str(e))

@app.get("/plants/", response_model=List[Plant])
def list_plants(
    planting_method: Optional[PlantingMethod] = None,
    variety: Optional[str] = None,
    year: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Plant)
    if planting_method:
        query = query.filter(models.Plant.planting_method == planting_method)
    if variety:
        query = query.filter(models.Plant.variety == variety)
    if year:
        query = query.filter(models.Plant.year_id == year)
    if seed_packet_id:
        query = query.filter(models.Plant.seed_packet_id == seed_packet_id)
    return query.all()

@app.get("/plants/{plant_id}")
def get_plant(plant_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
        if plant is None:
            raise ResourceNotFoundException("Plant", plant_id)
            
        # Get all seed packets for the dropdown
        seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.name).all()
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                "plants/detail.html",
                {
                    "request": request,
                    "plant": plant,
                    "seed_packets": seed_packets,
                    "planting_methods": list(PlantingMethod)
                }
            )
        # API JSON response - properly serialize the SQLAlchemy objects
        return {
            "id": plant.id,
            "name": plant.name,
            "variety": plant.variety,
            "planting_method": plant.planting_method,
            "seed_packet_id": plant.seed_packet_id,
            "created_at": plant.created_at,
            "updated_at": plant.updated_at,
            "year_id": plant.year_id,
            "seed_packets": [{
                "id": packet.id,
                "name": packet.name
            } for packet in seed_packets],
            "planting_methods": [method.value for method in PlantingMethod]
        }
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving plant", extra={"plant_id": plant_id})
        raise DatabaseOperationException("query", str(e))

@app.put("/plants/{plant_id}", response_model=Plant)
def update_plant(plant_id: int, plant: PlantCreate, db: Session = Depends(get_db)):
    db_plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if db_plant is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    
    # Create a dict of updates and remove seed_packet_id if it's empty
    update_data = plant.dict()
    if not update_data.get('seed_packet_id'):
        update_data.pop('seed_packet_id', None)
    
    for key, value in update_data.items():
        setattr(db_plant, key, value)
    
    db.commit()
    db.refresh(db_plant)
    return db_plant

@app.delete("/plants/{plant_id}")
def delete_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
    if plant is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    db.delete(plant)
    db.commit()
    return {"message": "Plant deleted"}

@app.post("/plants/{plant_id}/duplicate", response_model=Plant)
async def duplicate_plant(plant_id: int, db: Session = Depends(get_db)):
    """Duplicate a plant with all its properties except unique identifiers"""
    try:
        # Get the original plant
        original = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Plant not found")

        # Create new plant with same properties
        db_plant = models.Plant(
            name=f"{original.name} (Copy)",
            variety=original.variety,
            planting_method=original.planting_method,
            seed_packet_id=original.seed_packet_id,
            year_id=original.year_id
        )

        db.add(db_plant)
        db.commit()
        db.refresh(db_plant)
        return db_plant
    except Exception as e:
        logger.exception(f"Error duplicating plant", extra={"plant_id": plant_id})
        raise DatabaseOperationException("create", str(e))

# Seed Packet endpoints
@app.post("/seed-packets/", response_model=SeedPacket)
async def create_seed_packet(
    form: SeedPacketCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    image_path = None
    if form.image and form.image.filename:
        image_path = save_upload_file(form.image)
    
    db_seed_packet = models.SeedPacket(
        name=form.name,
        variety=form.variety,
        description=form.description,
        planting_instructions=form.planting_instructions,
        days_to_germination=form.days_to_germination,
        spacing=form.spacing,
        sun_exposure=form.sun_exposure,
        soil_type=form.soil_type,
        watering=form.watering,
        fertilizer=form.fertilizer,
        package_weight=form.package_weight,
        expiration_date=form.expiration_date,
        quantity=form.quantity,
        image_path=image_path
    )
    db.add(db_seed_packet)
    db.commit()
    db.refresh(db_seed_packet)
    return db_seed_packet

@app.get("/seed-packets/", response_model=List[SeedPacket])
def list_seed_packets(db: Session = Depends(get_db)):
    return db.query(models.SeedPacket).all()

@app.get("/seed-packets/{seed_packet_id}")
def get_seed_packet(seed_packet_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
        if seed_packet is None:
            raise ResourceNotFoundException("Seed Packet", seed_packet_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            # Sort notes by timestamp descending
            sorted_notes = sorted(seed_packet.notes, key=lambda x: x.timestamp, reverse=True)
            
            # Check if Mistral API key is available
            has_mistral_api = bool(get_mistral_api_key())
            
            return templates.TemplateResponse(
                "seed_packets/detail.html",
                {
                    "request": request,
                    "seed_packet": seed_packet,
                    "notes": sorted_notes,
                    "has_mistral_api": has_mistral_api
                }
            )
        # API JSON response
        return seed_packet
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving seed packet", extra={"seed_packet_id": seed_packet_id})
        raise DatabaseOperationException("query", str(e))

@app.put("/seed-packets/{seed_packet_id}", response_model=SeedPacket)
async def update_seed_packet(
    seed_packet_id: int,
    name: str = Form(...),
    variety: str = Form(None),
    description: str = Form(None),
    planting_instructions: str = Form(None),
    days_to_germination: int = Form(None),
    spacing: str = Form(None),
    sun_exposure: str = Form(None),
    soil_type: str = Form(None),
    watering: str = Form(None),
    fertilizer: str = Form(None),
    package_weight: float = Form(None),
    expiration_date: str = Form(None),
    quantity: int = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    db_seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
    if db_seed_packet is None:
        raise HTTPException(status_code=404, detail="Seed packet not found")
    
    # Handle image upload only if a file was actually uploaded
    if image and image.filename:
        # Delete old image if it exists
        delete_upload_file(db_seed_packet.image_path)
        # Save new image
        image_path = save_upload_file(image)
        db_seed_packet.image_path = image_path
    
    # Update all fields
    db_seed_packet.name = name
    db_seed_packet.variety = variety
    db_seed_packet.description = description
    db_seed_packet.planting_instructions = planting_instructions
    db_seed_packet.days_to_germination = days_to_germination
    db_seed_packet.spacing = spacing
    db_seed_packet.sun_exposure = sun_exposure
    db_seed_packet.soil_type = soil_type
    db_seed_packet.watering = watering
    db_seed_packet.fertilizer = fertilizer
    db_seed_packet.package_weight = package_weight
    db_seed_packet.expiration_date = datetime.strptime(expiration_date, "%Y-%m-%d").date() if expiration_date else None
    db_seed_packet.quantity = quantity
    
    db.commit()
    db.refresh(db_seed_packet)
    return db_seed_packet

@app.post("/seed-packets/{seed_packet_id}/duplicate", response_model=SeedPacket)
async def duplicate_seed_packet(seed_packet_id: int, db: Session = Depends(get_db)):
    """Duplicate a seed packet with all its properties except unique identifiers"""
    try:
        # Get the original seed packet
        original = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Seed packet not found")

        # Create new seed packet with same properties
        db_seed_packet = models.SeedPacket(
            name=f"{original.name} (Copy)",
            variety=original.variety,
            description=original.description,
            planting_instructions=original.planting_instructions,
            days_to_germination=original.days_to_germination,
            spacing=original.spacing,
            sun_exposure=original.sun_exposure,
            soil_type=original.soil_type,
            watering=original.watering,
            fertilizer=original.fertilizer,
            package_weight=original.package_weight,
            expiration_date=original.expiration_date,
            quantity=original.quantity
        )
        
        # If original has an image, copy it
        if original.image_path:
            try:
                from shutil import copyfile
                import os
                from uuid import uuid4
                
                # Generate new unique filename
                ext = os.path.splitext(original.image_path)[1]
                new_filename = f"{uuid4()}{ext}"
                new_path = os.path.join("app/static/uploads", new_filename)
                
                # Copy the file
                copyfile(f"app/static/{original.image_path}", new_path)
                db_seed_packet.image_path = f"uploads/{new_filename}"
            except Exception as e:
                logger.warning(f"Failed to copy image for duplicated seed packet: {str(e)}")
                # Continue without the image if copy fails
                pass

        db.add(db_seed_packet)
        db.commit()
        db.refresh(db_seed_packet)
        return db_seed_packet
    except Exception as e:
        logger.exception(f"Error duplicating seed packet", extra={"seed_packet_id": seed_packet_id})
        raise DatabaseOperationException("create", str(e))

@app.delete("/seed-packets/{seed_packet_id}")
def delete_seed_packet(seed_packet_id: int, db: Session = Depends(get_db)):
    seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
    if seed_packet is None:
        raise HTTPException(status_code=404, detail="Seed packet not found")
    
    # Delete image file if it exists
    delete_upload_file(seed_packet.image_path)
    
    db.delete(seed_packet)
    db.commit()
    return {"message": "Seed packet deleted"}

# Modify the process_seed_packet_ocr function to improve text detection

@app.post("/seed-packets/{seed_packet_id}/ocr")
async def process_seed_packet_ocr(
    seed_packet_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
        if seed_packet is None:
            raise ResourceNotFoundException("Seed Packet", seed_packet_id)
        if not seed_packet.image_path:
            return JSONResponse(
                status_code=400,
                content={"error": "No image available for this seed packet"}
            )
        # Get the API key from configuration
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )
        # Initialize Mistral client
        client = Mistral(api_key=api_key)
        # Clean up the image path - it might start with "/" or "static/"
        image_path = seed_packet.image_path
        # Remove initial '/' if present
        if image_path.startswith('/'):
            image_path = image_path[1:]
        # Add "app/" prefix if not already there and if it doesn't start with "static/"
        if not image_path.startswith('app/'):
            if image_path.startswith('static/'):
                image_path = f"app/{image_path}"
            else:
                image_path = f"app/static/{image_path}"
        
        logger.info(f"Processing OCR for seed packet image: {image_path}")
        
        # Print debug info
        import os
        if os.path.exists(image_path):
            logger.info(f"Image file exists at {image_path}")
            # Get and log image file size
            file_size = os.path.getsize(image_path)
            logger.info(f"Image file size: {file_size} bytes")
        else:
            logger.error(f"Image file does not exist at {image_path}")
            # Try to list the directory to see what's there
            dir_path = os.path.dirname(image_path)
            if os.path.exists(dir_path):
                logger.info(f"Contents of {dir_path}: {os.listdir(dir_path)}")
            else:
                logger.error(f"Directory {dir_path} does not exist")
        
        # Try to preprocess the image to improve OCR results if PIL is available
        preprocessed_image_path = None
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import tempfile
            
            logger.info("Attempting to preprocess image for better OCR results")
            # Create a temporary file for the processed image
            fd, preprocessed_image_path = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            
            # Open the image
            img = Image.open(image_path)
            
            # Convert to RGB if needed (in case it's RGBA with transparency)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
                
            # Resize if the image is very large (preserves detail but reduces processing time)
            max_size = 2000
            if max(img.size) > max_size:
                logger.info(f"Resizing large image from {img.size}")
                img.thumbnail((max_size, max_size), Image.LANCZOS)
                logger.info(f"Image resized to {img.size}")
            
            # Enhance contrast to make text more visible
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)  # Increase contrast by 50%
            
            # Sharpen to make text edges crisper
            img = img.filter(ImageFilter.SHARPEN)
            
            # Save the preprocessed image
            img.save(preprocessed_image_path, 'JPEG', quality=95)
            logger.info(f"Image preprocessed and saved to {preprocessed_image_path}")
            
            # Use the preprocessed image instead of the original
            image_to_process = preprocessed_image_path
        except ImportError:
            logger.warning("PIL not available for image preprocessing, using original image")
            image_to_process = image_path
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {str(e)}, using original image")
            image_to_process = image_path
        
        # Base64 encode the image
        import base64
        try:
            with open(image_to_process, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
            # Determine image format from the file extension
            image_format = "jpeg"  # Default format
            if image_to_process.lower().endswith(".png"):
                image_format = "png"
            elif image_to_process.lower().endswith(".gif"):
                image_format = "gif"
            elif image_to_process.lower().endswith((".jpg", ".jpeg")):
                image_format = "jpeg"
            
            # Log more detailed information about the API call
            logger.info(f"Calling OCR API with image format: {image_format}, base64 length: {len(base64_image)}")
            
            # Call the OCR API with base64-encoded image
            ocr_response = client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "image_url",
                    "image_url": f"data:image/{image_format};base64,{base64_image}"
                }
            )
            
            # Extract OCR text from the response based on the structure:
            # {
            #   "pages": [
            #     {
            #       "index": 0,
            #       "markdown": "string",
            #       ...
            #     }
            #   ],
            #   ...
            # }
            
            # Convert response to a dictionary to handle the JSON structure
            response_dict = None
            if hasattr(ocr_response, 'model_dump'):
                # For Pydantic models
                response_dict = ocr_response.model_dump()
            elif hasattr(ocr_response, '__dict__'):
                # For regular objects
                response_dict = ocr_response.__dict__
            else:
                # Try to convert directly to dict if it's a JSON response
                import json
                try:
                    response_dict = json.loads(str(ocr_response))
                except:
                    response_dict = {"error": "Could not parse response"}
            
            logger.info(f"Response keys: {list(response_dict.keys()) if isinstance(response_dict, dict) else 'Not a dictionary'}")
            
            # Extract the markdown text from the pages
            ocr_text = ""
            if isinstance(response_dict, dict) and "pages" in response_dict:
                page_texts = []
                
                for page in response_dict["pages"]:
                    if "markdown" in page:
                        page_text = page["markdown"]
                        page_texts.append(page_text)
                        
                        # If we have OCR text, append it
                        if ocr_text:
                            ocr_text += "\n\n"
                        ocr_text += page_text
                
                # Check if OCR text is just image references (no actual text)
                is_just_image_refs = all(
                    text.strip().startswith('![') and text.strip().endswith(')')
                    for text in page_texts if text.strip()
                )
                
                # Check if there's any content at all
                is_empty = not ''.join(page_texts).strip()
                
                if is_just_image_refs or is_empty:
                    logger.warning(f"OCR only returned image references or empty content for seed packet {seed_packet_id}")
                    
                    # Fall back to OCR using a different model or approach
                    logger.info("Trying alternative OCR approach...")
                    
                    # Create a note explaining the issue but don't fail the process
                    ocr_text = "The OCR process detected an image but couldn't extract text. This could be due to:\n"
                    ocr_text += "- Text being too small or unclear\n"
                    ocr_text += "- Low contrast between text and background\n"
                    ocr_text += "- Unusual font styles\n\n"
                    ocr_text += "Try taking a clearer photo of the seed packet in good lighting, focusing on text areas."
            else:
                # Fallback to string representation if we can't extract text
                ocr_text = str(ocr_response)
            
            logger.info(f"Extracted OCR text: {ocr_text[:100]}...")  # Log first 100 chars
            
            # Clean up the temporary preprocessed image if it exists
            if preprocessed_image_path and os.path.exists(preprocessed_image_path):
                try:
                    os.unlink(preprocessed_image_path)
                    logger.info(f"Removed temporary preprocessed image: {preprocessed_image_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove temporary image: {str(e)}")
            
        except FileNotFoundError:
            logger.error(f"Image file not found: {image_path}")
            return JSONResponse(
                status_code=500, 
                content={"error": f"Image file not found: {image_path}"}
            )
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Error processing image: {str(e)}"}
            )
        # Create a note with the OCR results
        note_body = f"OCR Results:\n\n{ocr_text}"
        
        db_note = models.Note(
            body=note_body,
            seed_packet_id=seed_packet_id
        )
        
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        
        logger.info(f"Created note with OCR results for seed packet: {seed_packet_id}")
        return JSONResponse(
            content={
                "status": "success",
                "note_id": db_note.id,
                "ocr_text": ocr_text
            }
        )
        
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error processing OCR for seed packet", extra={"seed_packet_id": seed_packet_id})
        return JSONResponse(
            status_code=500,
            content={"error": f"OCR processing failed: {str(e)}"}
        )

# Extract structured data from OCR results
@app.post("/seed-packets/{seed_packet_id}/extract-data")
async def extract_data_from_ocr(
    seed_packet_id: int,
    request: Request,
    ocr_text: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
        if seed_packet is None:
            raise ResourceNotFoundException("Seed Packet", seed_packet_id)

        # Get the API key from configuration
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )

        # Initialize Mistral client
        client = Mistral(api_key=api_key)

        # Define prompt to extract structured data
        prompt = f"""
Extract structured information from the following seed packet text.
The text was obtained from OCR and may have formatting issues or errors.
Please extract the following fields if they are present in the text:

- name: The name of the plant/seed (e.g., 'Tomato', 'Basil', 'Carrot')
- variety: The specific variety (e.g., 'Roma', 'Sweet Thai', 'Nantes')
- description: A brief description of the plant
- planting_instructions: Instructions on how to plant
- days_to_germination: The number of days it takes to germinate (just the number)
- spacing: Recommended spacing between plants
- sun_exposure: Light requirements (e.g., 'Full Sun', 'Partial Shade')
- soil_type: Soil preferences
- watering: Watering requirements
- fertilizer: Fertilizer recommendations
- package_weight: The weight of the seed packet (just the number in grams)
- expiration_date: Date format YYYY-MM-DD if present

Return ONLY a JSON object with these fields. If information for a field is not available, use null.

Here's the OCR text from the seed packet:

{ocr_text}
"""

        # Create chat completion request
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        # Get the chat response
        logger.info(f"Sending chat completion request for seed packet {seed_packet_id}")
        chat_response = client.chat.complete(
            model=MISTRAL_CHAT_MODEL,
            messages=messages
        )

        # Extract the response content
        response_content = chat_response.choices[0].message.content
        logger.info(f"Received chat completion response: {response_content[:100]}...")

        # Parse the JSON response
        import json
        try:
            extracted_data = json.loads(response_content)
            
            # Clean up and validate the data
            if "days_to_germination" in extracted_data and extracted_data["days_to_germination"]:
                try:
                    extracted_data["days_to_germination"] = int(extracted_data["days_to_germination"])
                except (ValueError, TypeError):
                    extracted_data["days_to_germination"] = None
            
            if "package_weight" in extracted_data and extracted_data["package_weight"]:
                try:
                    extracted_data["package_weight"] = float(extracted_data["package_weight"])
                except (ValueError, TypeError):
                    extracted_data["package_weight"] = None
            
            # Format dates properly
            if "expiration_date" in extracted_data and extracted_data["expiration_date"]:
                # Simple validation to check if it matches YYYY-MM-DD format
                import re
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(extracted_data["expiration_date"])):
                    extracted_data["expiration_date"] = None
                    
            return JSONResponse(content=extracted_data)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from chat completion response")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to parse structured data from response"}
            )
            
    except Exception as e:
        logger.exception(f"Error extracting structured data", extra={"seed_packet_id": seed_packet_id})
        return JSONResponse(
            status_code=500,
            content={"error": f"Data extraction failed: {str(e)}"}
        )

# New endpoint for uploading an image and processing it with OCR immediately
@app.post("/seed-packets/upload-and-ocr")
async def upload_and_ocr_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a seed packet image and process it with OCR in one step"""
    try:
        # Check if Mistral API key is available
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )

        # First, save the uploaded image
        image_path = save_upload_file(image)
        if not image_path:
            return JSONResponse(
                status_code=400,
                content={"error": "Failed to save uploaded image"}
            )

        # Initialize Mistral client
        client = Mistral(api_key=api_key)

        # Clean up the image path for processing
        processed_image_path = image_path
        if processed_image_path.startswith('/'):
            processed_image_path = processed_image_path[1:]
        
        # Add "app/" prefix if not already there
        if not processed_image_path.startswith('app/'):
            processed_image_path = f"app/{processed_image_path}"
        
        logger.info(f"Processing OCR for uploaded image: {processed_image_path}")

        # Base64 encode the image for OCR
        import base64
        with open(processed_image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
        # Determine image format from the file extension
        image_format = "jpeg"  # Default format
        if processed_image_path.lower().endswith(".png"):
            image_format = "png"
        elif processed_image_path.lower().endswith(".gif"):
            image_format = "gif"
        elif processed_image_path.lower().endswith((".jpg", ".jpeg")):
            image_format = "jpeg"

        # Process with OCR
        ocr_response = client.ocr.process(
            model=MISTRAL_OCR_MODEL,
            document={
                "type": "image_url",
                "image_url": f"data:image/{image_format};base64,{base64_image}"
            }
        )
        
        # Extract OCR text
        ocr_text = ""
        response_dict = None
        if hasattr(ocr_response, 'model_dump'):
            response_dict = ocr_response.model_dump()
        elif hasattr(ocr_response, '__dict__'):
            response_dict = ocr_response.__dict__
        else:
            import json
            try:
                response_dict = json.loads(str(ocr_response))
            except:
                response_dict = {"error": "Could not parse response"}
        
        logger.info(f"Response dictionary: {response_dict}")
        
        # Extract the markdown text from the pages
        if isinstance(response_dict, dict) and "pages" in response_dict:
            for page in response_dict["pages"]:
                if "markdown" in page:
                    if ocr_text:
                        ocr_text += "\n\n"
                    ocr_text += page["markdown"]
        else:
            # Fallback to string representation if we can't extract text
            ocr_text = str(ocr_response)
        
        # Return OCR text and image path
        return JSONResponse(
            content={
                "status": "success",
                "image_path": image_path,
                "ocr_text": ocr_text
            }
        )
            
    except Exception as e:
        logger.exception(f"Error processing OCR for uploaded image")
        return JSONResponse(
            status_code=500,
            content={"error": f"OCR processing failed: {str(e)}"}
        )

# Endpoint to extract data from OCR text without needing a specific seed packet ID
@app.post("/seed-packets/extract-data-temp")
async def extract_data_from_ocr_temp(
    ocr_text: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # Get the API key from configuration
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )
        # Initialize Mistral client
        client = Mistral(api_key=api_key)
        # Log the OCR text input
        logger.info(f"OCR text to process: {ocr_text[:500]}...")
        # Define prompt to extract structured data
        prompt = """...existing prompt text..."""

        # Create chat completion request
        messages = [
            {
                "role": "system",
                "content": "You are an expert seed packet information extraction expert. Your task is to extract structured information from OCR text of seed packets, providing the most accurate data possible."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        # Get the chat response
        chat_response = client.chat.complete(
            model=MISTRAL_CHAT_MODEL,
            messages=messages,
            temperature=0.2
        )

        # Extract and process response
        response_content = chat_response.choices[0].message.content
        extracted_data = process_chat_response(response_content)
        
        return JSONResponse(content=extracted_data)
    except Exception as e:
        logger.exception(f"Error extracting structured data")
        return JSONResponse(
            status_code=500,
            content={"error": f"Data extraction failed: {str(e)}"}
        )

# OCR endpoint for temporary image upload (not attached to an existing seed packet)
@app.post("/seed-packets/ocr-temp")
async def process_ocr_temp(
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Process OCR on an uploaded image without saving it to a specific seed packet"""
    try:
        # Check if Mistral API key is available
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )
        
        # Save the uploaded image temporarily
        image_path = save_upload_file(image)
        if not image_path:
            return JSONResponse(
                status_code=400,
                content={"error": "Failed to save uploaded image"}
            )

        # Initialize Mistral client
        client = Mistral(api_key=api_key)

        # Prepare the image path for processing
        processed_image_path = f"app/static/{image_path}" if not image_path.startswith('app/') else image_path
        logger.info(f"Processing OCR for uploaded image: {processed_image_path}")
        
        # Log image properties
        import os
        if os.path.exists(processed_image_path):
            file_size = os.path.getsize(processed_image_path)
            logger.info(f"Image file exists, size: {file_size} bytes")
        else:
            logger.error(f"Image file does not exist: {processed_image_path}")
            return JSONResponse(
                status_code=400,
                content={"error": "Image file not found"}
            )

        # Base64 encode the image
        import base64
        with open(processed_image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            logger.info(f"Base64 encoded image length: {len(base64_image)} characters")
            
        # Determine image format from the file extension
        image_format = "jpeg"  # Default format
        if processed_image_path.lower().endswith(".png"):
            image_format = "png"
        elif processed_image_path.lower().endswith(".gif"):
            image_format = "gif"
        elif processed_image_path.lower().endswith((".jpg", ".jpeg")):
            image_format = "jpeg"
        
        logger.info(f"Using image format: {image_format}")

        # Call the OCR API with more detailed logging
        logger.info(f"Calling Mistral OCR API with model: {MISTRAL_OCR_MODEL}")
        try:
            # Get original filename for better traceability in the API
            original_filename = image.filename if hasattr(image, 'filename') and image.filename else "uploaded_image"
            
            ocr_response = client.ocr.process(
                model=MISTRAL_OCR_MODEL,
                document={
                    "type": "image_url",
                    "image_url": f"data:image/{image_format};base64,{base64_image}",
                    "document_name": original_filename  # Added document_name for better traceability
                }
            )
            logger.info("Received response from Mistral OCR API")
        except Exception as e:
            logger.exception(f"Error calling OCR API: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"OCR API call failed: {str(e)}"}
            )
        
        # Extract OCR text from the response
        ocr_text = ""
        response_dict = None
        if hasattr(ocr_response, 'model_dump'):
            response_dict = ocr_response.model_dump()
        elif hasattr(ocr_response, '__dict__'):
            response_dict = ocr_response.__dict__
        else:
            import json
            try:
                response_dict = json.loads(str(ocr_response))
            except:
                response_dict = {"error": "Could not parse response"}
        
        # Log the full OCR response for debugging
        logger.info(f"OCR Response structure: {list(response_dict.keys()) if isinstance(response_dict, dict) else 'Not a dictionary'}")
        logger.info(f"Response dictionary: {response_dict}")
        
        # Extract the markdown text from the pages and check if it's just image references
        if isinstance(response_dict, dict) and "pages" in response_dict:
            page_texts = []
            
            for page in response_dict["pages"]:
                if "markdown" in page:
                    page_text = page["markdown"]
                    page_texts.append(page_text)
                    
                    # If we have OCR text, append it
                    if ocr_text:
                        ocr_text += "\n\n"
                    ocr_text += page_text
                    
            # Check if OCR text is just image references (no actual text)
            is_just_image_refs = all(
                text.strip().startswith('![') and text.strip().endswith(')')
                for text in page_texts if text.strip()
            )
            
            if is_just_image_refs:
                logger.warning("OCR only returned image references, no actual text was extracted")
                
                # Return the error with the image path so the frontend can still show the image
                return JSONResponse(
                    content={
                        "status": "warning",
                        "image_path": image_path,
                        "ocr_text": "No text could be extracted from this image. The OCR process detected only image content.",
                        "warning": "OCR process didn't find text in the image"
                    }
                )
        else:
            # Fallback to string representation if we can't extract text
            ocr_text = str(ocr_response)
        
        # Check if OCR extracted any meaningful text
        if not ocr_text or ocr_text.isspace():
            logger.warning("OCR returned empty or whitespace-only text")
            return JSONResponse(
                content={
                    "status": "warning",
                    "image_path": image_path,
                    "ocr_text": "No text could be extracted from this image.",
                    "warning": "OCR process didn't find text in the image"
                }
            )
        
        # Log the extracted OCR text
        logger.info(f"Extracted OCR text (first 300 chars): {ocr_text[:300]}...")
        logger.info(f"OCR text length: {len(ocr_text)} characters")
        
        # Return OCR text and image path
        return JSONResponse(
            content={
                "status": "success",
                "image_path": image_path,
                "ocr_text": ocr_text
            }
        )
            
    except Exception as e:
        logger.exception(f"Error processing OCR for uploaded image: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"OCR processing failed: {str(e)}"}
        )

# Structured data extraction from OCR text
@app.post("/seed-packets/extract-info")
async def extract_info_from_ocr(
    request: Request,
    db: Session = Depends(get_db)
):
    """Extract structured data from OCR text using Mistral AI"""
    try:
        # Parse JSON body
        body = await request.json()
        ocr_text = body.get("ocr_text", "")
        
        if not ocr_text:
            logger.error("No OCR text provided in request body")
            return JSONResponse(
                status_code=400,
                content={"error": "No OCR text provided"}
            )

        # Get the API key from configuration
        api_key = get_mistral_api_key()
        if not api_key:
            logger.error("MISTRAL_API_KEY not set in environment variables")
            return JSONResponse(
                status_code=500,
                content={"error": "MISTRAL_API_KEY not set in environment"}
            )

        # Initialize Mistral client
        client = Mistral(api_key=api_key)
        
        # Log the OCR text we're processing
        logger.info(f"OCR text to process for extraction (length: {len(ocr_text)})")
        logger.info(f"First 300 chars of OCR text: {ocr_text[:300]}...")

        # Create a simple, clear prompt
        prompt = f"""You are a seed packet analyzer. I have an image of a seed packet and I've run OCR on it.
Please extract the following information from the OCR text and format it as a simple JSON object.

For each field, extract ONLY if present in the text. Otherwise, use null:

1. name: The name of the plant (example: "Tomato", "Basil", "Carrot")
2. variety: The specific variety name (example: "Roma", "Brandywine", "Sweet Thai", "Nantes")
3. description: A brief description of the plant or product
4. planting_instructions: Step-by-step planting guidance
5. days_to_germination: Number of days to germination (just the number)
6. spacing: Recommended spacing between plants
7. sun_exposure: Light requirements (Full Sun, Partial Shade, etc.)
8. soil_type: Soil recommendations
9. watering: Watering instructions
10. fertilizer: Fertilizer recommendations
11. package_weight: Weight in grams (just the number)
12. expiration_date: Date in YYYY-MM-DD format

Only return a valid JSON object containing these 12 fields and null values for missing information.
Do NOT include code block formatting, explanations, or any text outside the JSON object.

Here's the OCR text from the seed packet:

{ocr_text}
"""

        # Create chat completion request with system and user messages
        messages = [
            {
                "role": "system",
                "content": "You are an expert seed packet information extractor. Return ONLY a valid JSON object with no text outside the JSON."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]

        # Log that we're sending the request
        logger.info(f"Sending chat completion request to Mistral API for data extraction")
        
        # Get the chat response with low temperature for more deterministic results
        chat_response = client.chat.complete(
            model=MISTRAL_CHAT_MODEL,
            messages=messages,
            temperature=0.1
        )

        # Extract the response content
        response_content = chat_response.choices[0].message.content
        
        # Log the response for debugging
        logger.info(f"Raw chat completion response from Mistral API (first 500 chars): {response_content[:500]}...")
        logger.info(f"Response length: {len(response_content)}")

        # Parse JSON from the response, handling any code blocks
        import json
        import re

        # Try to find JSON in the response
        try:
            # First check if response is wrapped in code blocks
            code_block_pattern = r'```(?:json)?(.*?)```'
            match = re.search(code_block_pattern, response_content, re.DOTALL)
            
            if match:
                # Extract JSON from code block
                json_str = match.group(1).strip()
                logger.info(f"Found JSON in code block (first 100 chars): {json_str[:100]}...")
                extracted_data = json.loads(json_str)
            else:
                # Try to parse the entire response as JSON
                logger.info("No code block found, trying to parse entire response as JSON")
                extracted_data = json.loads(response_content.strip())
            
            # Clean up data types
            if "days_to_germination" in extracted_data and extracted_data["days_to_germination"]:
                try:
                    # Handle ranges like "7-10 days"
                    dgerm = str(extracted_data["days_to_germination"])
                    if "-" in dgerm:
                        dgerm = dgerm.split("-")[0]  # Take minimum value
                    # Remove non-numeric characters
                    dgerm = re.sub(r'[^\d.]', '', dgerm)
                    extracted_data["days_to_germination"] = int(float(dgerm))
                    logger.info(f"Cleaned days_to_germination: {extracted_data['days_to_germination']}")
                except Exception as e:
                    logger.warning(f"Could not parse days_to_germination: {e}")
                    extracted_data["days_to_germination"] = None
            
            if "package_weight" in extracted_data and extracted_data["package_weight"]:
                try:
                    # Handle string with units like "0.5g"
                    weight_str = str(extracted_data["package_weight"])
                    weight_str = re.sub(r'[^\d.]', '', weight_str)  # Remove non-numeric chars
                    extracted_data["package_weight"] = float(weight_str)
                    logger.info(f"Cleaned package_weight: {extracted_data['package_weight']}")
                except Exception as e:
                    logger.warning(f"Could not parse package_weight: {e}")
                    extracted_data["package_weight"] = None
            
            # Format dates
            if "expiration_date" in extracted_data and extracted_data["expiration_date"]:
                # Check if already in YYYY-MM-DD format
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(extracted_data["expiration_date"])):
                    try:
                        from dateutil import parser
                        date_str = str(extracted_data["expiration_date"])
                        parsed_date = parser.parse(date_str)
                        extracted_data["expiration_date"] = parsed_date.strftime("%Y-%m-%d")
                        logger.info(f"Parsed expiration_date: {extracted_data['expiration_date']}")
                    except Exception as e:
                        logger.warning(f"Could not parse expiration_date: {e}")
                        extracted_data["expiration_date"] = None
                        
            # Log the final extracted data
            logger.info(f"Final extracted data: {extracted_data}")
            return JSONResponse(content=extracted_data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Response content that failed to parse: {response_content}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to parse structured data from response: {str(e)}"}
            )
            
    except Exception as e:
        logger.exception(f"Error extracting structured data: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Data extraction failed: {str(e)}"}
        )

def process_chat_response(response_content: str) -> dict:
    """Process the chat response and extract structured data."""
    import json
    import re
    
    # Try to find JSON in the response
    try:
        # First check if response is wrapped in code blocks
        code_block_pattern = r'```(?:json)?(.*?)```'
        match = re.search(code_block_pattern, response_content, re.DOTALL)
        
        if match:
            # Extract JSON from code block
            json_str = match.group(1).strip()
            extracted_data = json.loads(json_str)
        else:
            # Try to parse the entire response as JSON
            extracted_data = json.loads(response_content.strip())
        
        # Clean up data types
        if "days_to_germination" in extracted_data and extracted_data["days_to_germination"]:
            try:
                # Handle ranges like "7-10 days"
                dgerm = str(extracted_data["days_to_germination"])
                if "-" in dgerm:
                    dgerm = dgerm.split("-")[0]  # Take minimum value
                # Remove non-numeric characters
                dgerm = re.sub(r'[^\d.]', '', dgerm)
                extracted_data["days_to_germination"] = int(float(dgerm))
            except (ValueError, TypeError):
                extracted_data["days_to_germination"] = None
        
        if "package_weight" in extracted_data and extracted_data["package_weight"]:
            try:
                # Handle string with units like "0.5g"
                weight_str = str(extracted_data["package_weight"])
                weight_str = re.sub(r'[^\d.]', '', weight_str)  # Remove non-numeric chars
                extracted_data["package_weight"] = float(weight_str)
            except (ValueError, TypeError):
                extracted_data["package_weight"] = None
        
        # Format dates
        if "expiration_date" in extracted_data and extracted_data["expiration_date"]:
            # Check if already in YYYY-MM-DD format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(extracted_data["expiration_date"])):
                try:
                    from datetime import datetime
                    date_str = str(extracted_data["expiration_date"])
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            extracted_data["expiration_date"] = parsed_date.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                    else:
                        extracted_data["expiration_date"] = None
                except Exception:
                    extracted_data["expiration_date"] = None
                    
        return extracted_data
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from response: {e}")
    except Exception as e:
        raise ValueError(f"Error processing chat response: {e}")

# Garden Supply endpoints
@app.post("/garden-supplies/", response_model=GardenSupply)
async def create_garden_supply(
    form: GardenSupplyCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    image_path = None
    if form.image and form.image.filename:
        image_path = save_upload_file(form.image)
    
    db_garden_supply = models.GardenSupply(
        name=form.name,
        description=form.description,
        image_path=image_path
    )
    db.add(db_garden_supply)
    db.commit()
    db.refresh(db_garden_supply)
    return db_garden_supply

@app.get("/garden-supplies/", response_model=List[GardenSupply])
def list_garden_supplies(db: Session = Depends(get_db)):
    return db.query(models.GardenSupply).all()

@app.get("/garden-supplies/{supply_id}")
def get_garden_supply(supply_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        supply = db.query(models.GardenSupply).filter(models.GardenSupply.id == supply_id).first()
        if supply is None:
            raise ResourceNotFoundException("Garden Supply", supply_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            # Sort notes by timestamp descending
            sorted_notes = sorted(supply.notes, key=lambda x: x.timestamp, reverse=True)
            return templates.TemplateResponse(
                "garden_supplies/detail.html",
                {
                    "request": request,
                    "supply": supply,
                    "notes": sorted_notes
                }
            )
        # API JSON response
        return supply
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving garden supply", extra={"supply_id": supply_id})
        raise DatabaseOperationException("query", str(e))

@app.put("/garden-supplies/{supply_id}", response_model=GardenSupply)
async def update_garden_supply(
    supply_id: int,
    name: str = Form(...),
    description: str = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    db_supply = db.query(models.GardenSupply).filter(models.GardenSupply.id == supply_id).first()
    if db_supply is None:
        raise HTTPException(status_code=404, detail="Garden supply not found")
    
    # Handle image upload only if a file was actually uploaded
    if image and image.filename:
        # Delete old image if it exists
        delete_upload_file(db_supply.image_path)
        # Save new image
        image_path = save_upload_file(image)
        db_supply.image_path = image_path
    
    db_supply.name = name
    db_supply.description = description
    
    db.commit()
    db.refresh(db_supply)
    return db_supply

@app.post("/garden-supplies/{supply_id}/duplicate", response_model=GardenSupply)
async def duplicate_garden_supply(supply_id: int, db: Session = Depends(get_db)):
    """Duplicate a garden supply with all its properties except unique identifiers"""
    try:
        # Get the original supply
        original = db.query(models.GardenSupply).filter(models.GardenSupply.id == supply_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Garden supply not found")

        # Create new supply with same properties
        db_supply = models.GardenSupply(
            name=f"{original.name} (Copy)",
            description=original.description
        )
        
        # If original has an image, copy it
        if original.image_path:
            try:
                from shutil import copyfile
                import os
                from uuid import uuid4
                
                # Generate new unique filename
                ext = os.path.splitext(original.image_path)[1]
                new_filename = f"{uuid4()}{ext}"
                new_path = os.path.join("app/static/uploads", new_filename)
                
                # Copy the file
                copyfile(f"app/static/{original.image_path}", new_path)
                db_supply.image_path = f"uploads/{new_filename}"
            except Exception as e:
                logger.warning(f"Failed to copy image for duplicated garden supply: {str(e)}")
                # Continue without the image if copy fails
                pass

        db.add(db_supply)
        db.commit()
        db.refresh(db_supply)
        return db_supply
    except Exception as e:
        logger.exception(f"Error duplicating garden supply", extra={"supply_id": supply_id})
        raise DatabaseOperationException("create", str(e))

@app.delete("/garden-supplies/{supply_id}")
def delete_garden_supply(supply_id: int, db: Session = Depends(get_db)):
    supply = db.query(models.GardenSupply).filter(models.GardenSupply.id == supply_id).first()
    if supply is None:
        raise HTTPException(status_code=404, detail="Garden supply not found")
    
    # Delete image file if it exists
    delete_upload_file(supply.image_path)
    
    db.delete(supply)
    db.commit()
    return {"message": "Garden supply deleted"}

# Year endpoints
@app.get("/years/", response_model=List[Year])
def list_years(db: Session = Depends(get_db)):
    return db.query(models.Year).all()

@app.post("/years/", response_model=Year)
def create_year(year: Year, db: Session = Depends(get_db)):
    db_year = models.Year(year=year.year)
    db.add(db_year)
    db.commit()
    db.refresh(db_year)
    return db_year

# Note endpoints
@app.post("/notes/", response_model=Note)
async def create_note(
    body: str = Form(...),
    image: UploadFile = File(None),
    plant_id: Optional[int] = Form(None),
    seed_packet_id: Optional[int] = Form(None),
    garden_supply_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    image_path = None
    if image and image.filename:
        image_path = save_upload_file(image)
    
    db_note = models.Note(
        body=body,
        image_path=image_path,
        plant_id=plant_id,
        seed_packet_id=seed_packet_id,
        garden_supply_id=garden_supply_id
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

@app.get("/notes/", response_model=List[Note])
def list_notes(
    plant_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    garden_supply_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Note)
    if plant_id:
        query = query.filter(models.Note.plant_id == plant_id)
    if seed_packet_id:
        query = query.filter(models.Note.seed_packet_id == seed_packet_id)
    if garden_supply_id:
        query = query.filter(models.Note.garden_supply_id == garden_supply_id)
    return query.all()

@app.get("/notes/{note_id}")
def get_note(note_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        note = db.query(models.Note).filter(models.Note.id == note_id).first()
        if note is None:
            raise ResourceNotFoundException("Note", note_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                "notes/detail.html",
                {
                    "request": request,
                    "note": note
                }
            )
        # API JSON response
        return note
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving note", extra={"note_id": note_id})
        raise DatabaseOperationException("query", str(e))

@app.put("/notes/{note_id}", response_model=Note)
async def update_note(
    note_id: int,
    body: str = Form(...),
    image: UploadFile = File(None),
    plant_id: Optional[int] = Form(None),
    seed_packet_id: Optional[int] = Form(None),
    garden_supply_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    db_note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if db_note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Handle image upload only if a file was actually uploaded
    if image and image.filename:
        # Delete old image if it exists
        delete_upload_file(db_note.image_path)
        # Save new image
        image_path = save_upload_file(image)
        db_note.image_path = image_path
    
    db_note.body = body
    db_note.plant_id = plant_id
    db_note.seed_packet_id = seed_packet_id
    db_note.garden_supply_id = garden_supply_id
    
    db.commit()
    db.refresh(db_note)
    return db_note

@app.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Delete image file if it exists
    delete_upload_file(note.image_path)
    
    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}

# Harvest endpoints
@app.post("/harvests/", response_model=Harvest)
def create_harvest(harvest: HarvestCreate, db: Session = Depends(get_db)):
    db_harvest = models.Harvest(**harvest.dict())
    db.add(db_harvest)
    db.commit()
    db.refresh(db_harvest)
    return db_harvest

@app.get("/harvests/", response_model=List[Harvest])
def list_harvests(plant_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(models.Harvest)
    if plant_id:
        query = query.filter(models.Harvest.plant_id == plant_id)
    return query.all()

@app.get("/harvests/{harvest_id}", response_model=Harvest)
def get_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
    if harvest is None:
        raise HTTPException(status_code=404, detail="Harvest not found")
    return harvest

@app.put("/harvests/{harvest_id}", response_model=Harvest)
def update_harvest(harvest_id: int, harvest: HarvestCreate, db: Session = Depends(get_db)):
    db_harvest = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
    if db_harvest is None:
        raise HTTPException(status_code=404, detail="Harvest not found")
    
    for key, value in harvest.dict().items():
        setattr(db_harvest, key, value)
    
    db.commit()
    db.refresh(db_harvest)
    return db_harvest

@app.delete("/harvests/{harvest_id}")
def delete_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
    if harvest is None:
        raise HTTPException(status_code=404, detail="Harvest not found")
    db.delete(harvest)
    db.commit()
    return {"message": "Harvest deleted"}

@app.post("/harvests/{harvest_id}/duplicate", response_model=Harvest)
async def duplicate_harvest(harvest_id: int, db: Session = Depends(get_db)):
    """Duplicate a harvest with all its properties except unique identifiers"""
    try:
        # Get the original harvest
        original = db.query(models.Harvest).filter(models.Harvest.id == harvest_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Harvest not found")

        # Create new harvest with same properties
        db_harvest = models.Harvest(
            plant_id=original.plant_id,
            weight_oz=original.weight_oz
        )

        db.add(db_harvest)
        db.commit()
        db.refresh(db_harvest)
        return db_harvest
    except Exception as e:
        logger.exception(f"Error duplicating harvest", extra={"harvest_id": harvest_id})
        raise DatabaseOperationException("create", str(e))

# HTML Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

@app.get("/plants", response_class=HTMLResponse)
async def plants_page(
    request: Request,
    name: Optional[str] = None,
    variety: Optional[str] = None,
    planting_method: Optional[str] = None,
    year_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    supply_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Plant)
    filters = {
        "name": name,
        "variety": variety,
        "planting_method": planting_method,
        "year_id": year_id,
        "seed_packet_id": seed_packet_id
    }
    query = apply_filters(query, models.Plant, filters)
    
    if supply_id:
        query = query.filter(models.Plant.supplies.any(id=supply_id))
    
    db_plants = query.order_by(models.Plant.name).all()
    plants = [Plant.from_orm(plant) for plant in db_plants]
    
    years = db.query(models.Year).order_by(models.Year.year.desc()).all()
    seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.name).all()
    supplies = db.query(models.GardenSupply).order_by(models.GardenSupply.name).all()
    
    return templates.TemplateResponse(
        "plants/list.html",
        {
            "request": request,
            "plants": plants,
            "planting_methods": list(PlantingMethod),
            "years": years,
            "seed_packets": seed_packets,
            "supplies": supplies,
            "filters": filters
        }
    )

@app.get("/plants/{plant_id}", response_class=HTMLResponse)
async def plant_detail(request: Request, plant_id: int, db: Session = Depends(get_db)):
    try:
        plant = db.query(models.Plant).filter(models.Plant.id == plant_id).first()
        if plant is None:
            logger.warning(f"Plant with ID {plant_id} not found")
            raise ResourceNotFoundException("Plant", plant_id)
            
        # Get all seed packets for the dropdown
        seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.name).all()
            
        logger.info(f"Retrieved plant details", extra={"plant_id": plant_id})
        return templates.TemplateResponse(
            "plants/detail.html",
            {
                "request": request,
                "plant": plant,
                "seed_packets": seed_packets,
                "planting_methods": list(PlantingMethod)
            }
        )
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving plant details", extra={"plant_id": plant_id})
        raise DatabaseOperationException("query", str(e))

@app.get("/seed-packets", response_class=HTMLResponse)
async def seed_packets_page(
    request: Request,
    name: Optional[str] = None,
    variety: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.SeedPacket)
    filters = {"name": name, "variety": variety}
    query = apply_filters(query, models.SeedPacket, filters)
    db_seed_packets = query.order_by(models.SeedPacket.name).all()
    
    # Convert SQLAlchemy models to Pydantic models for proper JSON serialization
    seed_packets = [SeedPacket.from_orm(packet) for packet in db_seed_packets]
    
    return templates.TemplateResponse(
        "seed_packets/list.html",
        {
            "request": request,
            "seed_packets": seed_packets,
            "filters": filters
        }
    )

@app.get("/seed-packets/{seed_packet_id}")
def get_seed_packet(seed_packet_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        seed_packet = db.query(models.SeedPacket).filter(models.SeedPacket.id == seed_packet_id).first()
        if seed_packet is None:
            raise ResourceNotFoundException("Seed Packet", seed_packet_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            # Sort notes by timestamp descending
            sorted_notes = sorted(seed_packet.notes, key=lambda x: x.timestamp, reverse=True)
            return templates.TemplateResponse(
                "seed_packets/detail.html",
                {
                    "request": request,
                    "seed_packet": seed_packet,
                    "notes": sorted_notes
                }
            )
        # API JSON response
        return seed_packet
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving seed packet", extra={"seed_packet_id": seed_packet_id})
        raise DatabaseOperationException("query", str(e))

@app.get("/garden-supplies", response_class=HTMLResponse)
async def garden_supplies_page(
    request: Request,
    name: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.GardenSupply)
    filters = {"name": name, "category": category}
    query = apply_filters(query, models.GardenSupply, filters)
    db_supplies = query.order_by(models.GardenSupply.name).all()
    
    # Convert SQLAlchemy models to Pydantic models for proper JSON serialization
    supplies = [GardenSupply.from_orm(supply) for supply in db_supplies]
    
    return templates.TemplateResponse(
        "garden_supplies/list.html",
        {
            "request": request,
            "supplies": supplies,
            "filters": filters
        }
    )

@app.get("/garden-supplies/{supply_id}")
def get_garden_supply(supply_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        supply = db.query(models.GardenSupply).filter(models.GardenSupply.id == supply_id).first()
        if supply is None:
            raise ResourceNotFoundException("Garden Supply", supply_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            # Sort notes by timestamp descending
            sorted_notes = sorted(supply.notes, key=lambda x: x.timestamp, reverse=True)
            return templates.TemplateResponse(
                "garden_supplies/detail.html",
                {
                    "request": request,
                    "supply": supply,
                    "notes": sorted_notes
                }
            )
        # API JSON response
        return supply
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving garden supply", extra={"supply_id": supply_id})
        raise DatabaseOperationException("query", str(e))

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(
    request: Request,
    plant_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    supply_id: Optional[int] = None,
    date_min: Optional[str] = Query(None, description="Minimum date in YYYY-MM-DD format"),
    date_max: Optional[str] = Query(None, description="Maximum date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    query = db.query(models.Note)
    
    # Convert string dates to datetime objects for filtering
    if date_min:
        query = query.filter(models.Note.timestamp >= datetime.fromisoformat(f"{date_min}T00:00:00"))
    if date_max:
        query = query.filter(models.Note.timestamp <= datetime.fromisoformat(f"{date_max}T23:59:59"))
    
    # Apply other filters
    filters = {
        "plant_id": plant_id,
        "seed_packet_id": seed_packet_id,
        "supply_id": supply_id
    }
    query = apply_filters(query, models.Note, filters)
    notes = query.order_by(models.Note.timestamp.desc()).all()
    
    # Get related objects for filtering dropdowns
    plants = db.query(models.Plant).order_by(models.Plant.name).all()
    seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.name).all()
    supplies = db.query(models.GardenSupply).order_by(models.GardenSupply.name).all()
    
    # Add date filters back for form display
    filters.update({
        "date_min": date_min,
        "date_max": date_max
    })
    
    return templates.TemplateResponse(
        "notes/list.html",
        {
            "request": request,
            "notes": notes,
            "plants": plants,
            "seed_packets": seed_packets,
            "supplies": supplies,
            "filters": filters
        }
    )

@app.get("/notes/{note_id}")
def get_note(note_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        note = db.query(models.Note).filter(models.Note.id == note_id).first()
        if note is None:
            raise ResourceNotFoundException("Note", note_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                "notes/detail.html",
                {
                    "request": request,
                    "note": note
                }
            )
        # API JSON response
        return note
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving note", extra={"note_id": note_id})
        raise DatabaseOperationException("query", str(e))

@app.get("/harvests", response_class=HTMLResponse)
async def harvests_page(
    request: Request,
    plant_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Harvest)
    filters = {"plant_id": plant_id}
    
    if plant_id:
        query = query.filter(models.Harvest.plant_id == plant_id)
    
    # Get all plants for the dropdown
    plants = db.query(models.Plant).order_by(models.Plant.name).all()
    
    # Get harvests with related plant info
    harvests = query.join(models.Plant).order_by(models.Harvest.timestamp.desc()).all()
    
    return templates.TemplateResponse(
        "harvests/list.html",
        {
            "request": request,
            "harvests": harvests,
            "plants": plants,
            "filters": filters
        }
    )