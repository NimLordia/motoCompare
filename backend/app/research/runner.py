import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import service as catalog_service
from app.catalog import units
from app.catalog.models import SOURCE_TIER_PRIORITY, SourceType, SpecDefinition, ValueType
from app.research import tiering
from app.research.models import (
    EXECUTION_BACKOFF,
    FAILURE_COOLDOWNS,
    FailureReason,
    ResearchKind,
    ResearchTask,
    ResearchTaskState,
    ensure_utc,
)
from app.research.provider import (
    InsightFinding,
    ResearchExecutionError,
    ResearchFindings,
    SearchProvider,
    SpecFinding,
    SpecRequest,
)

logger = logging.getLogger(__name__)

# A crashed run leaves tasks stuck in `searching`; after this they are eligible again.
SEARCHING_STALE_AFTER = timedelta(minutes=10)


def is_eligible(task: ResearchTask, now: datetime) -> bool:
    if task.state == ResearchTaskState.queued:
        next_attempt_at = ensure_utc(task.next_attempt_at)
        return next_attempt_at is None or next_attempt_at <= now
    if task.state == ResearchTaskState.searching:
        attempted_at = ensure_utc(task.attempted_at)
        return attempted_at is None or attempted_at <= now - SEARCHING_STALE_AFTER
    return False


def run_bike_research(
    db: Session,
    provider: SearchProvider,
    bike_id: int,
    *,
    max_attempts: int = 3,
    conflict_tolerance: float = 0.15,
    now: datetime | None = None,
) -> list[ResearchTask]:
    """Execute every eligible research task for one bike in a single provider pass.

    Batching is the page-level extraction contract: one search run is mined for
    all missing facts, so populating a bike costs a few searches, not one per fact.
    """
    now = now or datetime.now(UTC)
    tasks = [task for task in _tasks_for_bike(db, bike_id) if is_eligible(task, now)]
    if not tasks:
        return []
    for task in tasks:
        task.state = ResearchTaskState.searching
        task.attempted_at = now
        task.attempt_count += 1
    # Publish `searching` before the slow provider call so coverage shows the
    # research as in-flight while it runs.
    db.commit()

    bike_name = catalog_service.get_bike_detail(db, bike_id).bike.display_name
    spec_tasks = [task for task in tasks if task.kind == ResearchKind.spec]
    insight_tasks = [task for task in tasks if task.kind == ResearchKind.insight]
    definitions = _definitions_for(db, [task.fact_key for task in spec_tasks])
    spec_requests = [
        SpecRequest(
            key=definition.key,
            display_name=definition.display_name,
            canonical_unit=definition.canonical_unit,
            value_type=definition.value_type.value,
        )
        for task in spec_tasks
        if (definition := definitions.get(task.fact_key)) is not None
    ]
    insight_topics = [task.fact_key for task in insight_tasks]

    try:
        findings = provider.research(bike_name, spec_requests, insight_topics)
    except ResearchExecutionError as error:
        logger.warning("research execution failed for bike %s: %s", bike_id, error)
        for task in tasks:
            _record_execution_failure(task, now, max_attempts)
        db.commit()
        return tasks

    for task in spec_tasks:
        _resolve_spec_task(
            db, task, definitions.get(task.fact_key), findings, now, conflict_tolerance
        )
    for task in insight_tasks:
        _resolve_insight_task(db, task, findings, now)
    db.commit()
    return tasks


def _tasks_for_bike(db: Session, bike_id: int) -> list[ResearchTask]:
    return list(
        db.scalars(select(ResearchTask).where(ResearchTask.motorcycle_id == bike_id))
    )


def _definitions_for(db: Session, keys: list[str]) -> dict[str, SpecDefinition]:
    if not keys:
        return {}
    definitions = db.scalars(select(SpecDefinition).where(SpecDefinition.key.in_(keys)))
    return {definition.key: definition for definition in definitions}


def _record_execution_failure(task: ResearchTask, now: datetime, max_attempts: int) -> None:
    if task.attempt_count >= max_attempts:
        _memoize_failure(task, FailureReason.retries_exhausted, now)
        logger.warning(
            "research task %s exhausted %s attempts; flagged for review",
            task.id,
            task.attempt_count,
        )
        return
    task.state = ResearchTaskState.queued
    backoff_index = min(task.attempt_count - 1, len(EXECUTION_BACKOFF) - 1)
    task.next_attempt_at = now + EXECUTION_BACKOFF[backoff_index]


@dataclass(frozen=True)
class _Candidate:
    finding: SpecFinding
    tier: SourceType
    canonical_value: float | str


def _resolve_spec_task(
    db: Session,
    task: ResearchTask,
    definition: SpecDefinition | None,
    findings: ResearchFindings,
    now: datetime,
    conflict_tolerance: float,
) -> None:
    if definition is None:
        # The registry no longer knows this key; there is nothing to research.
        _memoize_failure(task, FailureReason.not_applicable, now)
        return
    candidates = _normalized_candidates(definition, findings.spec_findings)
    if not candidates:
        _memoize_missing(task, findings, findings.not_applicable_spec_keys, now)
        return

    by_tier: dict[SourceType, list[_Candidate]] = {}
    for candidate in candidates:
        by_tier.setdefault(candidate.tier, []).append(candidate)
    tiers = sorted(by_tier, key=lambda tier: SOURCE_TIER_PRIORITY[tier])

    is_numeric = definition.value_type == ValueType.number
    if is_numeric and _conflicts(by_tier[tiers[0]], conflict_tolerance):
        logger.warning(
            "same-tier conflict on %s for bike %s; flagged for review",
            task.fact_key,
            task.motorcycle_id,
        )
        _memoize_failure(task, FailureReason.unresolved_conflict, now)
        return

    result = None
    for tier in tiers:
        group = by_tier[tier]
        if is_numeric and _conflicts(group, conflict_tolerance):
            # A disagreement below the best tier discredits that tier only; the
            # cleanly-sourced tiers above it are still worth storing.
            continue
        written = _write_tier_group(db, task, definition, group, tier, now)
        if written is not None and result is None:
            result = written
    if result is None:
        _memoize_failure(task, FailureReason.no_reliable_source, now)
        return
    _mark_found(task, now)
    task.result_spec_value_id = result.id


