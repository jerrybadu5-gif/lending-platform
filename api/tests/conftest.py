import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    app = create_app(Settings(backend="demo", session_secret="test-secret", allowed_origins=["http://test"]))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def staff(client):
    r = client.post("/api/staff/login", json={"username": "demo", "password": "demo"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def sms(client):
    return client.app.state.services.sms
