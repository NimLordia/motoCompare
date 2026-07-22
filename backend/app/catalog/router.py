from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.catalog import service
from app.catalog.schemas import (
    BikeCandidate,
    BikeDetail,
    ComparisonMatrix,
    Coverage,
    Fact,
    InsightOut,
    ManufacturerOut,
    ModelOut,
    VariantOut,
)
from app.db import get_db

router = APIRouter()

UnitSystemParam = Annotated[Literal["metric", "imperial", "mixed"], Query()]


def _split_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or None


@router.get("/manufacturers", response_model=list[ManufacturerOut])
def get_manufacturers(db: Annotated[Session, Depends(get_db)]) -> list[ManufacturerOut]:
    return service.list_manufacturers(db)


@router.get("/manufacturers/{manufacturer_id}/models", response_model=list[ModelOut])
def get_models(
    manufacturer_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[ModelOut]:
    return service.list_models(db, manufacturer_id)


@router.get("/models/{model_id}/variants", response_model=list[VariantOut])
def get_variants(model_id: int, db: Annotated[Session, Depends(get_db)]) -> list[VariantOut]:
    return service.list_variants(db, model_id)


# Declared before /bikes/{bike_id} so "resolve" is not parsed as a bike id.
@router.get("/bikes/resolve", response_model=list[BikeCandidate])
def resolve_bike(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=100)],
    market: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[BikeCandidate]:
    return service.resolve_bike(db, q, market=market, limit=limit)


@router.get("/bikes/compare", response_model=ComparisonMatrix)
def compare_bikes(
    db: Annotated[Session, Depends(get_db)],
    ids: Annotated[list[int], Query(min_length=2, max_length=6)],
    keys: Annotated[str | None, Query()] = None,
    unit_system: UnitSystemParam = "metric",
) -> ComparisonMatrix:
    return service.compare(db, ids, keys=_split_csv(keys), unit_system=unit_system)


@router.get("/bikes/{bike_id}", response_model=BikeDetail)
def get_bike_detail(
    bike_id: int,
    db: Annotated[Session, Depends(get_db)],
    unit_system: UnitSystemParam = "metric",
) -> BikeDetail:
    return service.get_bike_detail(db, bike_id, unit_system=unit_system)


@router.get("/bikes/{bike_id}/specs", response_model=list[Fact])
def get_bike_specs(
    bike_id: int,
    db: Annotated[Session, Depends(get_db)],
    keys: Annotated[str | None, Query()] = None,
    unit_system: UnitSystemParam = "metric",
) -> list[Fact]:
    return service.get_specs(db, bike_id, keys=_split_csv(keys), unit_system=unit_system)


@router.get("/bikes/{bike_id}/insights", response_model=list[InsightOut])
def get_bike_insights(
    bike_id: int,
    db: Annotated[Session, Depends(get_db)],
    topics: Annotated[str | None, Query()] = None,
) -> list[InsightOut]:
    return service.get_insights(db, bike_id, topics=_split_csv(topics))


@router.get("/bikes/{bike_id}/coverage", response_model=Coverage)
def get_bike_coverage(bike_id: int, db: Annotated[Session, Depends(get_db)]) -> Coverage:
    return service.data_coverage(db, bike_id)
