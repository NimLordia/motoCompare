import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.catalog import service as catalog_service
from app.chat import service as chat_service
from app.db import get_db
from app.main import create_app

YAMAHA_URL = "https://www.yamaha-motor.eu/r7"


@pytest.fixture()
def client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in body.strip().split("\n\n"):
        lines = chunk.split("\n")
        event = next(line[len("event: ") :] for line in lines if line.startswith("event: "))
        data = json.loads(
            next(line[len("data: ") :] for line in lines if line.startswith("data: "))
        )
        events.append((event, data))
    return events


def test_chat_without_model_is_503(client):
    chat_service.configure_chat_model(None)

    response = client.post("/api/chat/messages", json={"message": "hello"})

    assert response.status_code == 503
    assert "MOTO_GEMINI_API_KEY" in response.json()["detail"]


def test_chat_streams_sse_events(client, scripted_chat):
    scripted_chat(AIMessage(content="Hello rider!"))

    response = client.post(
        "/api/chat/messages", json={"message": "hi", "conversation_id": "api-conv"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    text = "".join(data["content"] for event, data in events if event == "text")
    assert text == "Hello rider!"
    assert events[-1] == ("done", {"conversation_id": "api-conv"})


def test_chat_streams_blocks_over_http(client, db, make_bike, scripted_chat):
    bike = make_bike()
    catalog_service.upsert_spec_value(
        db, bike.id, "power_peak", 54.0, "kW", "official", source_url=YAMAHA_URL
    )
    scripted_chat(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_specs", "args": {"bike_id": bike.id}, "id": "c1"}
            ],
        ),
        AIMessage(content="Here are the specs."),
    )

    events = parse_sse(client.post("/api/chat/messages", json={"message": "specs?"}).text)

    kinds = [event for event, _ in events]
    assert "status" in kinds and "block" in kinds and "done" in kinds
    block = next(data for event, data in events if event == "block")
    assert block["type"] == "spec_card"
    assert block["facts"][0]["source_type"] == "official"


def test_chat_empty_message_is_422(client, scripted_chat):
    scripted_chat(AIMessage(content="unused"))

    response = client.post("/api/chat/messages", json={"message": ""})

    assert response.status_code == 422
