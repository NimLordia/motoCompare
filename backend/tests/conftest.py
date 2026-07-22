from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.profile.models  # noqa: F401  (registers profile tables for create_all)
from app.catalog.models import Manufacturer, Model, Motorcycle
from app.catalog.seed import seed_registry
from app.db import Base
from app.research.provider import ResearchFindings, SpecRequest


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


class FakeSearchProvider:
    """Scripted SearchProvider: returns `findings`, or raises `error` if set."""

    def __init__(self) -> None:
        self.findings = ResearchFindings()
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    def research(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> ResearchFindings:
        self.calls.append(
            (
                bike_description,
                tuple(request.key for request in spec_requests),
                tuple(insight_topics),
            )
        )
        if self.error is not None:
            raise self.error
        return self.findings


@pytest.fixture()
def fake_provider() -> FakeSearchProvider:
    return FakeSearchProvider()
