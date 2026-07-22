from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import service as catalog_service
from app.catalog.schemas import VariantOut
from app.db import ensure_utc
from app.profile.models import (
    DreamBike,
    GarageBike,
    Profile,
    UnitSystemPreference,
    User,
)
from app.profile.schemas import DreamBikeOut, GarageBikeOut, ProfileOut


class ProfileNotFoundError(LookupError):
    pass


class ProfileValidationError(ValueError):
    pass


def get_profile(db: Session, user_id: int) -> ProfileOut:
    """Preferences plus the current garage bike. A user with nothing stored yet
    gets the defaults — reading never writes."""
    profile = db.get(Profile, user_id)
    current = _current_garage_bike(db, user_id)
    return ProfileOut(
        user_id=user_id,
        unit_system=profile.unit_system if profile else UnitSystemPreference.metric,
        market=profile.market if profile else None,
        riding_style=profile.riding_style if profile else None,
        priority_factors=list(profile.priority_factors) if profile else [],
        current_bike=_variant(db, current.motorcycle_id) if current else None,
    )


def update_profile(
    db: Session,
    user_id: int,
    unit_system: UnitSystemPreference | str,
    market: str | None = None,
    riding_style: str | None = None,
    priority_factors: Sequence[str] = (),
) -> ProfileOut:
    """Full replace of the stored preferences (PUT semantics)."""
    unit_system = _coerce_unit_system(unit_system)
    cleaned_factors = _validate_priority_factors(priority_factors)
    _ensure_user(db, user_id)
    profile = db.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        db.add(profile)
    profile.unit_system = unit_system
    profile.market = _stripped_or_none(market)
    profile.riding_style = _stripped_or_none(riding_style)
    profile.priority_factors = cleaned_factors
    db.commit()
    return get_profile(db, user_id)


def list_garage(db: Session, user_id: int) -> list[GarageBikeOut]:
    rows = db.scalars(
        select(GarageBike)
        .where(GarageBike.user_id == user_id)
        .order_by(
            GarageBike.is_current.desc(), GarageBike.added_at.desc(), GarageBike.id.desc()
        )
    ).all()
    return [_garage_out(db, row) for row in rows]


def add_garage_bike(
    db: Session, user_id: int, motorcycle_id: int, nickname: str | None = None
) -> GarageBikeOut:
    """Upsert on (user, catalog variant): a repeat add refreshes the nickname.
    The first bike in an empty garage becomes the current bike."""
    bike = _variant(db, motorcycle_id)
    _ensure_user(db, user_id)
    row = db.scalars(
        select(GarageBike).where(
            GarageBike.user_id == user_id, GarageBike.motorcycle_id == motorcycle_id
        )
    ).one_or_none()
    if row is None:
        row = GarageBike(
            user_id=user_id,
            motorcycle_id=motorcycle_id,
            is_current=_current_garage_bike(db, user_id) is None,
            added_at=datetime.now(UTC),
        )
        db.add(row)
    row.nickname = _stripped_or_none(nickname)
    db.commit()
    return _garage_out(db, row, bike)


def set_current_garage_bike(db: Session, user_id: int, garage_bike_id: int) -> GarageBikeOut:
    row = _get_garage_bike(db, user_id, garage_bike_id)
    if not row.is_current:
        current = _current_garage_bike(db, user_id)
        if current is not None:
            current.is_current = False
            # Separate flushes keep the one-current-per-user unique index
            # satisfied at every statement.
            db.flush()
        row.is_current = True
    db.commit()
    return _garage_out(db, row)


def remove_garage_bike(db: Session, user_id: int, garage_bike_id: int) -> None:
    """When the current bike leaves the garage, the most recently added
    remaining bike is promoted."""
    row = _get_garage_bike(db, user_id, garage_bike_id)
    was_current = row.is_current
    db.delete(row)
    db.flush()
    if was_current:
        successor = db.scalars(
            select(GarageBike)
            .where(GarageBike.user_id == user_id)
            .order_by(GarageBike.added_at.desc(), GarageBike.id.desc())
        ).first()
        if successor is not None:
            successor.is_current = True
    db.commit()


