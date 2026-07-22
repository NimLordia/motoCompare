from datetime import UTC, datetime, timedelta

import pytest

from app.catalog import service as catalog_service
from app.catalog.registry import CORE_SPEC_KEYS, INSIGHT_TOPICS
from app.research import service
from app.research.models import FailureReason, ResearchKind, ResearchTaskState


def test_request_research_creates_queued_task(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")

    assert task.state == ResearchTaskState.queued
    assert task.kind == ResearchKind.spec
    assert task.fact_key == "top_speed"
    assert task.attempt_count == 0


def test_request_research_is_idempotent(db, make_bike):
    bike = make_bike()
    first = service.request_research(db, bike.id, "spec", "top_speed")
    second = service.request_research(db, bike.id, "spec", "top_speed")

    assert first.id == second.id
    assert len(service.get_tasks_for_bike(db, bike.id)) == 1


def test_same_fact_key_is_distinct_per_kind(db, make_bike):
    bike = make_bike()
    spec_task = service.request_research(db, bike.id, "spec", "top_speed")
    insight_task = service.request_research(db, bike.id, "insight", "heat")

    assert spec_task.id != insight_task.id


def test_request_research_unknown_bike_raises(db):
    with pytest.raises(service.ResearchNotFoundError):
        service.request_research(db, 424242, "spec", "top_speed")


def test_request_research_unknown_spec_key_raises(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.ResearchValidationError):
        service.request_research(db, bike.id, "spec", "flux_capacitance")


def test_request_research_unknown_topic_raises(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.ResearchValidationError):
        service.request_research(db, bike.id, "insight", "vibes")


def test_request_research_unknown_kind_raises(db, make_bike):
    bike = make_bike()
    with pytest.raises(service.ResearchValidationError):
        service.request_research(db, bike.id, "rumor", "top_speed")


def test_memoized_failure_returned_before_recheck(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")
    task.state = ResearchTaskState.not_found
    task.failure_reason = FailureReason.no_reliable_source
    task.recheck_after = datetime.now(UTC) + timedelta(days=10)
    db.flush()

    again = service.request_research(db, bike.id, "spec", "top_speed")

    assert again.id == task.id
    assert again.state == ResearchTaskState.not_found
    assert again.failure_reason == FailureReason.no_reliable_source


def test_memoized_failure_requeued_after_recheck(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")
    task.state = ResearchTaskState.not_found
    task.failure_reason = FailureReason.no_reliable_source
    task.recheck_after = datetime.now(UTC) - timedelta(minutes=1)
    task.attempt_count = 3
    db.flush()

    again = service.request_research(db, bike.id, "spec", "top_speed")

    assert again.id == task.id
    assert again.state == ResearchTaskState.queued
    assert again.failure_reason is None
    assert again.recheck_after is None
    assert again.attempt_count == 0


def test_not_applicable_is_never_requeued(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")
    task.state = ResearchTaskState.not_found
    task.failure_reason = FailureReason.not_applicable
    task.recheck_after = None
    db.flush()

    again = service.request_research(db, bike.id, "spec", "top_speed")

    assert again.state == ResearchTaskState.not_found
    assert again.failure_reason == FailureReason.not_applicable


def test_populate_bike_covers_every_missing_core_fact(db, make_bike):
    bike = make_bike()
    tasks = service.populate_bike(db, bike.id)

    spec_keys = {task.fact_key for task in tasks if task.kind == ResearchKind.spec}
    topics = {task.fact_key for task in tasks if task.kind == ResearchKind.insight}
    assert spec_keys == set(CORE_SPEC_KEYS)
    assert topics == set(INSIGHT_TOPICS)


def test_populate_bike_skips_present_facts(db, make_bike):
    bike = make_bike()
    catalog_service.upsert_spec_value(db, bike.id, "power_peak", 54.0, "kW", "official")
    catalog_service.upsert_insight(
        db, bike.id, "heat", "runs cool", "community", ["https://example.com"]
    )

    tasks = service.populate_bike(db, bike.id)

    fact_keys = {(task.kind, task.fact_key) for task in tasks}
    assert (ResearchKind.spec, "power_peak") not in fact_keys
    assert (ResearchKind.insight, "heat") not in fact_keys
    assert (ResearchKind.spec, "top_speed") in fact_keys


def test_populate_bike_is_idempotent(db, make_bike):
    bike = make_bike()
    first = service.populate_bike(db, bike.id)
    second = service.populate_bike(db, bike.id)

    assert {task.id for task in first} == {task.id for task in second}


def test_pending_research_feeds_coverage(db, make_bike):
    bike = make_bike()
    service.populate_bike(db, bike.id)
    catalog_service.register_pending_research_provider(service.pending_research_for_bike)
    try:
        coverage = catalog_service.data_coverage(db, bike.id)
    finally:
        catalog_service.register_pending_research_provider(
            catalog_service._no_pending_research
        )

    assert coverage.research_pending_specs == sorted(CORE_SPEC_KEYS)
    assert coverage.research_pending_topics == sorted(INSIGHT_TOPICS)


class RecordingDispatcher:
    def __init__(self):
        self.submitted: list[int] = []

    def submit_bike(self, bike_id: int) -> None:
        self.submitted.append(bike_id)

    def wait_for_bike(self, bike_id: int, timeout: float) -> bool:
        return True


def test_request_research_dispatches_eligible_tasks(db, make_bike):
    bike = make_bike()
    dispatcher = RecordingDispatcher()
    service.configure_dispatcher(dispatcher)
    try:
        service.request_research(db, bike.id, "spec", "top_speed")
    finally:
        service.configure_dispatcher(None)

    assert dispatcher.submitted == [bike.id]


def test_memoized_failure_is_not_redispatched(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")
    task.state = ResearchTaskState.not_found
    task.failure_reason = FailureReason.not_applicable
    db.commit()

    dispatcher = RecordingDispatcher()
    service.configure_dispatcher(dispatcher)
    try:
        service.request_research(db, bike.id, "spec", "top_speed")
        service.get_tasks_for_bike(db, bike.id)
    finally:
        service.configure_dispatcher(None)

    assert dispatcher.submitted == []


def test_polling_redispatches_due_retries(db, make_bike):
    bike = make_bike()
    task = service.request_research(db, bike.id, "spec", "top_speed")
    task.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    dispatcher = RecordingDispatcher()
    service.configure_dispatcher(dispatcher)
    try:
        service.get_tasks_for_bike(db, bike.id)
    finally:
        service.configure_dispatcher(None)

    assert dispatcher.submitted == [bike.id]


def test_wait_for_research_without_dispatcher_returns_true(db):
    assert service.wait_for_research(1, timeout=0.01) is True


def test_get_task_unknown_id_raises(db):
    with pytest.raises(service.ResearchNotFoundError):
        service.get_task(db, 424242)
