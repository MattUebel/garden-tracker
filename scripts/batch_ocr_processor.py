#!/usr/bin/env python3
"""
Batch OCR Processor for Seed Packet Images

This script processes a directory of images using Mistral OCR and caches the results as JSON files.
It can be used to batch process seed packet images for offline analysis or data extraction.

Usage:
    python batch_ocr_processor.py --input-dir /path/to/images --output-dir /path/to/output
"""

import os
import sys
import json
import base64
import argparse
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add the project root to the path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from mistralai import Mistral, ImageURLChunk, TextChunk
    from app.config import get_mistral_api_key
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you have installed all dependencies with: pip install -r requirements.txt")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("batch_ocr_processor")

def get_image_files(directory: str) -> List[str]:
    """Get all image files in the directory with common image extensions."""
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    image_files = []
    
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in valid_extensions):
                image_files.append(os.path.join(root, file))
    
    return image_files

def process_image(
    client: Mistral, 
    image_path: str, 
    extract_structured_data: bool = True
) -> Dict[str, Any]:
    """Process a single image with Mistral OCR and optionally extract structured data."""
    logger.info(f"Processing image: {image_path}")
    
    try:
        # Read and encode the image
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
        
        # Make OCR call
        logger.info("Calling Mistral OCR API...")
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
        
        # If no text extracted, log a warning
        if not ocr_text.strip():
            logger.warning(f"No text extracted from image: {image_path}")
            return {
                "status": "warning",
                "image_path": image_path,
                "ocr_text": "",
                "raw_ocr_data": ocr_raw,
                "structured_data": {},
                "timestamp": datetime.now().isoformat()
            }
        
        result = {
            "status": "success",
            "image_path": image_path,
            "ocr_text": ocr_text,
            "raw_ocr_data": ocr_raw,
            "timestamp": datetime.now().isoformat()
        }
        
        # Extract structured data if requested
        if extract_structured_data:
            try:
                logger.info("Extracting structured data from OCR text...")
                
                # Extract structured data from OCR text
                text_extraction_prompt = f"""
I need to extract detailed information from a seed packet's OCR text.
Here's the text from the seed packet:

{ocr_text}

IMPORTANT FORMATTING GUIDELINES:
- For the "name" field, provide ONLY the basic plant type (Tomato, Carrot, Lettuce, etc.) without varieties
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

Return ONLY a JSON object with these fields. Use null for missing information.
"""
                
                # Call the chat model
                chat_response = client.chat.complete(
                    model="mistral-large-latest",  # Using the large model for better extraction
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
                result["structured_data"] = structured_data
                logger.info(f"Successfully extracted structured data")
                
            except Exception as e:
                logger.warning(f"Error extracting structured data: {str(e)}")
                result["structured_data"] = {}
                result["extraction_error"] = str(e)
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {str(e)}")
        return {
            "status": "error",
            "image_path": image_path,
            "error_message": str(e),
            "timestamp": datetime.now().isoformat()
        }

def save_result(result: Dict[str, Any], output_dir: str) -> str:
    """Save the OCR result to a JSON file in the output directory."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate a filename based on the original image name
    image_path = result["image_path"]
    image_name = os.path.basename(image_path)
    base_name = os.path.splitext(image_name)[0]
    output_path = os.path.join(output_dir, f"{base_name}_ocr.json")
    
    # Save the result
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Process images in a directory with Mistral OCR and cache results")
    parser.add_argument("--input-dir", "-i", required=True, help="Directory containing images to process")
    parser.add_argument("--output-dir", "-o", required=True, help="Directory to store JSON results")
    parser.add_argument("--skip-existing", "-s", action="store_true", help="Skip files that already have OCR results")
    parser.add_argument("--no-structured-data", action="store_true", help="Skip structured data extraction")
    parser.add_argument("--delay", "-d", type=float, default=1.0, 
                        help="Delay in seconds between API calls to avoid rate limits")
    
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.isdir(args.input_dir):
        logger.error(f"Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Get Mistral API key
    api_key = get_mistral_api_key()
    if not api_key:
        logger.error("MISTRAL_API_KEY not set. Please set the environment variable.")
        sys.exit(1)
    
    # Initialize Mistral client
    client = Mistral(api_key=api_key)
    
    # Get all image files in the input directory
    image_files = get_image_files(args.input_dir)
    logger.info(f"Found {len(image_files)} image files in {args.input_dir}")
    
    # Process each image
    for index, image_file in enumerate(image_files):
        # Check if we should skip this file
        base_name = os.path.splitext(os.path.basename(image_file))[0]
        output_path = os.path.join(args.output_dir, f"{base_name}_ocr.json")
        
        if args.skip_existing and os.path.exists(output_path):
            logger.info(f"Skipping {image_file} (result file already exists)")
            continue
        
        logger.info(f"Processing image {index+1}/{len(image_files)}: {image_file}")
        
        # Process the image
        result = process_image(
            client, 
            image_file, 
            extract_structured_data=not args.no_structured_data
        )
        
        # Save the result
        output_path = save_result(result, args.output_dir)
        logger.info(f"Saved result to {output_path}")
        
        # Add delay between requests to avoid rate limits
        if index < len(image_files) - 1 and args.delay > 0:
            time.sleep(args.delay)
    
    logger.info(f"Processing complete. Results saved to {args.output_dir}")

if __name__ == "__main__":
    main()