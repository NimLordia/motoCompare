import pytest

from app.catalog import service
from app.catalog.models import SourceType, SpecValue


def test_all_tiers_returned_in_priority_order(db, make_bike):
    bike = make_bike()
    for source_type, kilowatts in [
        ("community", 50.0),
        ("official", 54.0),
        ("estimated", 52.0),
        ("tested", 49.0),
    ]:
        service.upsert_spec_value(db, bike.id, "power_peak", kilowatts, "kW", source_type)

    facts = service.get_specs(db, bike.id, keys=["power_peak"])

    assert [fact.source_type for fact in facts] == [
        SourceType.official,
        SourceType.tested,
        SourceType.community,
        SourceType.estimated,
    ]
    assert [fact.value for fact in facts] == [54.0, 49.0, 50.0, 52.0]


def test_upsert_updates_existing_tier_instead_of_duplicating(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "official")
    service.upsert_spec_value(db, bike.id, "power_peak", 55.0, "kW", "official")

    rows = db.query(SpecValue).filter_by(motorcycle_id=bike.id, spec_key="power_peak").all()
    assert len(rows) == 1
    assert rows[0].value_num == 55.0


def test_upsert_converts_input_units_to_canonical(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "power_peak", 72.42, "hp", "official")

    row = db.query(SpecValue).filter_by(motorcycle_id=bike.id, spec_key="power_peak").one()
    assert row.value_num == pytest.approx(54.0, abs=0.01)


def test_get_specs_converts_to_imperial(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "official")

    (fact,) = service.get_specs(db, bike.id, keys=["power_peak"], unit_system="imperial")
    assert fact.unit == "hp"
    assert fact.value == pytest.approx(72.42, abs=0.01)


def test_text_spec_roundtrip_and_unit_rejection(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "engine_type", "Parallel twin", None, "official")

    (fact,) = service.get_specs(db, bike.id, keys=["engine_type"])
    assert fact.value == "Parallel twin"
    assert fact.unit == ""

    with pytest.raises(service.CatalogValidationError, match="does not take a unit"):
        service.upsert_spec_value(db, bike.id, "engine_type", "Inline four", "kW", "official")


def test_upsert_validation_errors(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.CatalogValidationError, match="not in the registry"):
        service.upsert_spec_value(db, bike.id, "flux_capacitance", 1.21, "kW", "official")
    with pytest.raises(service.CatalogValidationError, match="expects a numeric value"):
        service.upsert_spec_value(db, bike.id, "power_peak", "fifty-four", "kW", "official")
    with pytest.raises(service.CatalogValidationError, match="unknown source type"):
        service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "hearsay")
    with pytest.raises(service.CatalogValidationError, match="no known conversion"):
        service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "mm", "official")


def test_insight_upsert_validation(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.CatalogValidationError, match="unknown insight topic"):
        service.upsert_insight(db, bike.id, "vibes", "great", "community", ["https://x.example"])
    with pytest.raises(service.CatalogValidationError, match="community or tested"):
        service.upsert_insight(db, bike.id, "heat", "runs hot", "official", ["https://x.example"])
    with pytest.raises(service.CatalogValidationError, match="at least one source URL"):
        service.upsert_insight(db, bike.id, "heat", "runs hot", "community", [])


def test_compare_aligns_facts_and_marks_missing(db, make_bike):
    bike_one = make_bike(model="YZF-R7")
    bike_two = make_bike(model="MT-07")
    service.upsert_spec_value(db, bike_one.id, "power_peak", 54.0, "kW", "official")
    service.upsert_spec_value(db, bike_one.id, "torque_peak", 67.0, "Nm", "official")
    service.upsert_spec_value(db, bike_two.id, "power_peak", 55.0, "kW", "official")
    service.upsert_spec_value(db, bike_two.id, "power_peak", 51.0, "kW", "tested")

    matrix = service.compare(db, [bike_one.id, bike_two.id])

    assert [row.spec_key for row in matrix.rows] == ["power_peak", "torque_peak"]
    power_row = matrix.rows[0]
    assert [fact.source_type for fact in power_row.cells[1].facts] == [
        SourceType.official,
        SourceType.tested,
    ]
    torque_row = matrix.rows[1]
    assert torque_row.cells[0].missing is False
    assert torque_row.cells[1].missing is True
    assert torque_row.cells[1].facts == []


def test_compare_requires_two_distinct_bikes(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.CatalogValidationError, match="at least two"):
        service.compare(db, [bike.id])
    with pytest.raises(service.CatalogValidationError, match="distinct"):
        service.compare(db, [bike.id, bike.id])
