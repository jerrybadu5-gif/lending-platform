import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    app = create_app(Settings(backend="demo", session_secret="test-secret", allowed_origins=["http://test"]))
    with TestClient(app) as c:
        yield c


def login_staff(client, username="demo"):
    r = client.post("/api/staff/login", json={"username": username, "password": username})
    assert r.status_code == 200, r.text
    headers = {"X-MCL-User": r.json()["username"], "X-MCL-Tab": r.json()["tab_token"]}
    client.headers.update(headers)
    return headers


@pytest.fixture
def staff(client):
    login_staff(client)
    return client


@pytest.fixture
def sms(client):
    return client.app.state.services.sms
