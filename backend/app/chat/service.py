import logging
import uuid
from collections.abc import Iterator
from typing import Any, NamedTuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from sqlalchemy.orm import Session

from app.chat.agent import RECURSION_LIMIT, build_chat_agent
from app.chat.tools import build_toolbox, status_line
from app.config import get_settings
from app.profile import service as profile_service
from app.profile.models import DEFAULT_USER_ID

logger = logging.getLogger(__name__)


class ChatEvent(NamedTuple):
    event: str  # status | text | block | done | error
    data: dict[str, Any]


# Configured at app startup (ChatGoogleGenerativeAI in production); left unset in
# tests, which inject a scripted model. Conversations live in the checkpointer for
# the process lifetime and reset with the model (see modules/chat.md).
_chat_model: BaseChatModel | None = None
_checkpointer: InMemorySaver | None = None


def configure_chat_model(model: BaseChatModel | None) -> None:
    global _chat_model, _checkpointer
    _chat_model = model
    _checkpointer = InMemorySaver() if model is not None else None


def chat_is_configured() -> bool:
    return _chat_model is not None


def stream_chat(
    db: Session,
    message: str,
    conversation_id: str | None = None,
    user_id: int = DEFAULT_USER_ID,
) -> Iterator[ChatEvent]:
    """Run one conversation turn, yielding SSE-ready events. Always terminates
    with `done` (carrying the conversation id) or `error`."""
    if _chat_model is None or _checkpointer is None:
        yield ChatEvent("error", {"detail": "chat model is not configured"})
        return
    settings = get_settings()
    conversation_id = conversation_id or uuid.uuid4().hex
    profile = profile_service.get_profile(db, user_id)
    toolbox = build_toolbox(
        db,
        user_id=user_id,
        unit_system=profile.unit_system.value,
        inline_budget_seconds=settings.research_inline_budget_seconds,
    )
    agent = build_chat_agent(_chat_model, toolbox, _checkpointer)
    config = {"configurable": {"thread_id": conversation_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        for mode, payload in agent.stream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                yield from _text_events(payload)
            else:
                yield from _update_events(payload)
        yield ChatEvent("done", {"conversation_id": conversation_id})
    except GraphRecursionError:
        logger.warning("chat turn exceeded %d graph steps", RECURSION_LIMIT)
        yield ChatEvent(
            "error",
            {"detail": "The assistant needed too many steps for this request. Try again."},
        )
    except Exception:
        logger.exception("chat turn failed")
        yield ChatEvent("error", {"detail": "The assistant hit an internal error. Try again."})


def _text_events(payload: Any) -> Iterator[ChatEvent]:
    """LLM token chunks → `text` events (tool results also pass through this
    stream mode and are skipped)."""
    message_chunk, _metadata = payload
    if not isinstance(message_chunk, AIMessageChunk):
        return
    text = _chunk_text(message_chunk.content)
    if text:
        yield ChatEvent("text", {"content": text})


def _update_events(payload: dict[str, Any]) -> Iterator[ChatEvent]:
    """Node completions → `status` events (from the agent's tool calls) and
    `block` events (from tool artifacts)."""
    for node_update in payload.values():
        for message in (node_update or {}).get("messages", []):
            if isinstance(message, AIMessage) and message.tool_calls:
                for tool_call in message.tool_calls:
                    yield ChatEvent(
                        "status", {"content": status_line(tool_call["name"], tool_call["args"])}
                    )
            elif isinstance(message, ToolMessage) and message.artifact:
                for block in message.artifact:
                    yield ChatEvent("block", block.model_dump(mode="json"))


def _chunk_text(content: str | list) -> str:
    """Gemini chunks may carry a string or a list of content parts."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "".join(parts)
