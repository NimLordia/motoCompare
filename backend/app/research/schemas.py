from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.research.models import FailureReason, ResearchKind, ResearchTaskState


class ResearchTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    motorcycle_id: int
    kind: ResearchKind
    fact_key: str
    state: ResearchTaskState
    failure_reason: FailureReason | None
    recheck_after: datetime | None
    attempt_count: int
    next_attempt_at: datetime | None
    attempted_at: datetime | None
    completed_at: datetime | None
    result_spec_value_id: int | None
    result_insight_id: int | None


class ResearchRequestIn(BaseModel):
    kind: ResearchKind
    fact_key: str = Field(min_length=1, max_length=50)
