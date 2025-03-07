from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from datetime import datetime, date
import logging

from app.database import get_db
from app.models import Harvest as HarvestModel, Plant as PlantModel
from app.schemas.harvests import Harvest, HarvestCreate
from app.exceptions import ResourceNotFoundException, DatabaseOperationException

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/harvests/", response_model=Harvest)
def create_harvest(harvest: HarvestCreate, db: Session = Depends(get_db)):
    db_harvest = HarvestModel(**harvest.dict())
    db.add(db_harvest)
    db.commit()
    db.refresh(db_harvest)
    return db_harvest

@router.get("/harvests/", response_model=List[Harvest])
def list_harvests(
    plant_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db)
):
    query = db.query(HarvestModel)
    if plant_id:
        query = query.filter(HarvestModel.plant_id == plant_id)
    if date_from:
        query = query.filter(HarvestModel.timestamp >= date_from)
    if date_to:
        query = query.filter(HarvestModel.timestamp <= date_to)
    return query.all()

@router.get("/harvests/{harvest_id}")
def get_harvest(harvest_id: int, db: Session = Depends(get_db)):
    try:
        harvest = db.query(HarvestModel).filter(HarvestModel.id == harvest_id).first()
        if harvest is None:
            raise ResourceNotFoundException("Harvest", harvest_id)
        return harvest
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving harvest", extra={"harvest_id": harvest_id})
        raise DatabaseOperationException("query", str(e))

@router.put("/harvests/{harvest_id}", response_model=Harvest)
def update_harvest(harvest_id: int, harvest: HarvestCreate, db: Session = Depends(get_db)):
    db_harvest = db.query(HarvestModel).filter(HarvestModel.id == harvest_id).first()
    if db_harvest is None:
        raise HTTPException(status_code=404, detail="Harvest not found")
    
    for key, value in harvest.dict().items():
        setattr(db_harvest, key, value)
    
    db.commit()
    db.refresh(db_harvest)
    return db_harvest

@router.delete("/harvests/{harvest_id}")
def delete_harvest(harvest_id: int, db: Session = Depends(get_db)):
    harvest = db.query(HarvestModel).filter(HarvestModel.id == harvest_id).first()
    if harvest is None:
        raise HTTPException(status_code=404, detail="Harvest not found")
    db.delete(harvest)
    db.commit()
    return {"message": "Harvest deleted"}

@router.get("/harvests", response_class=HTMLResponse)
async def harvests_page(
    request: Request,
    plant_id: Optional[int] = None,
    date_min: Optional[str] = Query(None, description="Minimum date in YYYY-MM-DD format"),
    date_max: Optional[str] = Query(None, description="Maximum date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    from app.utils import apply_filters
    
    query = db.query(HarvestModel)
    
    # Convert string dates to datetime objects for filtering
    if date_min:
        query = query.filter(HarvestModel.timestamp >= datetime.fromisoformat(f"{date_min}T00:00:00"))
    if date_max:
        query = query.filter(HarvestModel.timestamp <= datetime.fromisoformat(f"{date_max}T23:59:59"))
    
    # Apply plant filter
    if plant_id:
        query = query.filter(HarvestModel.plant_id == plant_id)
    
    # Get the harvests ordered by timestamp
    harvests = query.order_by(HarvestModel.timestamp.desc()).all()
    
    # Get plants for dropdown filter
    plants = db.query(PlantModel).order_by(PlantModel.name).all()
    
    # Calculate summary statistics
    total_weight = sum(harvest.weight_oz for harvest in harvests)
    
    # Calculate monthly stats
    monthly_stats = []
    if harvests:
        # Query for monthly totals
        monthly_totals = (
            db.query(
                extract('year', HarvestModel.timestamp).label('year'),
                extract('month', HarvestModel.timestamp).label('month'),
                func.sum(HarvestModel.weight_oz).label('total_weight')
            )
            .filter(HarvestModel.plant_id == plant_id if plant_id else True)
            .group_by(
                extract('year', HarvestModel.timestamp),
                extract('month', HarvestModel.timestamp)
            )
            .order_by(
                extract('year', HarvestModel.timestamp).desc(),
                extract('month', HarvestModel.timestamp).desc()
            )
            .all()
        )
        
        for year, month, weight in monthly_totals:
            month_date = date(int(year), int(month), 1)
            month_name = month_date.strftime("%B %Y")
            monthly_stats.append({
                "month": month_name,
                "weight_oz": weight,
                "weight_lbs": weight / 16
            })
    
    # Get plant-specific stats if needed
    plant_stats = None
    if plant_id:
        plant = db.query(PlantModel).filter(PlantModel.id == plant_id).first()
        if plant:
            plant_stats = {
                "name": plant.name,
                "variety": plant.variety,
                "total_weight_oz": total_weight,
                "total_weight_lbs": total_weight / 16
            }
    
    # Add filters for form display
    filters = {
        "plant_id": plant_id,
        "date_min": date_min,
        "date_max": date_max
    }
    
    return templates.TemplateResponse(
        "harvests/list.html",
        {
            "request": request,
            "harvests": harvests,
            "plants": plants,
            "filters": filters,
            "total_weight": total_weight,
            "total_weight_lbs": total_weight / 16 if total_weight else 0,
            "monthly_stats": monthly_stats,
            "plant_stats": plant_stats
        }
    )