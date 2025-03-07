#!/usr/bin/env python3
import argparse
import base64
import os
from mistralai import Mistral
import json

def get_mistral_api_key():
    """Get Mistral API key from environment"""
    api_key = os.getenv('MISTRAL_API_KEY')
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable is not set")
    return api_key

def process_image(image_path):
    """Process an image through Mistral's OCR endpoint"""
    # Read and encode image
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Determine format from extension
    image_format = "jpeg"  # Default format
    if image_path.lower().endswith(".png"):
        image_format = "png"
    elif image_path.lower().endswith((".jpg", ".jpeg")):
        image_format = "jpeg"
    
    # Initialize client
    client = Mistral(api_key=get_mistral_api_key())
    
    # Make OCR call
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "image_url",
            "image_url": f"data:image/{image_format};base64,{base64_image}"
        }
    )
    
    # Extract text
    ocr_text = ""
    if hasattr(ocr_response, 'model_dump'):
        response_dict = ocr_response.model_dump()
        if "pages" in response_dict:
            for page in response_dict["pages"]:
                if "markdown" in page:
                    ocr_text += page["markdown"] + "\n\n"
    
    return ocr_text, response_dict

def main():
    parser = argparse.ArgumentParser(description='Test Mistral OCR API with an image')
    parser.add_argument('image_path', help='Path to the image file to process')
    parser.add_argument('--raw', action='store_true', help='Output raw JSON response')
    args = parser.parse_args()
    
    try:
        ocr_text, raw_response = process_image(args.image_path)
        
        if args.raw:
            print("Raw API response:")
            print(json.dumps(raw_response, indent=2))
        else:
            print("Extracted text:")
            print(ocr_text)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()