def _normalized_candidates(
    definition: SpecDefinition, findings: tuple[SpecFinding, ...]
) -> list[_Candidate]:
    candidates = []
    for finding in findings:
        if finding.spec_key != definition.key:
            continue
        if not tiering.is_valid_source_url(finding.source_url):
            continue
        canonical_value = _canonical_value(definition, finding)
        if canonical_value is None:
            continue
        candidates.append(
            _Candidate(
                finding=finding,
                tier=tiering.classify_source_tier(finding.source_url),
                canonical_value=canonical_value,
            )
        )
    return candidates


def _canonical_value(definition: SpecDefinition, finding: SpecFinding) -> float | str | None:
    if definition.value_type == ValueType.number:
        if not isinstance(finding.value, int | float):
            return None
        source_unit = finding.unit if finding.unit else definition.canonical_unit
        try:
            return units.convert(float(finding.value), source_unit, definition.canonical_unit)
        except units.UnknownConversionError:
            return None
    if not isinstance(finding.value, str) or not finding.value.strip():
        return None
    return finding.value.strip()


def _conflicts(group: list[_Candidate], tolerance: float) -> bool:
    values = [
        candidate.canonical_value
        for candidate in group
        if isinstance(candidate.canonical_value, float)
    ]
    if len(values) < 2:
        return False
    spread = max(values) - min(values)
    mean = sum(values) / len(values)
    if mean == 0:
        return spread > 0
    return spread / abs(mean) > tolerance


def _write_tier_group(
    db: Session,
    task: ResearchTask,
    definition: SpecDefinition,
    group: list[_Candidate],
    tier: SourceType,
    now: datetime,
):
    if definition.value_type == ValueType.number:
        # The group agrees within tolerance; the median candidate keeps the stored
        # value paired with a real source URL.
        ordered = sorted(group, key=lambda candidate: candidate.canonical_value)
        chosen = ordered[len(ordered) // 2]
    else:
        chosen = group[0]
    try:
        return catalog_service.upsert_spec_value(
            db,
            task.motorcycle_id,
            task.fact_key,
            chosen.canonical_value,
            None,
            tier,
            source_url=chosen.finding.source_url,
            source_note=chosen.finding.source_note,
            retrieved_at=now,
        )
    except catalog_service.CatalogValidationError as error:
        logger.warning(
            "dropped %s candidate for task %s: %s", tier.value, task.id, error
        )
        return None


def _resolve_insight_task(
    db: Session,
    task: ResearchTask,
    findings: ResearchFindings,
    now: datetime,
) -> None:
    candidate = _best_insight_candidate(task.fact_key, findings.insight_findings)
    if candidate is None:
        _memoize_missing(task, findings, findings.not_applicable_topics, now)
        return
    finding, urls = candidate
    tiers = {tiering.classify_source_tier(url) for url in urls}
    source_type = SourceType.tested if SourceType.tested in tiers else SourceType.community
    try:
        insight = catalog_service.upsert_insight(
            db,
            task.motorcycle_id,
            task.fact_key,
            finding.summary,
            source_type,
            urls,
            retrieved_at=now,
        )
    except catalog_service.CatalogValidationError as error:
        logger.warning("dropped insight candidate for task %s: %s", task.id, error)
        _memoize_failure(task, FailureReason.no_reliable_source, now)
        return
    _mark_found(task, now)
    task.result_insight_id = insight.id


def _best_insight_candidate(
    topic: str, findings: tuple[InsightFinding, ...]
) -> tuple[InsightFinding, list[str]] | None:
    for finding in findings:
        if finding.topic != topic or not finding.summary.strip():
            continue
        urls = [url for url in finding.source_urls if tiering.is_valid_source_url(url)]
        if urls:
            # A summary without verifiable sources is never stored.
            return finding, urls
    return None


def _memoize_missing(
    task: ResearchTask,
    findings: ResearchFindings,
    not_applicable_keys: frozenset[str],
    now: datetime,
) -> None:
    if task.fact_key in not_applicable_keys:
        _memoize_failure(task, FailureReason.not_applicable, now)
    elif findings.expected_release_date is not None:
        _memoize_failure(
            task,
            FailureReason.not_released_yet,
            now,
            recheck_after=_start_of_day_utc(findings.expected_release_date),
        )
    else:
        _memoize_failure(task, FailureReason.no_reliable_source, now)


def _memoize_failure(
    task: ResearchTask,
    reason: FailureReason,
    now: datetime,
    recheck_after: datetime | None = None,
) -> None:
    if recheck_after is None and reason in FAILURE_COOLDOWNS:
        cooldown = FAILURE_COOLDOWNS[reason]
        recheck_after = now + cooldown if cooldown is not None else None
    task.state = (
        ResearchTaskState.failed
        if reason == FailureReason.retries_exhausted
        else ResearchTaskState.not_found
    )
    task.failure_reason = reason
    task.recheck_after = recheck_after
    task.completed_at = now
    task.next_attempt_at = None


def _mark_found(task: ResearchTask, now: datetime) -> None:
    task.state = ResearchTaskState.found
    task.failure_reason = None
    task.recheck_after = None
    task.completed_at = now
    task.next_attempt_at = None


def _start_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)
