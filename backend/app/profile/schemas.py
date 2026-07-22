from datetime import datetime

from pydantic import BaseModel, Field

from app.catalog.schemas import VariantOut
from app.profile.models import UnitSystemPreference


class ProfileOut(BaseModel):
    user_id: int
    unit_system: UnitSystemPreference
    market: str | None
    riding_style: str | None
    priority_factors: list[str]
    current_bike: VariantOut | None


class ProfileUpdateIn(BaseModel):
    unit_system: UnitSystemPreference
    market: str | None = Field(default=None, max_length=20)
    riding_style: str | None = Field(default=None, max_length=50)
    priority_factors: list[str] = Field(default_factory=list, max_length=10)


class GarageBikeIn(BaseModel):
    motorcycle_id: int
    nickname: str | None = Field(default=None, max_length=50)


class GarageBikeOut(BaseModel):
    id: int
    bike: VariantOut
    nickname: str | None
    is_current: bool
    added_at: datetime


class DreamBikeIn(BaseModel):
    motorcycle_id: int
    note: str | None = Field(default=None, max_length=500)


class DreamBikeOut(BaseModel):
    id: int
    bike: VariantOut
    note: str | None
    added_at: datetime
