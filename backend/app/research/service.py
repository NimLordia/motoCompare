from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog import service as catalog_service
from app.catalog.models import Motorcycle, SpecDefinition
from app.catalog.registry import INSIGHT_TOPICS
from app.db import ensure_utc
from app.research import runner
from app.research.models import ResearchKind, ResearchTask, ResearchTaskState


class ResearchNotFoundError(LookupError):
    pass


class ResearchValidationError(ValueError):
    pass


class ResearchDispatcher(Protocol):
    def submit_bike(self, bike_id: int) -> None: ...

    def wait_for_bike(self, bike_id: int, timeout: float) -> bool: ...


# Configured at app startup (BackgroundResearchExecutor in production); left unset
# in tests so nothing runs in the background.
_dispatcher: ResearchDispatcher | None = None


def configure_dispatcher(dispatcher: ResearchDispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def request_research(
    db: Session, bike_id: int, kind: ResearchKind | str, fact_key: str
) -> ResearchTask:
    """Idempotent: returns the existing task (or its memoized failure) unless the
    failure's recheck_after has passed, in which case the task is re-queued."""
    kind = _coerce_kind(kind)
    _validate_bike(db, bike_id)
    _validate_fact_key(db, kind, fact_key)
    now = datetime.now(UTC)
    task = _get_or_create_task(db, bike_id, kind, fact_key, now)
    # The dispatcher's worker threads read through their own sessions, so the task
    # must be committed before dispatch.
    db.commit()
    if runner.is_eligible(task, now):
        _dispatch(bike_id)
    return task


def populate_bike(db: Session, bike_id: int) -> list[ResearchTask]:
    """Fan out one task per missing core spec and insight topic, each individually
    deduplicated, and dispatch them as a single batched research run."""
    coverage = catalog_service.data_coverage(db, bike_id)
    now = datetime.now(UTC)
    tasks = [
        _get_or_create_task(db, bike_id, ResearchKind.spec, key, now)
        for key in coverage.core_specs_missing
    ]
    tasks += [
        _get_or_create_task(db, bike_id, ResearchKind.insight, topic, now)
        for topic in coverage.insight_topics_missing
    ]
    db.commit()
    if any(runner.is_eligible(task, now) for task in tasks):
        _dispatch(bike_id)
    return tasks


def get_task(db: Session, task_id: int) -> ResearchTask:
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise ResearchNotFoundError(f"research task {task_id} not found")
    return task


def get_tasks_for_bike(db: Session, bike_id: int) -> list[ResearchTask]:
    _validate_bike(db, bike_id)
    tasks = list(
        db.scalars(
            select(ResearchTask)
            .where(ResearchTask.motorcycle_id == bike_id)
            .order_by(ResearchTask.id)
        )
    )
    # Polling doubles as the retry pump: due retries and stale `searching` tasks
    # are re-dispatched here, so no scheduler is needed.
    now = datetime.now(UTC)
    if any(runner.is_eligible(task, now) for task in tasks):
        _dispatch(bike_id)
    return tasks


def pending_research_for_bike(db: Session, bike_id: int) -> tuple[set[str], set[str]]:
    """Catalog's pending-research provider hook: in-flight spec keys and topics."""
    tasks = db.scalars(
        select(ResearchTask).where(
            ResearchTask.motorcycle_id == bike_id,
            ResearchTask.state.in_(
                [ResearchTaskState.queued, ResearchTaskState.searching]
            ),
        )
    )
    pending_specs: set[str] = set()
    pending_topics: set[str] = set()
    for task in tasks:
        if task.kind == ResearchKind.spec:
            pending_specs.add(task.fact_key)
        else:
            pending_topics.add(task.fact_key)
    return pending_specs, pending_topics


def wait_for_research(bike_id: int, timeout: float) -> bool:
    """Chat's inline-await hook: block up to `timeout` seconds for the bike's
    in-flight research to settle; False means it continues in the background."""
    if _dispatcher is None:
        return True
    return _dispatcher.wait_for_bike(bike_id, timeout)


def _dispatch(bike_id: int) -> None:
    if _dispatcher is not None:
        _dispatcher.submit_bike(bike_id)


def _get_or_create_task(
    db: Session, bike_id: int, kind: ResearchKind, fact_key: str, now: datetime
) -> ResearchTask:
    task = _find_task(db, bike_id, kind, fact_key)
    if task is None:
        task = ResearchTask(motorcycle_id=bike_id, kind=kind, fact_key=fact_key)
        try:
            with db.begin_nested():
                db.add(task)
                db.flush()
        except IntegrityError:
            # A concurrent request won the unique-constraint race; theirs is ours.
            task = _find_task(db, bike_id, kind, fact_key)
            if task is None:  # pragma: no cover - only under concurrent deletes
                raise
        return task
    if task.state in (ResearchTaskState.not_found, ResearchTaskState.failed):
        recheck_after = ensure_utc(task.recheck_after)
        if recheck_after is not None and recheck_after <= now:
            _requeue(task)
            db.flush()
    return task


def _find_task(
    db: Session, bike_id: int, kind: ResearchKind, fact_key: str
) -> ResearchTask | None:
    return db.scalars(
        select(ResearchTask).where(
            ResearchTask.motorcycle_id == bike_id,
            ResearchTask.kind == kind,
            ResearchTask.fact_key == fact_key,
        )
    ).one_or_none()


def _requeue(task: ResearchTask) -> None:
    task.state = ResearchTaskState.queued
    task.failure_reason = None
    task.recheck_after = None
    task.attempt_count = 0
    task.next_attempt_at = None
    task.attempted_at = None
    task.completed_at = None


def _coerce_kind(kind: ResearchKind | str) -> ResearchKind:
    try:
        return ResearchKind(kind)
    except ValueError as error:
        raise ResearchValidationError(f"unknown research kind {kind!r}") from error


def _validate_bike(db: Session, bike_id: int) -> None:
    if db.get(Motorcycle, bike_id) is None:
        raise ResearchNotFoundError(f"bike {bike_id} not found")


def _validate_fact_key(db: Session, kind: ResearchKind, fact_key: str) -> None:
    if kind == ResearchKind.spec:
        if db.get(SpecDefinition, fact_key) is None:
            raise ResearchValidationError(f"spec key {fact_key!r} is not in the registry")
    elif fact_key not in INSIGHT_TOPICS:
        raise ResearchValidationError(f"unknown insight topic {fact_key!r}")
