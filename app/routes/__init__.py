from fastapi import APIRouter
from . import plants, seed_packets, notes, garden_supplies, harvests

# Create a main router that includes all entity routers
router = APIRouter()

# Include all entity routers
router.include_router(plants.router, tags=["plants"])
router.include_router(seed_packets.router, tags=["seed_packets"])
router.include_router(notes.router, tags=["notes"])
router.include_router(garden_supplies.router, tags=["garden_supplies"])
router.include_router(harvests.router, tags=["harvests"])