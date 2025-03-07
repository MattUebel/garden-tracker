from fastapi import Form, File, UploadFile
from typing import Optional

class GardenSupplyCreateForm:
    def __init__(
        self,
        name: str = Form(...),
        description: str = Form(None),
        image: UploadFile = File(None)
    ):
        self.name = name
        self.description = description
        self.image = image