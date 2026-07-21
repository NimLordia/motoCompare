from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.catalog.models import SourceType


class ManufacturerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    manufacturer_id: int
    name: str


class VariantOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    model_id: int
    year: int
    trim: str
    market: str
    display_name: str


class BikeCandidate(BaseModel):
    bike: VariantOut
    confidence: float


class Fact(BaseModel):
    spec_key: str
    display_name: str
    category: str
    value: float | str
    unit: str
    source_type: SourceType
    source_url: str | None
    source_note: str | None
    retrieved_at: datetime


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic: str
    summary: str
    source_type: SourceType
    source_urls: list[str]
    retrieved_at: datetime


class Coverage(BaseModel):
    bike_id: int
    core_specs_present: list[str]
    core_specs_missing: list[str]
    insight_topics_present: list[str]
    insight_topics_missing: list[str]
    research_pending_specs: list[str]
    research_pending_topics: list[str]
    complete: bool


class ComparisonCell(BaseModel):
    facts: list[Fact]
    missing: bool


class ComparisonRow(BaseModel):
    spec_key: str
    display_name: str
    category: str
    unit: str
    cells: list[ComparisonCell]


class ComparisonMatrix(BaseModel):
    bikes: list[VariantOut]
    rows: list[ComparisonRow]


class BikeDetail(BaseModel):
    bike: VariantOut
    specs: list[Fact]
    insights: list[InsightOut]
    coverage: Coverage
