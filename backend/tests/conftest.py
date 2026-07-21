from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.models import Manufacturer, Model, Motorcycle
from app.catalog.seed import seed_registry
from app.db import Base


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSession() as session:
        seed_registry(session)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture()
def make_bike(db: Session):
    def _make_bike(
        manufacturer: str = "Yamaha",
        model: str = "YZF-R7",
        year: int = 2023,
        trim: str = "",
        market: str = "EU",
    ) -> Motorcycle:
        manufacturer_row = db.scalars(
            select(Manufacturer).where(Manufacturer.name == manufacturer)
        ).one_or_none()
        if manufacturer_row is None:
            manufacturer_row = Manufacturer(name=manufacturer)
            db.add(manufacturer_row)
            db.flush()
        model_row = db.scalars(
            select(Model).where(
                Model.manufacturer_id == manufacturer_row.id, Model.name == model
            )
        ).one_or_none()
        if model_row is None:
            model_row = Model(manufacturer_id=manufacturer_row.id, name=model)
            db.add(model_row)
            db.flush()
        bike = Motorcycle(model_id=model_row.id, year=year, trim=trim, market=market)
        db.add(bike)
        db.flush()
        return bike

    return _make_bike
