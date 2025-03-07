from fastapi import APIRouter, Depends, Query, Request, File, Form, UploadFile, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.database import get_db
from app.models import Note as NoteModel, Plant as PlantModel, SeedPacket as SeedPacketModel, GardenSupply as GardenSupplyModel
from app.schemas.notes import Note, NoteCreate
from app.forms.notes import NoteCreateForm
from app.utils import save_upload_file, delete_upload_file, apply_filters
from app.exceptions import ResourceNotFoundException, DatabaseOperationException

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/notes/", response_model=Note)
async def create_note(
    form: NoteCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    try:
        image_path = None
        if form.image and form.image.filename:
            image_path = save_upload_file(form.image)
        
        db_note = NoteModel(
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
    except Exception as e:
        logger.exception("Failed to create note")
        raise DatabaseOperationException("create", str(e))

@router.get("/notes/", response_model=List[Note])
def list_notes(
    plant_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    garden_supply_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(NoteModel)
    if plant_id:
        query = query.filter(NoteModel.plant_id == plant_id)
    if seed_packet_id:
        query = query.filter(NoteModel.seed_packet_id == seed_packet_id)
    if garden_supply_id:
        query = query.filter(NoteModel.garden_supply_id == garden_supply_id)
    return query.all()

@router.get("/notes/{note_id}")
def get_note(note_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        note = db.query(NoteModel).filter(NoteModel.id == note_id).first()
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

@router.put("/notes/{note_id}", response_model=Note)
async def update_note(
    note_id: int,
    body: str = Form(...),
    image: UploadFile = File(None),
    plant_id: Optional[int] = Form(None),
    seed_packet_id: Optional[int] = Form(None),
    garden_supply_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    db_note = db.query(NoteModel).filter(NoteModel.id == note_id).first()
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

@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(NoteModel).filter(NoteModel.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    
    # Delete image file if it exists
    delete_upload_file(note.image_path)
    
    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}

@router.get("/notes", response_class=HTMLResponse)
async def notes_page(
    request: Request,
    plant_id: Optional[int] = None,
    seed_packet_id: Optional[int] = None,
    supply_id: Optional[int] = None,
    date_min: Optional[str] = Query(None, description="Minimum date in YYYY-MM-DD format"),
    date_max: Optional[str] = Query(None, description="Maximum date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    query = db.query(NoteModel)
    
    # Convert string dates to datetime objects for filtering
    if date_min:
        query = query.filter(NoteModel.timestamp >= datetime.fromisoformat(f"{date_min}T00:00:00"))
    if date_max:
        query = query.filter(NoteModel.timestamp <= datetime.fromisoformat(f"{date_max}T23:59:59"))
    
    # Apply other filters
    filters = {
        "plant_id": plant_id,
        "seed_packet_id": seed_packet_id,
        "garden_supply_id": supply_id
    }
    
    query = apply_filters(query, NoteModel, filters)
    notes = query.order_by(NoteModel.timestamp.desc()).all()
    
    # Get related objects for filtering dropdowns
    plants = db.query(PlantModel).order_by(PlantModel.name).all()
    seed_packets = db.query(SeedPacketModel).order_by(SeedPacketModel.name).all()
    supplies = db.query(GardenSupplyModel).order_by(GardenSupplyModel.name).all()
    
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