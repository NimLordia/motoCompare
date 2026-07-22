from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.catalog.schemas import BikeCandidate, ComparisonMatrix, Fact, InsightOut, VariantOut
from app.research.models import ResearchKind


class ChatMessageIn(BaseModel):
    # Omitted on the first message of a conversation; the server generates one
    # and returns it in the `done` event.
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)


class SpecCardBlock(BaseModel):
    type: Literal["spec_card"] = "spec_card"
    bike: VariantOut
    facts: list[Fact]


class ComparisonTableBlock(BaseModel):
    type: Literal["comparison_table"] = "comparison_table"
    matrix: ComparisonMatrix


class InsightCardBlock(BaseModel):
    type: Literal["insight_card"] = "insight_card"
    bike: VariantOut
    insights: list[InsightOut]


class ResearchPendingBlock(BaseModel):
    type: Literal["research_pending"] = "research_pending"
    bike: VariantOut
    kind: ResearchKind
    fact_keys: list[str]


class DisambiguationBlock(BaseModel):
    type: Literal["disambiguation"] = "disambiguation"
    query: str
    candidates: list[BikeCandidate]


ChatBlock = Annotated[
    SpecCardBlock
    | ComparisonTableBlock
    | InsightCardBlock
    | ResearchPendingBlock
    | DisambiguationBlock,
    Field(discriminator="type"),
]
