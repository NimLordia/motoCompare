from datetime import UTC, date, datetime, timedelta

import pytest

from app.catalog import service as catalog_service
from app.catalog.models import SourceType
from app.db import ensure_utc
from app.research import service
from app.research.models import FailureReason, ResearchTaskState
from app.research.provider import (
    InsightFinding,
    ResearchExecutionError,
    ResearchFindings,
    SpecFinding,
)
from app.research.runner import run_bike_research

OFFICIAL_URL = "https://www.yamaha-motor.eu/gb/en/products/motorcycles/yzf-r7/"
TESTED_URL = "https://www.cycleworld.com/yamaha-yzf-r7-dyno-test/"
FORUM_URL = "https://www.r7forum.com/threads/real-world-top-speed.123/"


@pytest.fixture()
def bike(db, make_bike):
    return make_bike()


def _spec_task(db, bike, key="top_speed"):
    return service.request_research(db, bike.id, "spec", key)


def _insight_task(db, bike, topic="heat"):
    return service.request_research(db, bike.id, "insight", topic)


def test_found_spec_written_with_official_tier(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        spec_findings=(SpecFinding("top_speed", 222.0, "km/h", OFFICIAL_URL),)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found
    assert task.completed_at is not None
    facts = catalog_service.get_specs(db, bike.id, keys=["top_speed"])
    assert len(facts) == 1
    assert facts[0].source_type == SourceType.official
    assert facts[0].value == 222.0
    assert facts[0].source_url == OFFICIAL_URL
    assert task.result_spec_value_id is not None


def test_units_converted_to_canonical(db, bike, fake_provider):
    task = _spec_task(db, bike, "power_peak")
    fake_provider.findings = ResearchFindings(
        spec_findings=(SpecFinding("power_peak", 72.4, "hp", OFFICIAL_URL),)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found
    fact = catalog_service.get_specs(db, bike.id, keys=["power_peak"])[0]
    assert fact.unit == "kW"
    assert fact.value == pytest.approx(53.99, abs=0.01)


def test_official_and_tested_values_coexist(db, bike, fake_provider):
    task = _spec_task(db, bike, "power_peak")
    fake_provider.findings = ResearchFindings(
        spec_findings=(
            SpecFinding("power_peak", 54.0, "kW", OFFICIAL_URL),
            SpecFinding("power_peak", 49.5, "kW", TESTED_URL, "rear-wheel dyno"),
        )
    )

    run_bike_research(db, fake_provider, bike.id)

    facts = catalog_service.get_specs(db, bike.id, keys=["power_peak"])
    assert [fact.source_type for fact in facts] == [SourceType.official, SourceType.tested]
    # The result reference points at the highest-tier value.
    assert task.result_spec_value_id is not None


def test_same_tier_conflict_is_memoized_and_nothing_written(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        spec_findings=(
            SpecFinding("top_speed", 200.0, "km/h", OFFICIAL_URL),
            SpecFinding("top_speed", 260.0, "km/h", "https://www.yamaha-motor.com/us/"),
        )
    )

    now = datetime.now(UTC)
    run_bike_research(db, fake_provider, bike.id, now=now)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.unresolved_conflict
    assert ensure_utc(task.recheck_after) == now + timedelta(days=30)
    assert catalog_service.get_specs(db, bike.id, keys=["top_speed"]) == []


def test_same_tier_agreement_within_tolerance_is_found(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        spec_findings=(
            SpecFinding("top_speed", 220.0, "km/h", OFFICIAL_URL),
            SpecFinding("top_speed", 225.0, "km/h", "https://www.yamaha-motor.com/us/"),
        )
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found
    facts = catalog_service.get_specs(db, bike.id, keys=["top_speed"])
    assert len(facts) == 1


def test_lower_tier_conflict_does_not_block_official_value(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        spec_findings=(
            SpecFinding("top_speed", 222.0, "km/h", OFFICIAL_URL),
            SpecFinding("top_speed", 180.0, "km/h", FORUM_URL),
            SpecFinding("top_speed", 260.0, "km/h", "https://www.reddit.com/r/YamahaR7/"),
        )
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found
    facts = catalog_service.get_specs(db, bike.id, keys=["top_speed"])
    assert [fact.source_type for fact in facts] == [SourceType.official]


def test_no_source_memoized_with_cooldown(db, bike, fake_provider):
    task = _spec_task(db, bike)

    now = datetime.now(UTC)
    run_bike_research(db, fake_provider, bike.id, now=now)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.no_reliable_source
    assert ensure_utc(task.recheck_after) == now + timedelta(days=30)


def test_invalid_source_url_never_counts(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        spec_findings=(SpecFinding("top_speed", 222.0, "km/h", "trust me bro"),)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.no_reliable_source
    assert catalog_service.get_specs(db, bike.id, keys=["top_speed"]) == []


def test_not_applicable_never_retried(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        not_applicable_spec_keys=frozenset({"top_speed"})
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.not_applicable
    assert task.recheck_after is None


def test_unreleased_bike_rechecks_at_release_date(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.findings = ResearchFindings(
        expected_release_date=date(2027, 3, 1)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.not_released_yet
    assert ensure_utc(task.recheck_after) == datetime(2027, 3, 1, tzinfo=UTC)


def test_insight_written_with_sources(db, bike, fake_provider):
    task = _insight_task(db, bike)
    fake_provider.findings = ResearchFindings(
        insight_findings=(
            InsightFinding("heat", "Owners report mild heat in traffic.", (FORUM_URL,)),
        )
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found
    insight = catalog_service.get_insights(db, bike.id, topics=["heat"])[0]
    assert insight.source_type == SourceType.community
    assert insight.source_urls == [FORUM_URL]
    assert task.result_insight_id is not None


def test_insight_with_test_source_is_tested_tier(db, bike, fake_provider):
    _insight_task(db, bike)
    fake_provider.findings = ResearchFindings(
        insight_findings=(
            InsightFinding("heat", "Long-term test found no heat issues.", (TESTED_URL, FORUM_URL)),
        )
    )

    run_bike_research(db, fake_provider, bike.id)

    insight = catalog_service.get_insights(db, bike.id, topics=["heat"])[0]
    assert insight.source_type == SourceType.tested


def test_insight_without_verifiable_source_is_not_stored(db, bike, fake_provider):
    task = _insight_task(db, bike)
    fake_provider.findings = ResearchFindings(
        insight_findings=(InsightFinding("heat", "Sounds plausible.", ()),)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.not_found
    assert task.failure_reason == FailureReason.no_reliable_source
    assert catalog_service.get_insights(db, bike.id, topics=["heat"]) == []


def test_execution_errors_back_off_then_exhaust(db, bike, fake_provider):
    task = _spec_task(db, bike)
    fake_provider.error = ResearchExecutionError("rate limited")
    now = datetime.now(UTC)

    run_bike_research(db, fake_provider, bike.id, now=now)
    assert task.state == ResearchTaskState.queued
    assert task.attempt_count == 1
    assert ensure_utc(task.next_attempt_at) == now + timedelta(minutes=1)

    # Not yet due: nothing runs.
    run_bike_research(db, fake_provider, bike.id, now=now + timedelta(seconds=30))
    assert task.attempt_count == 1

    second = now + timedelta(minutes=2)
    run_bike_research(db, fake_provider, bike.id, now=second)
    assert task.state == ResearchTaskState.queued
    assert task.attempt_count == 2
    assert ensure_utc(task.next_attempt_at) == second + timedelta(minutes=10)

    third = second + timedelta(minutes=11)
    run_bike_research(db, fake_provider, bike.id, now=third)
    assert task.state == ResearchTaskState.failed
    assert task.failure_reason == FailureReason.retries_exhausted
    assert task.attempt_count == 3
    assert ensure_utc(task.recheck_after) == third + timedelta(days=7)

    # Exhausted: no further attempts until the cooldown passes.
    run_bike_research(db, fake_provider, bike.id, now=third + timedelta(minutes=1))
    assert task.attempt_count == 3


def test_batch_makes_a_single_provider_call(db, bike, fake_provider):
    service.populate_bike(db, bike.id)

    run_bike_research(db, fake_provider, bike.id)

    assert len(fake_provider.calls) == 1
    _, spec_keys, topics = fake_provider.calls[0]
    assert "top_speed" in spec_keys
    assert "heat" in topics


def test_stale_searching_task_is_reclaimed(db, bike, fake_provider):
    task = _spec_task(db, bike)
    task.state = ResearchTaskState.searching
    task.attempted_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    fake_provider.findings = ResearchFindings(
        spec_findings=(SpecFinding("top_speed", 222.0, "km/h", OFFICIAL_URL),)
    )

    run_bike_research(db, fake_provider, bike.id)

    assert task.state == ResearchTaskState.found


def test_fresh_searching_task_is_not_rerun(db, bike, fake_provider):
    task = _spec_task(db, bike)
    task.state = ResearchTaskState.searching
    task.attempted_at = datetime.now(UTC)
    db.commit()

    run_bike_research(db, fake_provider, bike.id)

    assert fake_provider.calls == []
    assert task.state == ResearchTaskState.searching
