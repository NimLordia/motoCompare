from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ResearchKind(StrEnum):
    spec = "spec"
    insight = "insight"


class ResearchTaskState(StrEnum):
    queued = "queued"
    searching = "searching"
    found = "found"
    not_found = "not_found"
    failed = "failed"


class FailureReason(StrEnum):
    not_released_yet = "not_released_yet"
    no_reliable_source = "no_reliable_source"
    unresolved_conflict = "unresolved_conflict"
    not_applicable = "not_applicable"
    retries_exhausted = "retries_exhausted"


# Knowledge-failure cooldowns: how long until the fact is worth researching again.
# None means never. not_released_yet is absent because its recheck date comes from
# the research result (the expected release date), not from a fixed cooldown.
FAILURE_COOLDOWNS: dict[FailureReason, timedelta | None] = {
    FailureReason.no_reliable_source: timedelta(days=30),
    FailureReason.unresolved_conflict: timedelta(days=30),
    FailureReason.not_applicable: None,
    FailureReason.retries_exhausted: timedelta(days=7),
}

# Execution-error backoff: the attempt that just failed (1-based) indexes the delay
# before the next one; attempts past the schedule reuse the last delay.
EXECUTION_BACKOFF: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=10),
    timedelta(hours=1),
)


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    # This constraint IS the "research once for all users" guarantee.
    __table_args__ = (UniqueConstraint("motorcycle_id", "kind", "fact_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    motorcycle_id: Mapped[int] = mapped_column(
        ForeignKey("motorcycles.id", ondelete="CASCADE")
    )
    kind: Mapped[ResearchKind] = mapped_column(Enum(ResearchKind, native_enum=False, length=10))
    fact_key: Mapped[str] = mapped_column(String(50))
    state: Mapped[ResearchTaskState] = mapped_column(
        Enum(ResearchTaskState, native_enum=False, length=10),
        default=ResearchTaskState.queued,
        server_default="queued",
    )
    failure_reason: Mapped[FailureReason | None] = mapped_column(
        Enum(FailureReason, native_enum=False, length=20)
    )
    recheck_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_spec_value_id: Mapped[int | None] = mapped_column(
        ForeignKey("spec_values.id", ondelete="SET NULL")
    )
    result_insight_id: Mapped[int | None] = mapped_column(
        ForeignKey("insights.id", ondelete="SET NULL")
    )
