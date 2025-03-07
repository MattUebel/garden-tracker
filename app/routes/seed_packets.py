from fastapi import APIRouter, Depends, Request, HTTPException, Form, File, UploadFile, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Optional
from sqlalchemy.orm import Session
import logging
from datetime import datetime
import os
import base64
from mistralai import Mistral

from app.database import get_db
from app.models import SeedPacket as SeedPacketModel, Note as NoteModel
from app.schemas.seed_packets import SeedPacket, SeedPacketCreate
from app.forms.seed_packets import SeedPacketCreateForm
from app.utils import save_upload_file, delete_upload_file, apply_filters
from app.exceptions import ResourceNotFoundException, DatabaseOperationException, FileUploadException
from app.config import get_mistral_api_key, MISTRAL_OCR_MODEL, MISTRAL_CHAT_MODEL

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

@router.post("/seed-packets/", response_model=SeedPacket)
async def create_seed_packet(
    form: SeedPacketCreateForm = Depends(),
    db: Session = Depends(get_db)
):
    image_path = None
    if form.image and form.image.filename:
        image_path = save_upload_file(form.image)
    
    db_seed_packet = SeedPacketModel(
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

@router.get("/seed-packets/", response_model=List[SeedPacket])
def list_seed_packets(db: Session = Depends(get_db)):
    return db.query(SeedPacketModel).all()

@router.get("/seed-packets/{seed_packet_id}")
def get_seed_packet(seed_packet_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
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

@router.put("/seed-packets/{seed_packet_id}", response_model=SeedPacket)
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
    db_seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
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

@router.post("/seed-packets/{seed_packet_id}/duplicate", response_model=SeedPacket)
async def duplicate_seed_packet(seed_packet_id: int, db: Session = Depends(get_db)):
    """Duplicate a seed packet with all its properties except unique identifiers"""
    try:
        # Get the original seed packet
        original = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
        if original is None:
            raise HTTPException(status_code=404, detail="Seed packet not found")

        # Create new seed packet with same properties
        db_seed_packet = SeedPacketModel(
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

@router.delete("/seed-packets/{seed_packet_id}")
def delete_seed_packet(seed_packet_id: int, db: Session = Depends(get_db)):
    seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
    if seed_packet is None:
        raise HTTPException(status_code=404, detail="Seed packet not found")
    
    # Delete image file if it exists
    delete_upload_file(seed_packet.image_path)
    
    db.delete(seed_packet)
    db.commit()
    return {"message": "Seed packet deleted"}

@router.post("/seed-packets/{seed_packet_id}/ocr")
async def process_seed_packet_ocr(
    seed_packet_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Simple OCR extraction for seed packet images"""
    try:
        # Get the seed packet
        seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
        if seed_packet is None:
            return JSONResponse(status_code=404, content={"error": "Seed packet not found"})
            
        # Check if there's an image
        if not seed_packet.image_path:
            return JSONResponse(status_code=400, content={"error": "No image available for this seed packet"})
            
        # Get the API key
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(status_code=500, content={"error": "MISTRAL_API_KEY not set"})
            
        # Initialize Mistral client
        client = Mistral(api_key=api_key)
        
        # Prepare the image path
        image_path = seed_packet.image_path
        if not image_path.startswith('/'):
            image_path = f"app/static/{image_path}"
        else:
            image_path = f"app{image_path}"
            
        logger.info(f"Processing OCR for seed packet image: {image_path}")
        
        # Check if file exists
        if not os.path.exists(image_path):
            return JSONResponse(status_code=404, content={"error": "Image file not found"})
            
        # Base64 encode the image
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
        # Determine format from extension
        image_format = "jpeg"  # Default format
        if image_path.lower().endswith(".png"):
            image_format = "png"
        elif image_path.lower().endswith((".jpg", ".jpeg")):
            image_format = "jpeg"
            
        # Make simple OCR call
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "image_url",
                "image_url": f"data:image/{image_format};base64,{base64_image}"
            }
        )
        
        # Extract text simply
        ocr_text = ""
        if hasattr(ocr_response, 'model_dump'):
            response_dict = ocr_response.model_dump()
            if "pages" in response_dict:
                for page in response_dict["pages"]:
                    if "markdown" in page:
                        ocr_text += page["markdown"] + "\n\n"
        
        # If we get no text, provide a simple message
        if not ocr_text.strip():
            ocr_text = "No text could be extracted from the image."
            
        # Create a note with the OCR results
        db_note = NoteModel(
            body=f"OCR Results:\n\n{ocr_text}",
            seed_packet_id=seed_packet_id
        )
        
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        
        # Return just the text
        return JSONResponse(content={"status": "success", "ocr_text": ocr_text})
        
    except Exception as e:
        logger.exception(f"Error in OCR: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"OCR failed: {str(e)}"})

@router.post("/seed-packets/{seed_packet_id}/extract-data")
async def extract_data_from_ocr(
    seed_packet_id: int,
    request: Request,
    ocr_text: str = Form(...),
    db: Session = Depends(get_db)
):
    """Extract structured data from OCR text"""
    try:
        # Basic validation
        seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
        if seed_packet is None:
            return JSONResponse(status_code=404, content={"error": "Seed packet not found"})

        # Get API key
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(status_code=500, content={"error": "MISTRAL_API_KEY not set"})

        # Initialize client
        client = Mistral(api_key=api_key)

        # Simple prompt
        prompt = f"""
Extract these fields from the seed packet text (return as JSON):
- name: Plant name (e.g., "Tomato")
- variety: Variety name (e.g., "Roma")
- description: Brief description
- planting_instructions: How to plant
- days_to_germination: Number of days (just the number)
- spacing: Recommended spacing
- sun_exposure: Light requirements
- soil_type: Soil preferences
- watering: Watering instructions
- fertilizer: Fertilizer recommendations
- package_weight: Weight in grams (just the number)
- expiration_date: Date in YYYY-MM-DD format

Only return a JSON object with these fields. Use null for missing information.

Text from seed packet:
{ocr_text}
"""
        # Simple message structure
        messages = [
            {"role": "user", "content": prompt}
        ]

        # Make API call
        chat_response = client.chat.complete(
            model=MISTRAL_CHAT_MODEL,
            messages=messages
        )

        # Extract response
        response_content = chat_response.choices[0].message.content
        
        # Basic parsing
        import json
        try:
            extracted_data = json.loads(response_content)
            return JSONResponse(content=extracted_data)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=500,
                content={"error": "Could not parse response as JSON"}
            )
            
    except Exception as e:
        logger.exception(f"Error extracting data: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Data extraction failed: {str(e)}"}
        )

@router.get("/seed-packets", response_class=HTMLResponse)
async def seed_packets_page(
    request: Request,
    name: Optional[str] = None,
    variety: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(SeedPacketModel)
    filters = {"name": name, "variety": variety}
    query = apply_filters(query, SeedPacketModel, filters)
    db_seed_packets = query.order_by(SeedPacketModel.name).all()
    
    # Convert SQLAlchemy models to Pydantic models and ensure relationships are loaded
    seed_packets = []
    for packet in db_seed_packets:
        pydantic_packet = SeedPacket.from_orm(packet)
        # Load relationships explicitly to ensure they're available in the template
        pydantic_packet.plants = packet.plants
        seed_packets.append(pydantic_packet)
    
    return templates.TemplateResponse(
        "seed_packets/list.html",
        {
            "request": request,
            "seed_packets": seed_packets,
            "filters": filters
        }
    )