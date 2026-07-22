from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import service
from app.catalog.models import Manufacturer, Model, Motorcycle, SpecDefinition
from app.catalog.registry import MANUFACTURER_OFFICIAL_DOMAINS, SPEC_DEFINITIONS
from app.db import SessionLocal

SEED_RETRIEVED_AT = datetime(2026, 7, 21, tzinfo=UTC)


@dataclass(frozen=True)
class SeedSpec:
    key: str
    value: float | str
    unit: str | None
    source_type: str
    source_url: str
    source_note: str = "seed baseline data"


@dataclass(frozen=True)
class SeedInsight:
    topic: str
    summary: str
    source_type: str
    source_urls: list[str]


@dataclass(frozen=True)
class SeedBike:
    manufacturer: str
    model: str
    year: int
    trim: str
    market: str
    specs: list[SeedSpec]
    insights: list[SeedInsight] = field(default_factory=list)


def _official(key: str, value: float | str, unit: str | None, url: str) -> SeedSpec:
    return SeedSpec(key, value, unit, "official", url)


def _tested(key: str, value: float | str, unit: str | None, url: str) -> SeedSpec:
    return SeedSpec(key, value, unit, "tested", url, "seed baseline data (measured)")


_YAMAHA = "https://www.yamaha-motor.eu"
_HONDA = "https://www.honda.co.uk/motorcycles.html"
_KAWASAKI = "https://www.kawasaki.eu"
_BMW = "https://www.bmw-motorrad.com"
_DUCATI = "https://www.ducati.com"
_KTM = "https://www.ktm.com"
_TRIUMPH = "https://www.triumphmotorcycles.co.uk"
_CYCLEWORLD = "https://www.cycleworld.com"

