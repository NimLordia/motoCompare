import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.chat import service
from app.chat.schemas import ChatMessageIn
from app.chat.service import ChatEvent
from app.db import get_db

router = APIRouter()


@router.post("/messages")
def post_message(
    payload: ChatMessageIn, db: Annotated[Session, Depends(get_db)]
) -> StreamingResponse:
    if not service.chat_is_configured():
        raise HTTPException(
            status_code=503,
            detail="chat model is not configured; set MOTO_GEMINI_API_KEY",
        )
    events = service.stream_chat(
        db, message=payload.message, conversation_id=payload.conversation_id
    )
    return StreamingResponse(
        _as_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _as_sse(events: Iterator[ChatEvent]) -> Iterator[str]:
    for event in events:
        yield f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"
