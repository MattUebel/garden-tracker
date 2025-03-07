from fastapi import APIRouter, Depends, Request, HTTPException, Form, File, UploadFile, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Optional
from sqlalchemy.orm import Session
import logging
from datetime import datetime
import os
import base64
import json
from mistralai import Mistral

from app.database import get_db
from app.models import SeedPacket as SeedPacketModel, Note as NoteModel
from app.schemas.seed_packets import SeedPacket, SeedPacketCreate
from app.forms.seed_packets import SeedPacketCreateForm
from app.utils import save_upload_file, delete_upload_file, apply_filters, validate_image
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
                
                # Generate new unique filename and path
                ext = os.path.splitext(original.image_path)[1]
                new_filename = f"{uuid4()}{ext}"
                
                # Use the correct container paths
                source_path = os.path.join("/app/app/static/uploads", os.path.basename(original.image_path))
                new_path = os.path.join("/app/app/static/uploads", new_filename)
                
                # Copy the file
                copyfile(source_path, new_path)
                db_seed_packet.image_path = f"/uploads/{new_filename}"
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
    """OCR extraction with structured data capabilities for seed packet images"""
    try:
        # Get the seed packet
        seed_packet = db.query(SeedPacketModel).filter(SeedPacketModel.id == seed_packet_id).first()
        if seed_packet is None:
            logger.error(f"Seed packet {seed_packet_id} not found")
            return JSONResponse(status_code=404, content={"error": "Seed packet not found"})
            
        # Check if there's an image
        if not seed_packet.image_path:
            logger.error(f"No image path for seed packet {seed_packet_id}")
            return JSONResponse(status_code=400, content={"error": "No image available for this seed packet"})
            
        # Get the API key
        api_key = get_mistral_api_key()
        if not api_key:
            logger.error("MISTRAL_API_KEY not set")
            return JSONResponse(status_code=500, content={"error": "MISTRAL_API_KEY not set"})
            
        # Initialize Mistral client
        from mistralai import Mistral, ImageURLChunk, TextChunk
        client = Mistral(api_key=api_key)
        
        # Extract just the filename from the database path
        filename = os.path.basename(seed_packet.image_path)
        logger.info(f"Image filename: {filename}")
        
        # This is the key fix - we know the exact path inside Docker container
        image_path = f"/app/app/static/uploads/{filename}"
        logger.info(f"Looking for image at Docker path: {image_path}")
        
        # Check if file exists
        if not os.path.exists(image_path):
            logger.error(f"Image file not found at Docker path: {image_path}")
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
            
        # Create data URL for API calls
        base64_data_url = f"data:image/{image_format};base64,{base64_image}"
        
        # Make OCR call using modern approach
        ocr_response = client.ocr.process(
            document=ImageURLChunk(image_url=base64_data_url),
            model="mistral-ocr-latest"
        )
        
        # Extract OCR text from response
        ocr_text = ""
        ocr_raw = {}
        
        if hasattr(ocr_response, 'pages') and ocr_response.pages:
            ocr_text = ocr_response.pages[0].markdown
            # Get raw response for debugging
            ocr_raw = json.loads(ocr_response.json())
        
        # If we get no text, provide a simple message
        if not ocr_text.strip():
            logger.warning("No text extracted from image")
            ocr_text = "No text could be extracted from the image."
            return JSONResponse(content={"status": "warning", "ocr_text": ocr_text})
        
        # Extract structured data using Pixtral model
        structured_data = {}
        try:
            # Use Pixtral to extract structured data from the image and OCR text
            logger.info("Calling Pixtral model for structured data extraction")
            chat_response = client.chat.complete(
                model="pixtral-12b-latest",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            ImageURLChunk(image_url=base64_data_url),
                            TextChunk(text=f"This is image's OCR in markdown:\n<BEGIN_IMAGE_OCR>\n{ocr_text}\n<END_IMAGE_OCR>.\nConvert this into a sensible structured JSON object with fields for name, variety, description, planting_instructions, days_to_germination, spacing, sun_exposure, soil_type, watering, fertilizer, package_weight. The output should be strictly JSON with no extra commentary.")
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            # Parse the structured response
            structured_data = json.loads(chat_response.choices[0].message.content)
            logger.info(f"Successfully extracted structured data: {json.dumps(structured_data)[:100]}...")
        except Exception as e:
            logger.warning(f"Error using Pixtral for structured data: {str(e)}")
            # Fall back to using ministral if pixtral fails
            try:
                logger.info("Falling back to Ministral model")
                chat_response = client.chat.complete(
                    model="ministral-8b-latest",
                    messages=[
                        {
                            "role": "user",
                            "content": f"This is image's OCR in markdown:\n<BEGIN_IMAGE_OCR>\n{ocr_text}\n<END_IMAGE_OCR>.\nConvert this into a sensible structured JSON object with fields for name, variety, description, planting_instructions, days_to_germination, spacing, sun_exposure, soil_type, watering, fertilizer, package_weight. The output should be strictly JSON with no extra commentary."
                        },
                    ],
                    response_format={"type": "json_object"},
                    temperature=0
                )
                structured_data = json.loads(chat_response.choices[0].message.content)
            except Exception as inner_e:
                logger.error(f"Error using fallback model: {str(inner_e)}")
                structured_data = {}
        
        # Create a note with the OCR results and structured data
        note_content = f"OCR Results:\n\n{ocr_text}\n\nStructured Data:\n\n{json.dumps(structured_data, indent=2)}"
        db_note = NoteModel(
            body=note_content,
            seed_packet_id=seed_packet_id
        )
        
        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        
        # Return both the OCR text and structured data
        return JSONResponse(content={
            "status": "success", 
            "ocr_text": ocr_text,
            "structured_data": structured_data
        })
        
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

@router.post("/seed-packets/ocr-temp")
async def process_temp_ocr(
    image: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Process OCR on a temporary image during seed packet creation"""
    try:
        # Check if there's an image
        if not image or not image.filename:
            return JSONResponse(status_code=400, content={"error": "No image file provided"})
            
        # Log that we're starting OCR processing
        logger.info(f"Starting OCR processing for temporary image: {image.filename}")
            
        # Get the API key
        api_key = get_mistral_api_key()
        if not api_key:
            logger.error("MISTRAL_API_KEY not set")
            return JSONResponse(status_code=500, content={"error": "MISTRAL_API_KEY not set"})
            
        # Initialize Mistral client - without the unsupported client_options
        from mistralai import Mistral, ImageURLChunk, TextChunk
        client = Mistral(api_key=api_key)
        
        # Validate and read the image
        try:
            validate_image(image)
            contents = await image.read()
            base64_image = base64.b64encode(contents).decode('utf-8')
            # Reset file pointer for potential future use
            await image.seek(0) if hasattr(image.seek, '__await__') else image.file.seek(0)
            
            logger.info(f"Image read successfully, size: {len(contents)} bytes")
        except Exception as e:
            logger.error(f"Error reading image: {str(e)}")
            return JSONResponse(status_code=400, content={"error": f"Invalid image: {str(e)}"})
            
        # Determine format from extension
        image_format = "jpeg"  # Default format
        if image.filename.lower().endswith(".png"):
            image_format = "png"
        elif image.filename.lower().endswith((".jpg", ".jpeg")):
            image_format = "jpeg"
            
        # Create data URL for API calls
        base64_data_url = f"data:image/{image_format};base64,{base64_image}"
        
        # Log before making OCR call
        logger.info("Making OCR API call to Mistral...")
        
        # Make OCR call using modern approach - with appropriate settings
        try:
            ocr_response = client.ocr.process(
                document=ImageURLChunk(image_url=base64_data_url),
                model="mistral-ocr-latest"
            )
            logger.info("OCR API call completed successfully")
        except Exception as e:
            logger.error(f"OCR API call failed: {str(e)}")
            return JSONResponse(status_code=500, content={"error": f"OCR processing failed: {str(e)}"})
        
        # Extract OCR text from response
        ocr_text = ""
        
        if hasattr(ocr_response, 'pages') and ocr_response.pages:
            ocr_text = ocr_response.pages[0].markdown
        
        # If we get no text, provide a simple message
        if not ocr_text.strip():
            logger.warning("No text extracted from image")
            return JSONResponse(content={
                "status": "warning", 
                "ocr_text": "No text could be extracted from the image.",
                "warning": "No text was detected in the image"
            })
        
        logger.info(f"OCR extracted text: {ocr_text[:200]}...")
        
        # Extract structured data using Pixtral model
        structured_data = {}
        try:
            # Use a simpler approach with only OCR text - faster and more reliable
            logger.info("Processing OCR text for structured data...")
            
            # Extract structured data from OCR text only - no image analysis (faster)
            text_extraction_prompt = f"""
I need to extract detailed information from a seed packet's OCR text.
Here's the text from the seed packet:

{ocr_text}

IMPORTANT FORMATTING GUIDELINES:
- For the "name" field, provide ONLY the basic plant type (Tomato, Carrot, Lettuce, etc.)
- For the "title" field, provide the full name as it appears on the packet 
- For the "variety" field, extract the specific cultivar name separate from the basic name

For example:
- If the text mentions "Roma Tomatoes", then name="Tomato", variety="Roma"
- If the text mentions "Jubilee Tomato", then name="Tomato", variety="Jubilee"
- If the text mentions "Cherry Belle Radish", then name="Radish", variety="Cherry Belle"

Extract these specific fields in JSON format:
- name: Basic plant type (just "Tomato", "Carrot", etc.) without varieties
- title: The complete name as shown on the packet
- variety: Specific variety or cultivar name
- description: Brief description of the plant
- planting_instructions: How to plant the seeds
- days_to_germination: Number of days until germination
- spacing: Recommended spacing between plants
- sun_exposure: Light requirements
- soil_type: Soil requirements
- watering: Watering needs
- fertilizer: Fertilizer instructions
- package_weight: Weight in grams with unit (e.g., "100 mg", "5 g")

Return ONLY a JSON object with these fields. Use null for missing information.
"""
            
            # Set a shorter timeout for this call
            chat_response = client.chat.complete(
                model=MISTRAL_CHAT_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": text_extraction_prompt
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            
            structured_data = json.loads(chat_response.choices[0].message.content)
            logger.info(f"Successfully extracted structured data: {json.dumps(structured_data)[:100]}...")
            
        except Exception as e:
            logger.warning(f"Error extracting structured data: {str(e)}")
            structured_data = {}  # Return empty object on error
        
        # Return the OCR text and any structured data we managed to extract
        logger.info("OCR processing completed, returning results")
        return JSONResponse(content={
            "status": "success", 
            "ocr_text": ocr_text,
            "structured_data": structured_data
        })
        
    except Exception as e:
        logger.exception(f"Error in temp OCR: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"OCR failed: {str(e)}"})

@router.post("/seed-packets/extract-info")
async def extract_info_from_ocr_text(request: Request):
    """Extract structured data from OCR text for seed packet creation"""
    try:
        # Get the request body
        body = await request.json()
        ocr_text = body.get('ocr_text')
        
        if not ocr_text:
            return JSONResponse(status_code=400, content={"error": "No OCR text provided"})
            
        # Get API key
        api_key = get_mistral_api_key()
        if not api_key:
            return JSONResponse(status_code=500, content={"error": "MISTRAL_API_KEY not set"})

        # Initialize client
        client = Mistral(api_key=api_key)

        # Enhanced prompt for better extraction of name and variety
        prompt = f"""
I need to extract information from a seed packet's OCR text.
Here's the text from the seed packet:

{ocr_text}

IMPORTANT FORMATTING GUIDELINES:
- For the "name" field, provide ONLY the basic plant type (Tomato, Carrot, Lettuce, etc.)
- For the "title" field, provide the full name as it appears on the packet 
- For the "variety" field, extract the specific cultivar name separate from the basic name

For example:
- If the text mentions "Roma Tomatoes", then name="Tomato", variety="Roma"
- If the text mentions "Jubilee Tomato", then name="Tomato", variety="Jubilee"
- If the text mentions "Cherry Belle Radish", then name="Radish", variety="Cherry Belle"

Extract these specific fields in JSON format:
- name: Basic plant type (just "Tomato", "Carrot", etc.) without varieties
- title: The complete name as shown on the packet
- variety: Specific variety or cultivar name
- description: Brief description of the plant
- planting_instructions: How to plant the seeds
- days_to_germination: Number of days until germination
- spacing: Recommended spacing between plants
- sun_exposure: Light requirements
- soil_type: Soil requirements
- watering: Watering needs
- fertilizer: Fertilizer instructions
- package_weight: Weight in grams (just numeric value)
- expiration_date: Date in YYYY-MM-DD format (if available)

Return ONLY a JSON object with these fields. Use null for missing information.
"""
        # Simple message structure
        messages = [
            {"role": "user", "content": prompt}
        ]

        # Make API call
        chat_response = client.chat.complete(
            model=MISTRAL_CHAT_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0
        )

        # Extract response
        response_content = chat_response.choices[0].message.content
        
        # Parse the JSON
        try:
            extracted_data = json.loads(response_content)
            
            # Check if we got meaningful data
            meaningful_fields = ['name', 'title', 'variety', 'description']
            has_meaningful_data = any(extracted_data.get(field) for field in meaningful_fields)
            
            if not has_meaningful_data:
                logger.warning("No meaningful data extracted from OCR text")
                return JSONResponse(
                    status_code=400,
                    content={"error": "Could not extract meaningful information from the image text"}
                )
                
            return JSONResponse(content=extracted_data)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=500,
                content={"error": "Could not parse response as JSON"}
            )
            
    except Exception as e:
        logger.exception(f"Error extracting info: {str(e)}")
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