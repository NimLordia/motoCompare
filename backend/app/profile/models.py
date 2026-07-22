from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.catalog.models import PortableJSON
from app.db import Base

# V1 runs without auth: exactly one user row, created lazily on the first
# profile write. Every user-scoped table still carries user_id so multi-user
# later is a migration, not a rewrite.
DEFAULT_USER_ID = 1


class UnitSystemPreference(StrEnum):
    metric = "metric"
    imperial = "imperial"
    # Metric everywhere except power in hp — the motorcycle-press convention.
    mixed = "mixed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    unit_system: Mapped[UnitSystemPreference] = mapped_column(
        Enum(UnitSystemPreference, native_enum=False, length=10),
        default=UnitSystemPreference.metric,
        server_default="metric",
    )
    market: Mapped[str | None] = mapped_column(String(20))
    riding_style: Mapped[str | None] = mapped_column(String(50))
    priority_factors: Mapped[list[str]] = mapped_column(PortableJSON, default=list)


class GarageBike(Base):
    __tablename__ = "garage_bikes"
    # One row per catalog variant per garage: a repeat add is an upsert, and
    # the partial index makes "exactly one current bike per user" a database
    # invariant on both PostgreSQL and SQLite.
    __table_args__ = (
        UniqueConstraint("user_id", "motorcycle_id"),
        Index(
            "uq_garage_bikes_one_current_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_current"),
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    motorcycle_id: Mapped[int] = mapped_column(
        ForeignKey("motorcycles.id", ondelete="CASCADE")
    )
    is_current: Mapped[bool] = mapped_column(default=False, server_default="false")
    nickname: Mapped[str | None] = mapped_column(String(50))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DreamBike(Base):
    __tablename__ = "dream_bikes"
    __table_args__ = (UniqueConstraint("user_id", "motorcycle_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    motorcycle_id: Mapped[int] = mapped_column(
        ForeignKey("motorcycles.id", ondelete="CASCADE")
    )
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