def list_dream_bikes(db: Session, user_id: int) -> list[DreamBikeOut]:
    rows = db.scalars(
        select(DreamBike)
        .where(DreamBike.user_id == user_id)
        .order_by(DreamBike.added_at.desc(), DreamBike.id.desc())
    ).all()
    return [_dream_out(db, row) for row in rows]


def add_dream_bike(
    db: Session, user_id: int, motorcycle_id: int, note: str | None = None
) -> DreamBikeOut:
    """Upsert on (user, catalog variant): a repeat add refreshes the note."""
    bike = _variant(db, motorcycle_id)
    _ensure_user(db, user_id)
    row = db.scalars(
        select(DreamBike).where(
            DreamBike.user_id == user_id, DreamBike.motorcycle_id == motorcycle_id
        )
    ).one_or_none()
    if row is None:
        row = DreamBike(
            user_id=user_id, motorcycle_id=motorcycle_id, added_at=datetime.now(UTC)
        )
        db.add(row)
    row.note = _stripped_or_none(note)
    db.commit()
    return _dream_out(db, row, bike)


def remove_dream_bike(db: Session, user_id: int, dream_bike_id: int) -> None:
    row = db.get(DreamBike, dream_bike_id)
    if row is None or row.user_id != user_id:
        raise ProfileNotFoundError(f"dream bike {dream_bike_id} not found")
    db.delete(row)
    db.commit()


def _ensure_user(db: Session, user_id: int) -> None:
    if db.get(User, user_id) is None:
        db.add(User(id=user_id))
        db.flush()


def _current_garage_bike(db: Session, user_id: int) -> GarageBike | None:
    return db.scalars(
        select(GarageBike).where(
            GarageBike.user_id == user_id, GarageBike.is_current.is_(True)
        )
    ).one_or_none()


def _get_garage_bike(db: Session, user_id: int, garage_bike_id: int) -> GarageBike:
    row = db.get(GarageBike, garage_bike_id)
    if row is None or row.user_id != user_id:
        raise ProfileNotFoundError(f"garage bike {garage_bike_id} not found")
    return row


def _variant(db: Session, motorcycle_id: int) -> VariantOut:
    # Raises CatalogNotFoundError (mapped to 404) for a dangling motorcycle_id,
    # so bikes always enter the personal area as valid catalog FKs.
    return catalog_service.get_variant(db, motorcycle_id)


def _garage_out(db: Session, row: GarageBike, bike: VariantOut | None = None) -> GarageBikeOut:
    return GarageBikeOut(
        id=row.id,
        bike=bike or _variant(db, row.motorcycle_id),
        nickname=row.nickname,
        is_current=row.is_current,
        added_at=ensure_utc(row.added_at),
    )


def _dream_out(db: Session, row: DreamBike, bike: VariantOut | None = None) -> DreamBikeOut:
    return DreamBikeOut(
        id=row.id,
        bike=bike or _variant(db, row.motorcycle_id),
        note=row.note,
        added_at=ensure_utc(row.added_at),
    )


def _coerce_unit_system(unit_system: UnitSystemPreference | str) -> UnitSystemPreference:
    try:
        return UnitSystemPreference(unit_system)
    except ValueError as error:
        raise ProfileValidationError(f"unknown unit system {unit_system!r}") from error


def _validate_priority_factors(priority_factors: Sequence[str]) -> list[str]:
    cleaned = [factor.strip() for factor in priority_factors]
    if any(not factor for factor in cleaned):
        raise ProfileValidationError("priority factors must be non-empty strings")
    lowered = [factor.lower() for factor in cleaned]
    if len(set(lowered)) != len(lowered):
        raise ProfileValidationError("priority factors must not repeat")
    return cleaned


def _stripped_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
