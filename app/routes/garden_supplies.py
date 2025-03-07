from fastapi import APIRouter, Depends, Request, HTTPException, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import List, Optional
from sqlalchemy.orm import Session
import logging

from app.database import get_db
from app.models import GardenSupply as GardenSupplyModel, Note as NoteModel
from app.schemas.garden_supplies import GardenSupply, GardenSupplyCreate
from app.forms.garden_supplies import GardenSupplyCreateForm
from app.utils import save_upload_file, delete_upload_file, apply_filters
from app.exceptions import ResourceNotFoundException, DatabaseOperationException

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/garden-supplies/", response_model=GardenSupply)
async def create_garden_supply(
    form: GardenSupplyCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    try:
        image_path = None
        if form.image and form.image.filename:
            image_path = save_upload_file(form.image)

        db_garden_supply = GardenSupplyModel(
            name=form.name,
            description=form.description,
            image_path=image_path
        )
        db.add(db_garden_supply)
        db.commit()
        db.refresh(db_garden_supply)
        return db_garden_supply
    except Exception as e:
        logger.exception("Failed to create garden supply")
        raise DatabaseOperationException("create", str(e))

@router.get("/garden-supplies/", response_model=List[GardenSupply])
def list_garden_supplies(db: Session = Depends(get_db)):
    return db.query(GardenSupplyModel).all()

@router.get("/garden-supplies/{garden_supply_id}")
def get_garden_supply(garden_supply_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        garden_supply = db.query(GardenSupplyModel).filter(GardenSupplyModel.id == garden_supply_id).first()
        if garden_supply is None:
            raise ResourceNotFoundException("Garden Supply", garden_supply_id)
            
        # HTML response
        if "text/html" in request.headers.get("accept", ""):
            # Sort notes by timestamp descending
            sorted_notes = sorted(garden_supply.notes, key=lambda x: x.timestamp, reverse=True)
            
            return templates.TemplateResponse(
                "garden_supplies/detail.html",
                {
                    "request": request,
                    "garden_supply": garden_supply,
                    "notes": sorted_notes
                }
            )
        # API JSON response
        return garden_supply
            
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error retrieving garden supply", extra={"garden_supply_id": garden_supply_id})
        raise DatabaseOperationException("query", str(e))

@router.put("/garden-supplies/{garden_supply_id}", response_model=GardenSupply)
async def update_garden_supply(
    garden_supply_id: int,
    name: str = Form(...),
    description: str = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    db_garden_supply = db.query(GardenSupplyModel).filter(GardenSupplyModel.id == garden_supply_id).first()
    if db_garden_supply is None:
        raise HTTPException(status_code=404, detail="Garden supply not found")
    
    # Handle image upload only if a file was actually uploaded
    if image and image.filename:
        # Delete old image if it exists
        delete_upload_file(db_garden_supply.image_path)
        # Save new image
        image_path = save_upload_file(image)
        db_garden_supply.image_path = image_path
    
    db_garden_supply.name = name
    db_garden_supply.description = description
    
    db.commit()
    db.refresh(db_garden_supply)
    return db_garden_supply

@router.delete("/garden-supplies/{garden_supply_id}")
def delete_garden_supply(garden_supply_id: int, db: Session = Depends(get_db)):
    garden_supply = db.query(GardenSupplyModel).filter(GardenSupplyModel.id == garden_supply_id).first()
    if garden_supply is None:
        raise HTTPException(status_code=404, detail="Garden supply not found")
    
    # Delete image file if it exists
    delete_upload_file(garden_supply.image_path)
    
    db.delete(garden_supply)
    db.commit()
    return {"message": "Garden supply deleted"}

@router.get("/garden-supplies", response_class=HTMLResponse)
async def garden_supplies_page(
    request: Request,
    name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(GardenSupplyModel)
    
    filters = {"name": name}
    query = apply_filters(query, GardenSupplyModel, filters)
    
    db_garden_supplies = query.order_by(GardenSupplyModel.name).all()
    garden_supplies = [GardenSupply.from_orm(supply) for supply in db_garden_supplies]
    
    return templates.TemplateResponse(
        "garden_supplies/list.html",
        {
            "request": request,
            "garden_supplies": garden_supplies,
            "filters": filters
        }
    )

@router.post("/garden-supplies/{garden_supply_id}/duplicate", response_model=GardenSupply)
async def duplicate_garden_supply(garden_supply_id: int, db: Session = Depends(get_db)):
    """Duplicate a garden supply with all its properties except unique identifiers"""
    try:
        # Get the original garden supply
        original = db.query(GardenSupplyModel).filter(GardenSupplyModel.id == garden_supply_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Garden supply not found")

        # Create new garden supply with same properties
        db_garden_supply = GardenSupplyModel(
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
                new_path = os.path.join("data/uploads", new_filename)
                
                # Copy the file
                copyfile(os.path.join("data/uploads", os.path.basename(original.image_path)), new_path)
                db_garden_supply.image_path = f"/uploads/{os.path.basename(new_path)}"
            except Exception as e:
                logger.warning(f"Failed to copy image for duplicated garden supply: {str(e)}")
                # Continue without the image if copy fails
                pass

        db.add(db_garden_supply)
        db.commit()
        db.refresh(db_garden_supply)
        return db_garden_supply
    except Exception as e:
        logger.exception(f"Error duplicating garden supply", extra={"garden_supply_id": garden_supply_id})
        raise DatabaseOperationException("create", str(e))