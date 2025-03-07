#!/usr/bin/env python3
import argparse
import base64
import os
import json
from pathlib import Path
from mistralai import Mistral
from mistralai import DocumentURLChunk, ImageURLChunk, TextChunk

def get_mistral_api_key():
    """Get Mistral API key from environment"""
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable is not set")
    return api_key

def process_image(image_path):
    """Process an image through Mistral's OCR endpoint and extract structured data"""
    # Convert to Path object for better file handling
    image_file = Path(image_path)
    if not image_file.is_file():
        raise ValueError(f"Image file not found: {image_path}")
    
    # Read and encode image using modern Path methods
    encoded = base64.b64encode(image_file.read_bytes()).decode()
    
    # Determine format from extension
    image_format = "jpeg"  # Default format
    if image_path.lower().endswith(".png"):
        image_format = "png"
    elif image_path.lower().endswith((".jpg", ".jpeg")):
        image_format = "jpeg"
    
    # Create data URL
    base64_data_url = f"data:image/{image_format};base64,{encoded}"
    
    # Initialize client
    client = Mistral(api_key=get_mistral_api_key())
    
    # Make OCR call using the modern approach
    ocr_response = client.ocr.process(
        document=ImageURLChunk(image_url=base64_data_url), 
        model="mistral-ocr-latest"
    )
    
    # Get OCR response as dictionary for raw output
    raw_response = json.loads(ocr_response.json())
    
    # Extract OCR markdown text from the response
    ocr_text = ""
    if hasattr(ocr_response, 'pages') and ocr_response.pages:
        image_ocr_markdown = ocr_response.pages[0].markdown
        ocr_text = image_ocr_markdown
    
    # Extract structured data from OCR text using Pixtral model
    structured_data = {}
    try:
        # Use Pixtral to extract structured data from the image and OCR text
        chat_response = client.chat.complete(
            model="pixtral-12b-latest",
            messages=[
                {
                    "role": "user",
                    "content": [
                        ImageURLChunk(image_url=base64_data_url),
                        TextChunk(text=f"This is image's OCR in markdown:\n<BEGIN_IMAGE_OCR>\n{ocr_text}\n<END_IMAGE_OCR>.\nConvert this into a sensible structured json response. The output should be strictly be json with no extra commentary")
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        # Parse the structured response
        structured_data = json.loads(chat_response.choices[0].message.content)
    except Exception as e:
        print(f"Error extracting structured data: {str(e)}")
        # Fall back to using ministral if pixtral fails
        try:
            chat_response = client.chat.complete(
                model="ministral-8b-latest",
                messages=[
                    {
                        "role": "user",
                        "content": f"This is image's OCR in markdown:\n<BEGIN_IMAGE_OCR>\n{ocr_text}\n<END_IMAGE_OCR>.\nConvert this into a sensible structured json response. The output should be strictly be json with no extra commentary"
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0
            )
            structured_data = json.loads(chat_response.choices[0].message.content)
        except Exception as inner_e:
            print(f"Error using fallback model: {str(inner_e)}")
    
    return ocr_text, raw_response, structured_data

def main():
    parser = argparse.ArgumentParser(description='Test Mistral OCR API with an image')
    parser.add_argument('image_path', help='Path to the image file to process')
    parser.add_argument('--raw', action='store_true', help='Output raw JSON response')
    parser.add_argument('--structured', action='store_true', help='Output structured data (default)')
    args = parser.parse_args()
    
    try:
        ocr_text, raw_response, structured_data = process_image(args.image_path)
        
        if args.raw:
            print("Raw API response:")
            print(json.dumps(raw_response, indent=2))
        else:
            print("Extracted text:")
            print(ocr_text)
            
        # Always show structured data unless specifically asked for only raw
        if args.structured or not args.raw:
            print("\nStructured data:")
            print(json.dumps(structured_data, indent=2))
            
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()