SEED_BIKES: list[SeedBike] = [
    SeedBike(
        "Yamaha", "YZF-R7", 2023, "", "EU",
        specs=[
            _official("engine_type", "Parallel twin (CP2), 270° crank", None, _YAMAHA),
            _official("displacement", 689, "cc", _YAMAHA),
            _official("power_peak", 54.0, "kW", _YAMAHA),
            _tested("power_peak", 49.0, "kW", _CYCLEWORLD),
            _official("torque_peak", 67.0, "Nm", _YAMAHA),
            _official("wet_weight", 188, "kg", _YAMAHA),
            _official("seat_height", 835, "mm", _YAMAHA),
            _official("fuel_capacity", 13.0, "L", _YAMAHA),
            _tested("top_speed", 222, "km/h", _CYCLEWORLD),
            _official("wheelbase", 1395, "mm", _YAMAHA),
            _official("compression_ratio", 11.5, None, _YAMAHA),
        ],
        insights=[
            SeedInsight(
                "comfort",
                "Committed sport ergonomics: clip-ons sit below the top triple clamp and "
                "put real weight on the wrists in town, though owners find the reach "
                "natural at backroad and track pace. The seat is firm; taller riders "
                "report cramped legroom on longer rides.",
                "community",
                ["https://www.reddit.com/r/YamahaR7/"],
            ),
        ],
    ),
    SeedBike(
        "Yamaha", "MT-07", 2023, "", "EU",
        specs=[
            _official("engine_type", "Parallel twin (CP2), 270° crank", None, _YAMAHA),
            _official("displacement", 689, "cc", _YAMAHA),
            _official("power_peak", 54.0, "kW", _YAMAHA),
            _official("torque_peak", 67.0, "Nm", _YAMAHA),
            _official("wet_weight", 184, "kg", _YAMAHA),
            _official("seat_height", 805, "mm", _YAMAHA),
            _official("fuel_capacity", 14.0, "L", _YAMAHA),
            _official("wheelbase", 1400, "mm", _YAMAHA),
        ],
        insights=[
            SeedInsight(
                "heat",
                "Owners consistently report the CP2 engine runs cool even in summer "
                "traffic; radiator heat is barely noticeable on the legs compared with "
                "four-cylinder rivals.",
                "community",
                ["https://www.reddit.com/r/MT07/"],
            ),
        ],
    ),
    SeedBike(
        "Honda", "CB650R", 2023, "", "EU",
        specs=[
            _official("engine_type", "Inline four", None, _HONDA),
            _official("displacement", 649, "cc", _HONDA),
            _official("power_peak", 70.0, "kW", _HONDA),
            _official("torque_peak", 63.0, "Nm", _HONDA),
            _official("wet_weight", 202.5, "kg", _HONDA),
            _official("seat_height", 810, "mm", _HONDA),
            _official("fuel_capacity", 15.4, "L", _HONDA),
        ],
    ),
    SeedBike(
        "Kawasaki", "Ninja ZX-6R", 2024, "", "US",
        specs=[
            _official("engine_type", "Inline four", None, _KAWASAKI),
            _official("displacement", 636, "cc", _KAWASAKI),
            _official("power_peak", 91.4, "kW", _KAWASAKI),
            _official("torque_peak", 69.0, "Nm", _KAWASAKI),
            _official("wet_weight", 198.1, "kg", _KAWASAKI),
            _official("seat_height", 830, "mm", _KAWASAKI),
            _official("fuel_capacity", 17.0, "L", _KAWASAKI),
            _tested("top_speed", 257, "km/h", _CYCLEWORLD),
        ],
    ),
    SeedBike(
        "BMW", "R 1250 GS", 2023, "", "EU",
        specs=[
            _official("engine_type", "Boxer twin (ShiftCam)", None, _BMW),
            _official("displacement", 1254, "cc", _BMW),
            _official("power_peak", 100.0, "kW", _BMW),
            _official("torque_peak", 143.0, "Nm", _BMW),
            _official("wet_weight", 249, "kg", _BMW),
            _official("seat_height", 850, "mm", _BMW),
            _official("fuel_capacity", 20.0, "L", _BMW),
        ],
        insights=[
            SeedInsight(
                "maintenance",
                "Long-distance owners praise the 10,000 km service intervals and "
                "maintenance-free shaft drive; valve checks are straightforward on the "
                "boxer layout and many owners do them at home. Dealer service costs are "
                "the main complaint, not reliability.",
                "community",
                ["https://www.advrider.com/"],
            ),
        ],
    ),
    SeedBike(
        "Ducati", "Panigale V4", 2023, "", "EU",
        specs=[
            _official("engine_type", "V4 (Desmosedici Stradale)", None, _DUCATI),
            _official("displacement", 1103, "cc", _DUCATI),
            _official("power_peak", 158.5, "kW", _DUCATI),
            _official("torque_peak", 123.6, "Nm", _DUCATI),
            _official("wet_weight", 198.5, "kg", _DUCATI),
            _official("seat_height", 850, "mm", _DUCATI),
            _official("fuel_capacity", 16.0, "L", _DUCATI),
            _tested("top_speed", 299, "km/h", _CYCLEWORLD),
        ],
        insights=[
            SeedInsight(
                "heat",
                "Significant heat at low speed is the most-cited ownership drawback: the "
                "rear cylinder bank sits under the seat and owners report hot thighs in "
                "traffic despite the rear-bank deactivation at idle. At speed it is a "
                "non-issue.",
                "community",
                ["https://www.ducati.ms/"],
            ),
        ],
    ),
    SeedBike(
        "Kawasaki", "Z900", 2023, "", "EU",
        specs=[
            _official("engine_type", "Inline four", None, _KAWASAKI),
            _official("displacement", 948, "cc", _KAWASAKI),
            _official("power_peak", 92.2, "kW", _KAWASAKI),
            _official("torque_peak", 98.6, "Nm", _KAWASAKI),
            _official("wet_weight", 212, "kg", _KAWASAKI),
            _official("seat_height", 795, "mm", _KAWASAKI),
            _official("fuel_capacity", 17.0, "L", _KAWASAKI),
        ],
    ),
    # Deliberately incomplete (no wet weight, no top speed): exercises the
    # data_coverage "missing" path in the demo.
    SeedBike(
        "KTM", "390 Duke", 2024, "", "EU",
        specs=[
            _official("engine_type", "Single cylinder", None, _KTM),
            _official("displacement", 398.7, "cc", _KTM),
            _official("power_peak", 33.0, "kW", _KTM),
            _official("torque_peak", 39.0, "Nm", _KTM),
            _official("dry_weight", 165, "kg", _KTM),
            _official("seat_height", 820, "mm", _KTM),
            _official("fuel_capacity", 15.0, "L", _KTM),
        ],
    ),
    SeedBike(
        "Triumph", "Speed Triple 1200", 2023, "RS", "EU",
        specs=[
            _official("engine_type", "Inline triple", None, _TRIUMPH),
            _official("displacement", 1160, "cc", _TRIUMPH),
            _official("power_peak", 132.4, "kW", _TRIUMPH),
            _official("torque_peak", 125.0, "Nm", _TRIUMPH),
            _official("wet_weight", 198, "kg", _TRIUMPH),
            _official("seat_height", 830, "mm", _TRIUMPH),
            _official("fuel_capacity", 15.5, "L", _TRIUMPH),
            _official("wheelbase", 1445, "mm", _TRIUMPH),
            _official("compression_ratio", 13.2, None, _TRIUMPH),
        ],
    ),
    SeedBike(
        "Yamaha", "MT-09", 2023, "SP", "EU",
        specs=[
            _official("engine_type", "Inline triple (CP3)", None, _YAMAHA),
            _official("displacement", 889, "cc", _YAMAHA),
            _official("power_peak", 87.5, "kW", _YAMAHA),
            _official("torque_peak", 93.0, "Nm", _YAMAHA),
            _official("wet_weight", 190, "kg", _YAMAHA),
            _official("seat_height", 825, "mm", _YAMAHA),
            _official("fuel_capacity", 14.0, "L", _YAMAHA),
            _official("wheelbase", 1430, "mm", _YAMAHA),
        ],
    ),
    SeedBike(
        "Honda", "CB500X", 2023, "", "EU",
        specs=[
            _official("engine_type", "Parallel twin", None, _HONDA),
            _official("displacement", 471, "cc", _HONDA),
            _official("power_peak", 35.0, "kW", _HONDA),
            _official("torque_peak", 43.0, "Nm", _HONDA),
            _official("wet_weight", 199, "kg", _HONDA),
            _official("seat_height", 830, "mm", _HONDA),
            _official("fuel_capacity", 17.7, "L", _HONDA),
            _official("wheelbase", 1445, "mm", _HONDA),
        ],
    ),
    SeedBike(
        "Honda", "CRF1000L Africa Twin", 2019, "", "EU",
        specs=[
            _official("engine_type", "Parallel twin, 270° crank", None, _HONDA),
            _official("displacement", 998, "cc", _HONDA),
            _official("power_peak", 70.0, "kW", _HONDA),
            _official("torque_peak", 98.0, "Nm", _HONDA),
            _official("wet_weight", 232, "kg", _HONDA),
            _official("seat_height", 850, "mm", _HONDA),
            _official("fuel_capacity", 18.8, "L", _HONDA),
            _official("wheelbase", 1575, "mm", _HONDA),
            _official("compression_ratio", 10.0, None, _HONDA),
        ],
        insights=[
            SeedInsight(
                "reliability",
                "Long-distance owners regard the CRF1000L as one of the most dependable "
                "big adventure bikes: the under-stressed SOHC twin routinely passes "
                "50,000 km with nothing beyond scheduled maintenance. Early 2016 "
                "examples drew stalling complaints resolved by a dealer ECU update; "
                "later bikes are considered sorted.",
                "community",
                ["https://www.advrider.com/"],
            ),
        ],
    ),
]


