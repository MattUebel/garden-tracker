from fastapi import Form, File, UploadFile
from datetime import datetime
from typing import Optional

class SeedPacketCreateForm:
    def __init__(
        self,
        name: str = Form(...),
        variety: str = Form(None),
        description: str = Form(None),
        planting_instructions: str = Form(None),
        days_to_germination: int = Form(None),
        spacing: str = Form(None),
        sun_exposure: str = Form(None),
        soil_type: str = Form(None),
        watering: str = Form(None),
        quantity: int = Form(...),
        image: UploadFile = File(None)
    ):
        self.name = name
        self.variety = variety
        self.description = description
        self.planting_instructions = planting_instructions
        self.days_to_germination = days_to_germination
        self.spacing = spacing
        self.sun_exposure = sun_exposure
        self.soil_type = soil_type
        self.watering = watering
        self.quantity = quantity
        self.image = image