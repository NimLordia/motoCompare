import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import create_app


@pytest.fixture()
def client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_get_profile_returns_defaults(client):
    profile = client.get("/api/profile").json()

    assert profile["unit_system"] == "metric"
    assert profile["market"] is None
    assert profile["priority_factors"] == []
    assert profile["current_bike"] is None


def test_put_profile_round_trip(client):
    payload = {
        "unit_system": "mixed",
        "market": "EU",
        "riding_style": "commuting",
        "priority_factors": ["comfort", "cost"],
    }

    updated = client.put("/api/profile", json=payload).json()
    fetched = client.get("/api/profile").json()

    assert updated == fetched
    assert fetched["unit_system"] == "mixed"
    assert fetched["priority_factors"] == ["comfort", "cost"]


def test_put_profile_unknown_unit_system_is_422(client):
    response = client.put("/api/profile", json={"unit_system": "nautical"})
    assert response.status_code == 422


def test_put_profile_repeated_factors_is_422(client):
    response = client.put(
        "/api/profile",
        json={"unit_system": "metric", "priority_factors": ["heat", "heat"]},
    )
    assert response.status_code == 422
    assert "repeat" in response.json()["detail"]


def test_garage_add_and_list(client, make_bike):
    bike = make_bike()

    added = client.post(
        "/api/garage", json={"motorcycle_id": bike.id, "nickname": "daily"}
    ).json()
    garage = client.get("/api/garage").json()

    assert added["is_current"] is True
    assert added["nickname"] == "daily"
    assert added["bike"]["display_name"] == "Yamaha YZF-R7 2023 (EU)"
    assert garage == [added]


def test_garage_add_unknown_bike_is_404(client):
    response = client.post("/api/garage", json={"motorcycle_id": 424242})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_set_current_endpoint_switches(client, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    client.post("/api/garage", json={"motorcycle_id": first.id})
    second_entry = client.post("/api/garage", json={"motorcycle_id": second.id}).json()

    switched = client.put(f"/api/garage/{second_entry['id']}/current").json()
    garage = client.get("/api/garage").json()

    assert switched["is_current"] is True
    assert [entry["is_current"] for entry in garage] == [True, False]
    assert garage[0]["bike"]["id"] == second.id


def test_set_current_unknown_id_is_404(client):
    response = client.put("/api/garage/424242/current")
    assert response.status_code == 404


def test_delete_garage_bike_promotes_replacement(client, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    current_entry = client.post("/api/garage", json={"motorcycle_id": first.id}).json()
    client.post("/api/garage", json={"motorcycle_id": second.id})

    response = client.delete(f"/api/garage/{current_entry['id']}")
    garage = client.get("/api/garage").json()

    assert response.status_code == 204
    assert len(garage) == 1
    assert garage[0]["bike"]["id"] == second.id
    assert garage[0]["is_current"] is True


def test_delete_unknown_garage_bike_is_404(client):
    response = client.delete("/api/garage/424242")
    assert response.status_code == 404


def test_profile_includes_current_bike_after_garage_add(client, make_bike):
    bike = make_bike()
    client.post("/api/garage", json={"motorcycle_id": bike.id})

    profile = client.get("/api/profile").json()

    assert profile["current_bike"]["id"] == bike.id


def test_dream_bikes_flow(client, make_bike):
    bike = make_bike(manufacturer="Ducati", model="Panigale V4")

    added = client.post(
        "/api/dream-bikes", json={"motorcycle_id": bike.id, "note": "someday"}
    ).json()
    listed = client.get("/api/dream-bikes").json()
    deleted = client.delete(f"/api/dream-bikes/{added['id']}")

    assert listed == [added]
    assert added["note"] == "someday"
    assert deleted.status_code == 204
    assert client.get("/api/dream-bikes").json() == []


def test_delete_unknown_dream_bike_is_404(client):
    response = client.delete("/api/dream-bikes/424242")
    assert response.status_code == 404
