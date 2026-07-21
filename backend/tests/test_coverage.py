import pytest

from app.catalog import service
from app.catalog.registry import CORE_SPEC_KEYS, INSIGHT_TOPICS


def _fill_core_specs(db, bike_id: int) -> None:
    for key in CORE_SPEC_KEYS:
        if key == "engine_type":
            service.upsert_spec_value(db, bike_id, key, "Parallel twin", None, "official")
        else:
            service.upsert_spec_value(db, bike_id, key, 100.0, None, "official")


def _fill_insights(db, bike_id: int) -> None:
    for topic in INSIGHT_TOPICS:
        service.upsert_insight(
            db, bike_id, topic, f"summary for {topic}", "community", ["https://example.com"]
        )


def test_empty_bike_has_everything_missing(db, make_bike):
    bike = make_bike()
    coverage = service.data_coverage(db, bike.id)

    assert coverage.core_specs_present == []
    assert coverage.core_specs_missing == list(CORE_SPEC_KEYS)
    assert coverage.insight_topics_present == []
    assert coverage.insight_topics_missing == list(INSIGHT_TOPICS)
    assert coverage.complete is False


def test_partial_coverage_reports_exact_gaps(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "official")
    service.upsert_spec_value(db, bike.id, "wet_weight", 188.0, "kg", "official")
    service.upsert_insight(db, bike.id, "heat", "runs cool", "community", ["https://example.com"])

    coverage = service.data_coverage(db, bike.id)

    assert coverage.core_specs_present == ["power_peak", "wet_weight"]
    assert "seat_height" in coverage.core_specs_missing
    assert coverage.insight_topics_present == ["heat"]
    assert "comfort" in coverage.insight_topics_missing
    assert coverage.complete is False


def test_multiple_tiers_of_same_spec_count_once(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "official")
    service.upsert_spec_value(db, bike.id, "power_peak", 49.0, "kW", "tested")

    coverage = service.data_coverage(db, bike.id)
    assert coverage.core_specs_present == ["power_peak"]


def test_non_core_specs_do_not_affect_coverage(db, make_bike):
    bike = make_bike()
    service.upsert_spec_value(db, bike.id, "wheelbase", 1395.0, "mm", "official")

    coverage = service.data_coverage(db, bike.id)
    assert coverage.core_specs_present == []


def test_complete_bike(db, make_bike):
    bike = make_bike()
    _fill_core_specs(db, bike.id)
    _fill_insights(db, bike.id)

    coverage = service.data_coverage(db, bike.id)
    assert coverage.core_specs_missing == []
    assert coverage.insight_topics_missing == []
    assert coverage.complete is True


def test_pending_research_is_reported(db, make_bike):
    bike = make_bike()
    service.register_pending_research_provider(
        lambda session, bike_id: ({"top_speed"}, {"heat"})
    )
    try:
        coverage = service.data_coverage(db, bike.id)
        assert coverage.research_pending_specs == ["top_speed"]
        assert coverage.research_pending_topics == ["heat"]
    finally:
        service.register_pending_research_provider(service._no_pending_research)


def test_unknown_bike_raises(db):
    with pytest.raises(service.CatalogNotFoundError):
        service.data_coverage(db, 424242)
