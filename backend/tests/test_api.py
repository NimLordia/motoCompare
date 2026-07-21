import pytest
from fastapi.testclient import TestClient

from app.catalog import service
from app.db import get_db
from app.main import create_app


@pytest.fixture()
def client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.fixture()
def seeded_bike(db, make_bike):
    bike = make_bike(manufacturer="Yamaha", model="YZF-R7", year=2023, market="EU")
    service.upsert_spec_value(
        db, bike.id, "power_peak", 54.0, "kW", "official",
        source_url="https://www.yamaha-motor.eu",
    )
    service.upsert_insight(
        db, bike.id, "comfort", "sporty ergonomics", "community",
        ["https://www.reddit.com/r/YamahaR7/"],
    )
    return bike


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_browse_hierarchy(client, seeded_bike, db):
    manufacturers = client.get("/api/catalog/manufacturers").json()
    assert [manufacturer["name"] for manufacturer in manufacturers] == ["Yamaha"]

    models = client.get(
        f"/api/catalog/manufacturers/{manufacturers[0]['id']}/models"
    ).json()
    assert [model["name"] for model in models] == ["YZF-R7"]

    variants = client.get(f"/api/catalog/models/{models[0]['id']}/variants").json()
    assert [variant["id"] for variant in variants] == [seeded_bike.id]
    assert variants[0]["display_name"] == "Yamaha YZF-R7 2023 (EU)"


def test_bike_detail_includes_specs_insights_and_coverage(client, seeded_bike):
    detail = client.get(f"/api/catalog/bikes/{seeded_bike.id}").json()

    assert detail["bike"]["display_name"] == "Yamaha YZF-R7 2023 (EU)"
    assert detail["specs"][0]["spec_key"] == "power_peak"
    assert detail["insights"][0]["topic"] == "comfort"
    assert detail["coverage"]["core_specs_present"] == ["power_peak"]
    assert detail["coverage"]["complete"] is False


def test_bike_detail_imperial_units(client, seeded_bike):
    detail = client.get(
        f"/api/catalog/bikes/{seeded_bike.id}", params={"unit_system": "imperial"}
    ).json()
    power = detail["specs"][0]
    assert power["unit"] == "hp"
    assert power["value"] == pytest.approx(72.42, abs=0.01)


def test_unknown_bike_maps_to_404(client):
    response = client.get("/api/catalog/bikes/424242")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_unknown_spec_key_maps_to_422(client, seeded_bike):
    response = client.get(
        f"/api/catalog/bikes/{seeded_bike.id}/specs", params={"keys": "flux_capacitance"}
    )
    assert response.status_code == 422


def test_resolve_endpoint(client, seeded_bike):
    candidates = client.get("/api/catalog/bikes/resolve", params={"q": "r7"}).json()
    assert candidates[0]["bike"]["id"] == seeded_bike.id
    assert candidates[0]["confidence"] == 1.0


def test_compare_endpoint(client, db, make_bike, seeded_bike):
    other = make_bike(manufacturer="Yamaha", model="MT-07", year=2023, market="EU")
    service.upsert_spec_value(db, other.id, "torque_peak", 67.0, "Nm", "official")

    matrix = client.get(
        "/api/catalog/bikes/compare", params={"ids": [seeded_bike.id, other.id]}
    ).json()

    assert [row["spec_key"] for row in matrix["rows"]] == ["power_peak", "torque_peak"]
    assert matrix["rows"][0]["cells"][1]["missing"] is True
