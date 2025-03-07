from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import extract
from datetime import datetime
import logging

from app.database import get_db
from app.models.plant import PlantingMethod
from app.models import Plant as PlantModel, Year as YearModel, SeedPacket as SeedPacketModel
from app.schemas.plants import Plant, PlantCreate
from app.exceptions import ResourceNotFoundException, DatabaseOperationException

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/plants/", response_model=Plant)
def create_plant(plant: PlantCreate, db: Session = Depends(get_db)):
    try:
        logger.info("Creating new plant", extra={"plant_data": plant.dict()})
        
        current_year = db.query(YearModel).filter(
            YearModel.year == extract('year', datetime.now())
        ).first()
        
        if not current_year:
            current_year = YearModel(year=datetime.now().year)
            db.add(current_year)
            db.commit()
            db.refresh(current_year)

        # Create plant data dict and remove seed_packet_id if it's empty
        plant_data = plant.dict()
        if not plant_data.get('seed_packet_id'):
            plant_data.pop('seed_packet_id', None)

        db_plant = PlantModel(**plant_data, year_id=current_year.year)
        db.add(db_plant)
        db.commit()
        db.refresh(db_plant)
        
        logger.info("Plant created successfully", extra={"plant_id": db_plant.id})
        return db_plant
        
    except Exception as e:
        logger.exception("Failed to create plant")
        raise DatabaseOperationException("create", str(e))

@router.get("/plants/", response_model=List[Plant])
def list_plants(
    planting_method: Optional[PlantingMethod] = None,
    variety: Optional[str] = None,
    year: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(PlantModel)
    if planting_method:
        query = query.filter(PlantModel.planting_method == planting_method)
    if variety:
        query = query.filter(PlantModel.variety == variety)
    if year:
        query = query.filter(PlantModel.year_id == year)
    if seed_packet_id:
        query = query.filter(PlantModel.seed_packet_id == seed_packet_id)
    return query.all()

@router.get("/plants/{plant_id}")
def get_plant(plant_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        plant = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
        if plant is None:
            raise ResourceNotFoundException("Plant", plant_id)
            
        # Get all seed packets for the dropdown
        seed_packets = db.query(SeedPacketModel).order_by(SeedPacketModel.name).all()
            
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
        # API JSON response
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

@router.put("/plants/{plant_id}", response_model=Plant)
def update_plant(plant_id: int, plant: PlantCreate, db: Session = Depends(get_db)):
    db_plant = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
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

@router.delete("/plants/{plant_id}")
def delete_plant(plant_id: int, db: Session = Depends(get_db)):
    plant = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
    if plant is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    db.delete(plant)
    db.commit()
    return {"message": "Plant deleted"}

@router.post("/plants/{plant_id}/duplicate", response_model=Plant)
async def duplicate_plant(plant_id: int, db: Session = Depends(get_db)):
    """Duplicate a plant with all its properties except unique identifiers"""
    try:
        # Get the original plant
        original = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Plant not found")

        # Create new plant with same properties
        db_plant = PlantModel(
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

@router.get("/plants", response_class=HTMLResponse)
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
    from app.utils import apply_filters
    
    query = db.query(PlantModel)
    filters = {
        "name": name,
        "variety": variety,
        "planting_method": planting_method,
        "year_id": year_id,
        "seed_packet_id": seed_packet_id
    }
    query = apply_filters(query, PlantModel, filters)
    
    if supply_id:
        query = query.filter(PlantModel.supplies.any(id=supply_id))
    
    db_plants = query.order_by(PlantModel.name).all()
    plants = [Plant.from_orm(plant) for plant in db_plants]
    
    years = db.query(YearModel).order_by(YearModel.year.desc()).all()
    seed_packets = db.query(SeedPacketModel).order_by(SeedPacketModel.name).all()
    
    # Importing here to avoid circular imports
    from app.models import GardenSupply as GardenSupplyModel
    supplies = db.query(GardenSupplyModel).order_by(GardenSupplyModel.name).all()
    
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

@router.get("/plants/{plant_id}", response_class=HTMLResponse)
async def plant_detail(request: Request, plant_id: int, db: Session = Depends(get_db)):
    try:
        plant = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
        if plant is None:
            logger.warning(f"Plant with ID {plant_id} not found")
            raise ResourceNotFoundException("Plant", plant_id)
            
        # Get all seed packets for the dropdown
        seed_packets = db.query(SeedPacketModel).order_by(SeedPacketModel.name).all()
            
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