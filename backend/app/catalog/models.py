from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


class SourceType(StrEnum):
    official = "official"
    tested = "tested"
    community = "community"
    estimated = "estimated"


# Display/resolution priority: lower number wins (official > tested > community > estimated).
SOURCE_TIER_PRIORITY: dict[SourceType, int] = {
    SourceType.official: 0,
    SourceType.tested: 1,
    SourceType.community: 2,
    SourceType.estimated: 3,
}


class ValueType(StrEnum):
    number = "number"
    text = "text"


# JSON on SQLite (tests), JSONB on PostgreSQL.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    models: Mapped[list["Model"]] = relationship(back_populates="manufacturer")


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("manufacturer_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    name: Mapped[str] = mapped_column(String(100))

    manufacturer: Mapped[Manufacturer] = relationship(back_populates="models")
    variants: Mapped[list["Motorcycle"]] = relationship(back_populates="model")


class Motorcycle(Base):
    __tablename__ = "motorcycles"
    # trim and market are non-null with "" meaning base trim / unspecified market,
    # so the uniqueness constraint actually deduplicates (NULLs never collide).
    __table_args__ = (UniqueConstraint("model_id", "year", "trim", "market"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    year: Mapped[int]
    trim: Mapped[str] = mapped_column(String(50), default="", server_default="")
    market: Mapped[str] = mapped_column(String(20), default="", server_default="")

    model: Mapped[Model] = relationship(back_populates="variants")
    spec_values: Mapped[list["SpecValue"]] = relationship(
        back_populates="motorcycle", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="motorcycle", cascade="all, delete-orphan"
    )


class SpecDefinition(Base):
    __tablename__ = "spec_definitions"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    # "" for text specs and dimensionless numbers (e.g. compression ratio).
    canonical_unit: Mapped[str] = mapped_column(String(20))
    value_type: Mapped[ValueType] = mapped_column(Enum(ValueType, native_enum=False, length=10))
    category: Mapped[str] = mapped_column(String(30))
    is_core: Mapped[bool] = mapped_column(default=False, server_default="false")


class SpecValue(Base):
    __tablename__ = "spec_values"
    __table_args__ = (UniqueConstraint("motorcycle_id", "spec_key", "source_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    motorcycle_id: Mapped[int] = mapped_column(
        ForeignKey("motorcycles.id", ondelete="CASCADE")
    )
    spec_key: Mapped[str] = mapped_column(ForeignKey("spec_definitions.key"))
    value_num: Mapped[float | None]
    value_text: Mapped[str | None] = mapped_column(String(200))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=10)
    )
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_note: Mapped[str | None] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    motorcycle: Mapped[Motorcycle] = relationship(back_populates="spec_values")
    definition: Mapped[SpecDefinition] = relationship()


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (UniqueConstraint("motorcycle_id", "topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    motorcycle_id: Mapped[int] = mapped_column(
        ForeignKey("motorcycles.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=10)
    )
    source_urls: Mapped[list[str]] = mapped_column(PortableJSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    motorcycle: Mapped[Motorcycle] = relationship(back_populates="insights")
