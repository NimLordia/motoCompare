import pytest
from fastapi.testclient import TestClient

from app.catalog import service as catalog_service
from app.catalog.registry import CORE_SPEC_KEYS, INSIGHT_TOPICS
from app.db import get_db
from app.main import create_app
from app.research.provider import InsightFinding, ResearchFindings, SpecFinding
from app.research.runner import run_bike_research

OFFICIAL_URL = "https://www.yamaha-motor.eu/gb/en/products/motorcycles/yzf-r7/"
FORUM_URL = "https://www.r7forum.com/threads/ownership-report.1/"


@pytest.fixture()
def client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_populate_creates_queued_tasks(client, make_bike):
    bike = make_bike()

    tasks = client.post(f"/api/research/bikes/{bike.id}/populate").json()

    assert len(tasks) == len(CORE_SPEC_KEYS) + len(INSIGHT_TOPICS)
    assert {task["state"] for task in tasks} == {"queued"}
    assert {task["fact_key"] for task in tasks if task["kind"] == "spec"} == set(
        CORE_SPEC_KEYS
    )


def test_request_task_endpoint_is_idempotent(client, make_bike):
    bike = make_bike()
    payload = {"kind": "spec", "fact_key": "top_speed"}

    first = client.post(f"/api/research/bikes/{bike.id}/tasks", json=payload).json()
    second = client.post(f"/api/research/bikes/{bike.id}/tasks", json=payload).json()

    assert first["id"] == second["id"]
    assert first["state"] == "queued"


def test_unknown_bike_maps_to_404(client):
    response = client.post("/api/research/bikes/424242/populate")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_unknown_fact_key_maps_to_422(client, make_bike):
    bike = make_bike()
    response = client.post(
        f"/api/research/bikes/{bike.id}/tasks",
        json={"kind": "spec", "fact_key": "flux_capacitance"},
    )
    assert response.status_code == 422


def test_unknown_kind_rejected_by_schema(client, make_bike):
    bike = make_bike()
    response = client.post(
        f"/api/research/bikes/{bike.id}/tasks",
        json={"kind": "rumor", "fact_key": "top_speed"},
    )
    assert response.status_code == 422


def test_get_task_by_id(client, make_bike):
    bike = make_bike()
    created = client.post(
        f"/api/research/bikes/{bike.id}/tasks",
        json={"kind": "insight", "fact_key": "heat"},
    ).json()

    fetched = client.get(f"/api/research/tasks/{created['id']}").json()

    assert fetched == created


def test_get_unknown_task_maps_to_404(client):
    assert client.get("/api/research/tasks/424242").status_code == 404


def test_populate_then_research_fills_coverage(client, db, make_bike, fake_provider):
    bike = make_bike()
    client.post(f"/api/research/bikes/{bike.id}/populate")

    fake_provider.findings = ResearchFindings(
        spec_findings=tuple(
            SpecFinding(
                key,
                "Parallel twin" if key == "engine_type" else 100.0,
                None,
                OFFICIAL_URL,
            )
            for key in CORE_SPEC_KEYS
        ),
        insight_findings=tuple(
            InsightFinding(topic, f"Owners agree about {topic}.", (FORUM_URL,))
            for topic in INSIGHT_TOPICS
        ),
    )
    run_bike_research(db, fake_provider, bike.id)

    tasks = client.get(f"/api/research/bikes/{bike.id}/tasks").json()
    assert {task["state"] for task in tasks} == {"found"}

    coverage = client.get(f"/api/catalog/bikes/{bike.id}/coverage").json()
    assert coverage["complete"] is True
    assert coverage["core_specs_missing"] == []
    assert coverage["insight_topics_missing"] == []


def test_in_flight_research_shows_in_coverage(client, db, make_bike):
    bike = make_bike()
    client.post(f"/api/research/bikes/{bike.id}/populate")

    # The lifespan hook registers this in production; tests wire it directly.
    from app.research import service as research_service

    catalog_service.register_pending_research_provider(
        research_service.pending_research_for_bike
    )
    try:
        coverage = client.get(f"/api/catalog/bikes/{bike.id}/coverage").json()
    finally:
        catalog_service.register_pending_research_provider(
            catalog_service._no_pending_research
        )

    assert coverage["research_pending_specs"] == sorted(CORE_SPEC_KEYS)
    assert coverage["research_pending_topics"] == sorted(INSIGHT_TOPICS)
