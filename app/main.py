from fastapi import FastAPI, Depends, HTTPException, Query, Request, File, UploadFile, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional
import logging
from datetime import datetime
from . import models
from .database import SessionLocal, engine
from .logging_config import setup_logging
from .exceptions import GardenBaseException, ResourceNotFoundException, ValidationException, FileUploadException, DatabaseOperationException
from pydantic import BaseModel
import enum
import os
from .utils import save_upload_file, delete_upload_file, apply_filters
from .models.plant import PlantingMethod

# Setup logging
logger = setup_logging()

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Garden Tracker API")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

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

# Pydantic models for request/response
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

    class Config:
        orm_mode = True

class SeedPacketBase(BaseModel):
    name: str
    quantity: int
    image_path: Optional[str] = None

class SeedPacketCreate(SeedPacketBase):
    pass

class SeedPacket(SeedPacketBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class SeedPacketCreateForm:
    def __init__(
        self,
        name: str = Form(...),
        quantity: int = Form(...),
        image: UploadFile = File(None)
    ):
        self.name = name
        self.quantity = quantity
        self.image = image

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
        orm_mode = True

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
        orm_mode = True

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

class HarvestBase(BaseModel):
    weight_oz: float
    plant_id: int

class HarvestCreate(HarvestBase):
    pass

class Harvest(HarvestBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True

class Year(BaseModel):
    year: int

    class Config:
        orm_mode = True

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        # Get summary data for the dashboard
        plants = db.query(models.Plant).order_by(models.Plant.created_at.desc()).limit(5).all()
        notes = db.query(models.Note).order_by(models.Note.timestamp.desc()).limit(5).all()
        seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.created_at.desc()).limit(5).all()
        supplies = db.query(models.GardenSupply).order_by(models.GardenSupply.created_at.desc()).limit(5).all()
        
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

        db_plant = models.Plant(**plant.dict(), year_id=current_year.year)
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
    
    for key, value in plant.dict().items():
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

@app.put("/seed-packets/{seed_packet_id}", response_model=SeedPacket)
async def update_seed_packet(
    seed_packet_id: int,
    name: str = Form(...),
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
    
    db_seed_packet.name = name
    db_seed_packet.quantity = quantity
    
    db.commit()
    db.refresh(db_seed_packet)
    return db_seed_packet

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
    form: NoteCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    image_path = None
    if form.image and form.image.filename:  # Check both that image exists and has a filename
        image_path = save_upload_file(form.image)
    
    db_note = models.Note(
        body=form.body,
        image_path=image_path,
        plant_id=form.plant_id,
        seed_packet_id=form.seed_packet_id,
        garden_supply_id=form.garden_supply_id
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
    
    plants = query.order_by(models.Plant.name).all()
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
    seed_packets = query.order_by(models.SeedPacket.name).all()
    
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
    supplies = query.order_by(models.GardenSupply.name).all()
    
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
    date_min: Optional[datetime] = None,
    date_max: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Note)
    filters = {
        "plant_id": plant_id,
        "seed_packet_id": seed_packet_id,
        "supply_id": supply_id,
        "timestamp_min": date_min,
        "timestamp_max": date_max
    }
    query = apply_filters(query, models.Note, filters)
    notes = query.order_by(models.Note.timestamp.desc()).all()
    
    # Get related objects for filtering dropdowns
    plants = db.query(models.Plant).order_by(models.Plant.name).all()
    seed_packets = db.query(models.SeedPacket).order_by(models.SeedPacket.name).all()
    supplies = db.query(models.GardenSupply).order_by(models.GardenSupply.name).all()
    
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