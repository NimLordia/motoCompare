from sqlalchemy import select

from app.catalog.models import Manufacturer
from app.catalog.registry import MANUFACTURER_OFFICIAL_DOMAINS
from app.catalog.seed import SEED_BIKES, seed_manufacturers


def test_seed_manufacturers_creates_full_roster(db):
    seed_manufacturers(db)
    names = set(db.scalars(select(Manufacturer.name)))
    assert names == set(MANUFACTURER_OFFICIAL_DOMAINS)


def test_seed_manufacturers_is_idempotent(db):
    seed_manufacturers(db)
    seed_manufacturers(db)
    names = list(db.scalars(select(Manufacturer.name)))
    assert len(names) == len(MANUFACTURER_OFFICIAL_DOMAINS)


def test_seed_manufacturers_keeps_existing_rows(db):
    db.add(Manufacturer(name="Yamaha"))
    db.flush()
    yamaha_id = db.scalars(
        select(Manufacturer.id).where(Manufacturer.name == "Yamaha")
    ).one()

    seed_manufacturers(db)

    assert db.scalars(
        select(Manufacturer.id).where(Manufacturer.name == "Yamaha")
    ).one() == yamaha_id


def test_every_seed_bike_manufacturer_is_in_the_roster():
    seed_bike_manufacturers = {seed_bike.manufacturer for seed_bike in SEED_BIKES}
    assert seed_bike_manufacturers <= set(MANUFACTURER_OFFICIAL_DOMAINS)