def seed_registry(db: Session) -> None:
    for definition_seed in SPEC_DEFINITIONS:
        definition = db.get(SpecDefinition, definition_seed.key)
        if definition is None:
            definition = SpecDefinition(key=definition_seed.key)
            db.add(definition)
        definition.display_name = definition_seed.display_name
        definition.canonical_unit = definition_seed.canonical_unit
        definition.value_type = definition_seed.value_type
        definition.category = definition_seed.category
        definition.is_core = definition_seed.is_core
    db.flush()


def seed_manufacturers(db: Session) -> None:
    existing_names = set(db.scalars(select(Manufacturer.name)))
    for name in MANUFACTURER_OFFICIAL_DOMAINS:
        if name not in existing_names:
            db.add(Manufacturer(name=name))
    db.flush()


def seed_bikes(db: Session) -> None:
    for seed_bike in SEED_BIKES:
        bike = _get_or_create_variant(db, seed_bike)
        for spec in seed_bike.specs:
            service.upsert_spec_value(
                db,
                bike.id,
                spec.key,
                spec.value,
                spec.unit,
                spec.source_type,
                source_url=spec.source_url,
                source_note=spec.source_note,
                retrieved_at=SEED_RETRIEVED_AT,
            )
        for insight in seed_bike.insights:
            service.upsert_insight(
                db,
                bike.id,
                insight.topic,
                insight.summary,
                insight.source_type,
                insight.source_urls,
                retrieved_at=SEED_RETRIEVED_AT,
            )


def _get_or_create_variant(db: Session, seed_bike: SeedBike) -> Motorcycle:
    manufacturer = db.scalars(
        select(Manufacturer).where(Manufacturer.name == seed_bike.manufacturer)
    ).one_or_none()
    if manufacturer is None:
        manufacturer = Manufacturer(name=seed_bike.manufacturer)
        db.add(manufacturer)
        db.flush()
    model = db.scalars(
        select(Model).where(
            Model.manufacturer_id == manufacturer.id, Model.name == seed_bike.model
        )
    ).one_or_none()
    if model is None:
        model = Model(manufacturer_id=manufacturer.id, name=seed_bike.model)
        db.add(model)
        db.flush()
    variant = db.scalars(
        select(Motorcycle).where(
            Motorcycle.model_id == model.id,
            Motorcycle.year == seed_bike.year,
            Motorcycle.trim == seed_bike.trim,
            Motorcycle.market == seed_bike.market,
        )
    ).one_or_none()
    if variant is None:
        variant = Motorcycle(
            model_id=model.id,
            year=seed_bike.year,
            trim=seed_bike.trim,
            market=seed_bike.market,
        )
        db.add(variant)
        db.flush()
    return variant


def run() -> None:
    with SessionLocal() as db:
        seed_registry(db)
        seed_manufacturers(db)
        seed_bikes(db)
        db.commit()
    print(
        f"seeded {len(SPEC_DEFINITIONS)} spec definitions, "
        f"{len(MANUFACTURER_OFFICIAL_DOMAINS)} manufacturers, and {len(SEED_BIKES)} bikes"
    )


if __name__ == "__main__":
    run()
