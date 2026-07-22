from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.profile import service
from app.profile.models import DEFAULT_USER_ID
from app.profile.schemas import (
    DreamBikeIn,
    DreamBikeOut,
    GarageBikeIn,
    GarageBikeOut,
    ProfileOut,
    ProfileUpdateIn,
)

router = APIRouter()


@router.get("/profile", response_model=ProfileOut)
def get_profile(db: Annotated[Session, Depends(get_db)]) -> ProfileOut:
    return service.get_profile(db, DEFAULT_USER_ID)


@router.put("/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdateIn, db: Annotated[Session, Depends(get_db)]
) -> ProfileOut:
    return service.update_profile(
        db,
        DEFAULT_USER_ID,
        unit_system=payload.unit_system,
        market=payload.market,
        riding_style=payload.riding_style,
        priority_factors=payload.priority_factors,
    )


@router.get("/garage", response_model=list[GarageBikeOut])
def get_garage(db: Annotated[Session, Depends(get_db)]) -> list[GarageBikeOut]:
    return service.list_garage(db, DEFAULT_USER_ID)


@router.post("/garage", response_model=GarageBikeOut)
def add_garage_bike(
    payload: GarageBikeIn, db: Annotated[Session, Depends(get_db)]
) -> GarageBikeOut:
    return service.add_garage_bike(
        db, DEFAULT_USER_ID, payload.motorcycle_id, nickname=payload.nickname
    )


@router.put("/garage/{garage_bike_id}/current", response_model=GarageBikeOut)
def set_current_garage_bike(
    garage_bike_id: int, db: Annotated[Session, Depends(get_db)]
) -> GarageBikeOut:
    return service.set_current_garage_bike(db, DEFAULT_USER_ID, garage_bike_id)


@router.delete("/garage/{garage_bike_id}", status_code=204)
def remove_garage_bike(garage_bike_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    service.remove_garage_bike(db, DEFAULT_USER_ID, garage_bike_id)


@router.get("/dream-bikes", response_model=list[DreamBikeOut])
def get_dream_bikes(db: Annotated[Session, Depends(get_db)]) -> list[DreamBikeOut]:
    return service.list_dream_bikes(db, DEFAULT_USER_ID)


@router.post("/dream-bikes", response_model=DreamBikeOut)
def add_dream_bike(
    payload: DreamBikeIn, db: Annotated[Session, Depends(get_db)]
) -> DreamBikeOut:
    return service.add_dream_bike(
        db, DEFAULT_USER_ID, payload.motorcycle_id, note=payload.note
    )


@router.delete("/dream-bikes/{dream_bike_id}", status_code=204)
def remove_dream_bike(dream_bike_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    service.remove_dream_bike(db, DEFAULT_USER_ID, dream_bike_id)
