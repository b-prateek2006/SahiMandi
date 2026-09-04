from fastapi import APIRouter

from app.models import Farmer, SessionLocal
from app.schemas import FarmerRegistration, FarmerView


router = APIRouter(tags=["farmers"])


@router.post("/farmers", response_model=FarmerView)
def register_farmer(data: FarmerRegistration) -> FarmerView:
    with SessionLocal.begin() as session:
        farmer = Farmer(**data.model_dump())
        session.add(farmer)
        session.flush()
        return FarmerView(id=farmer.id, **data.model_dump())
