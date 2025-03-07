from fastapi import Form, File, UploadFile
from typing import Optional

class NoteCreateForm:
    def __init__(
        self,
        body: str = Form(...),
        image: UploadFile = File(None),
        plant_id: Optional[int] = Form(None),
        seed_packet_id: Optional[int] = Form(None),
        garden_supply_id: Optional[int] = Form(None)
    ):
        self.body = body
        self.image = image
        self.plant_id = plant_id
        self.seed_packet_id = seed_packet_id
        self.garden_supply_id = garden_supply_id