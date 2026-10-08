import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class StaffTabClient(TestClient):
    def post(self, url, *args, **kwargs):
        response = super().post(url, *args, **kwargs)
        if url == "/api/staff/login" and response.status_code == 200:
            user = response.json()
            self.headers.update({"X-MCL-User": user["username"], "X-MCL-Tab": user["tab_credential"]})
        return response


def login_staff(client, username="demo"):
    response = client.post("/api/staff/login", json={"username": username, "password": username})
    assert response.status_code == 200, response.text
    return {"X-MCL-User": response.json()["username"], "X-MCL-Tab": response.json()["tab_credential"]}


@pytest.fixture
def client():
    app = create_app(Settings(backend="demo", session_secret="test-secret", allowed_origins=["http://test"]))
    with StaffTabClient(app) as c:
        yield c


@pytest.fixture
def staff(client):
    login_staff(client)
    return client


@pytest.fixture
def sms(client):
    return client.app.state.services.sms
