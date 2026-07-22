import json
from collections.abc import Callable, Iterator, Sequence

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.profile.models  # noqa: F401  (registers profile tables for create_all)
from app.catalog.models import Manufacturer, Model, Motorcycle
from app.catalog.seed import seed_registry
from app.chat import service as chat_service
from app.db import Base
from app.research.provider import ResearchFindings, SpecRequest


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSession() as session:
        seed_registry(session)
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture()
def make_bike(db: Session):
    def _make_bike(
        manufacturer: str = "Yamaha",
        model: str = "YZF-R7",
        year: int = 2023,
        trim: str = "",
        market: str = "EU",
    ) -> Motorcycle:
        manufacturer_row = db.scalars(
            select(Manufacturer).where(Manufacturer.name == manufacturer)
        ).one_or_none()
        if manufacturer_row is None:
            manufacturer_row = Manufacturer(name=manufacturer)
            db.add(manufacturer_row)
            db.flush()
        model_row = db.scalars(
            select(Model).where(
                Model.manufacturer_id == manufacturer_row.id, Model.name == model
            )
        ).one_or_none()
        if model_row is None:
            model_row = Model(manufacturer_id=manufacturer_row.id, name=model)
            db.add(model_row)
            db.flush()
        bike = Motorcycle(model_id=model_row.id, year=year, trim=trim, market=market)
        db.add(bike)
        db.flush()
        return bike

    return _make_bike


class FakeSearchProvider:
    """Scripted SearchProvider: returns `findings`, or raises `error` if set."""

    def __init__(self) -> None:
        self.findings = ResearchFindings()
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []

    def research(
        self,
        bike_description: str,
        spec_requests: Sequence[SpecRequest],
        insight_topics: Sequence[str],
    ) -> ResearchFindings:
        self.calls.append(
            (
                bike_description,
                tuple(request.key for request in spec_requests),
                tuple(insight_topics),
            )
        )
        if self.error is not None:
            raise self.error
        return self.findings


@pytest.fixture()
def fake_provider() -> FakeSearchProvider:
    return FakeSearchProvider()


class FakeChatModel(BaseChatModel):
    """Scripted chat model: replays `responses`, one per LLM call, and records
    the prompts it saw. With `loop_last`, the final response repeats forever."""

    responses: list[AIMessage]
    loop_last: bool = False
    call_index: int = 0
    seen_prompts: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tool_names: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence, **kwargs) -> "FakeChatModel":
        self.bound_tool_names = [tool.name for tool in tools]
        return self

    def _next_response(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen_prompts.append(list(messages))
        if self.loop_last and self.call_index >= len(self.responses):
            return self.responses[-1]
        response = self.responses[self.call_index]  # IndexError = script exhausted
        self.call_index += 1
        return response

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next_response(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs,
    ) -> Iterator[ChatGenerationChunk]:
        response = self._next_response(messages)
        if response.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tool_call["name"],
                            "args": json.dumps(tool_call["args"]),
                            "id": tool_call["id"],
                            "index": position,
                            "type": "tool_call_chunk",
                        }
                        for position, tool_call in enumerate(response.tool_calls)
                    ],
                )
            )
            return
        # Word-level chunks so tests exercise token streaming.
        words = str(response.content).split(" ")
        for position, word in enumerate(words):
            text = word if position == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=text))


@pytest.fixture()
def scripted_chat() -> Iterator[Callable[..., FakeChatModel]]:
    """Configure the chat service with a scripted model; unconfigures on teardown."""

    def _configure(*responses: AIMessage, loop_last: bool = False) -> FakeChatModel:
        model = FakeChatModel(responses=list(responses), loop_last=loop_last)
        chat_service.configure_chat_model(model)
        return model

    yield _configure
    chat_service.configure_chat_model(None)
