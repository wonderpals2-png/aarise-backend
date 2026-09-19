import datetime
import math

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import Base, SessionLocal, engine
from app.main import app
from app.routers import ride_router


PICKUP = {"pickup_lat": 28.6139, "pickup_lng": 77.2090, "pickup_label": "India Gate"}
DROP = {"drop_lat": 28.6339, "drop_lng": 77.2290, "drop_label": "Civil Lines"}


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(client, phone="9000000001"):
    response = client.post("/auth/register", json={"name": "Test Rider", "phone": phone, "password": "password"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_ride(client, headers):
    response = client.post("/rides", headers=headers, json={**PICKUP, **DROP})
    assert response.status_code == 201
    return response.json()


def set_time(monkeypatch, requested_at, seconds):
    monkeypatch.setattr(ride_router, "now", lambda: requested_at + datetime.timedelta(seconds=seconds))


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    d_lat = lat2 - lat1
    d_lng = lng2 - lng1
    value = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def test_status_boundaries(monkeypatch, client):
    headers = auth_headers(client)
    base_time = datetime.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(ride_router, "now", lambda: base_time)
    ride = create_ride(client, headers)
    boundaries = [
        (0, "searching"),
        (ride_router.T_SEARCH, "driver_arriving"),
        (ride_router.T_SEARCH + ride_router.T_ARRIVE, "driver_arrived"),
        (ride_router.T_SEARCH + ride_router.T_ARRIVE + ride_router.T_OTP_WAIT, "in_ride"),
        (ride_router.T_SEARCH + ride_router.T_ARRIVE + ride_router.T_OTP_WAIT + ride_router.T_RIDE_MIN, "completed"),
    ]
    for seconds, expected in boundaries:
        set_time(monkeypatch, base_time, seconds)
        response = client.get(f"/rides/{ride['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == expected


def test_driver_arrival_path(monkeypatch, client):
    headers = auth_headers(client)
    base_time = datetime.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(ride_router, "now", lambda: base_time)
    ride = create_ride(client, headers)
    set_time(monkeypatch, base_time, ride_router.T_SEARCH)
    starting = client.get(f"/rides/{ride['id']}", headers=headers).json()
    assert starting["status"] == "driver_arriving"
    assert haversine_km(PICKUP["pickup_lat"], PICKUP["pickup_lng"], starting["driver_lat"], starting["driver_lng"]) == pytest.approx(ride_router.DRIVER_START_KM, abs=0.01)
    set_time(monkeypatch, base_time, ride_router.T_SEARCH + ride_router.T_ARRIVE)
    arrived = client.get(f"/rides/{ride['id']}", headers=headers).json()
    assert arrived["status"] == "driver_arrived"
    assert arrived["driver_lat"] == PICKUP["pickup_lat"]
    assert arrived["driver_lng"] == PICKUP["pickup_lng"]


def test_second_active_ride_is_rejected(client):
    headers = auth_headers(client)
    create_ride(client, headers)
    response = client.post("/rides", headers=headers, json={**PICKUP, **DROP})
    assert response.status_code == 409


def test_other_rider_cannot_view_ride(client):
    owner_headers = auth_headers(client)
    ride = create_ride(client, owner_headers)
    other_headers = auth_headers(client, "9000000002")
    response = client.get(f"/rides/{ride['id']}", headers=other_headers)
    assert response.status_code == 404


def test_cannot_cancel_in_ride(monkeypatch, client):
    headers = auth_headers(client)
    base_time = datetime.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(ride_router, "now", lambda: base_time)
    ride = create_ride(client, headers)
    set_time(monkeypatch, base_time, ride_router.T_SEARCH + ride_router.T_ARRIVE + ride_router.T_OTP_WAIT)
    response = client.post(f"/rides/{ride['id']}/cancel", headers=headers)
    assert response.status_code == 409


def test_otp_visibility(monkeypatch, client):
    headers = auth_headers(client)
    base_time = datetime.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(ride_router, "now", lambda: base_time)
    ride = create_ride(client, headers)
    searching = client.get(f"/rides/{ride['id']}", headers=headers).json()
    assert "otp" not in searching
    set_time(monkeypatch, base_time, ride_router.T_SEARCH)
    arriving = client.get(f"/rides/{ride['id']}", headers=headers).json()
    assert len(arriving["otp"]) == 4
    set_time(monkeypatch, base_time, ride_router.T_SEARCH + ride_router.T_ARRIVE + ride_router.T_OTP_WAIT)
    in_ride = client.get(f"/rides/{ride['id']}", headers=headers).json()
    assert "otp" not in in_ride


def test_estimate_for_known_coordinate_pair(client):
    headers = auth_headers(client)
    response = client.post(
        "/rides/estimate",
        headers=headers,
        json={"pickup_lat": 0, "pickup_lng": 0, "drop_lat": 1, "drop_lng": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["distance_km"] == pytest.approx(111.1949 * ride_router.ROAD_FACTOR, abs=0.01)
    assert data["est_fare"] == round(ride_router.FARE_BASE + ride_router.FARE_PER_KM * data["distance_km"])


def test_existing_endpoints_remain_available(client):
    assert client.get("/health").status_code == 200
    headers = auth_headers(client)
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.patch("/auth/me", headers=headers, json={"name": "Updated Rider"}).status_code == 200
    assert client.post("/auth/device", headers=headers, json={"device_id": "TEST-DEVICE-1"}).status_code == 200
    contact = client.post("/contacts", headers=headers, json={"name": "Friend", "phone": "9000000009"}).json()
    assert client.get("/contacts", headers=headers).status_code == 200
    assert client.delete(f"/contacts/{contact['id']}", headers=headers).status_code == 204
    alert = client.post("/alerts/sos", headers=headers, json={"latitude": 1, "longitude": 2}).json()
    assert client.get("/alerts", headers=headers).status_code == 200
    assert client.patch(f"/alerts/{alert['id']}/resolve", headers=headers).status_code == 200
    assert client.post("/alerts/device-sos?device_id=TEST-DEVICE-1", headers={"X-Device-Key": "dev-device-key-change-me"}, json={}).status_code == 201
    assert client.post("/location/refresh", headers=headers, json={"latitude": 1, "longitude": 2}).status_code == 200
    assert client.get("/location/latest", headers=headers).status_code == 200
    assert client.get("/location/history", headers=headers).status_code == 200
    assert client.post("/location/device-ping?device_id=TEST-DEVICE-1", headers={"X-Device-Key": "dev-device-key-change-me"}, json={"latitude": 1, "longitude": 2}).status_code == 200
