"""McLender's own database: sign-ins, codes and lock-outs survive an API restart."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.main import create_app
from app.store import usable_url


def app_on(db_url: str, secret: str = "test-secret"):
    return create_app(
        Settings(backend="demo", session_secret=secret, allowed_origins=["http://test"], database_url=db_url)
    )


@pytest.fixture(params=["sqlite", "postgresql"])
def db(request, tmp_path):
    """Each test runs on SQLite, and on PostgreSQL too when MCL_TEST_DATABASE_URL names one (CI does)."""
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path / 'mclender.db'}"
    url = os.environ.get("MCL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MCL_TEST_DATABASE_URL not set")
    engine = create_engine(url)
    with engine.begin() as conn:  # start each test from an empty database
        for table in ("mcl_rate_hit", "mcl_otp", "mcl_session", "alembic_version"):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    engine.dispose()
    return url


def test_staff_stay_signed_in_across_a_restart(db):
    with TestClient(app_on(db)) as first:
        login = first.post("/api/staff/login", json={"username": "demo", "password": "demo"})
        assert login.status_code == 200
        cookies = dict(first.cookies)
        headers = {"X-MCL-User": login.json()["username"], "X-MCL-Tab": login.json()["tab_credential"]}
    # The browser retains its cookie and tab credential across an API restart.
    with TestClient(app_on(db), cookies=cookies, headers=headers) as second:
        r = second.get("/api/staff/me")
        assert r.status_code == 200 and r.json()["display_name"] == "Grace Pokana"
        second.post("/api/staff/logout")
        assert second.get("/api/staff/me").status_code == 401


def test_sessions_are_stored_hashed_and_encrypted(db):
    with TestClient(app_on(db)) as c:
        c.post("/api/staff/login", json={"username": "demo", "password": "demo"})
        cookie = c.cookies.get("mcl_staff")
    engine = create_engine(db)
    with engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(text("select id_hash, payload from mcl_session"))]
    engine.dispose()
    assert len(rows) == 1
    id_hash, payload = rows[0]
    assert cookie not in id_hash and b"demo" not in payload and b"Grace" not in payload


def test_a_new_session_secret_signs_everyone_out(db):
    with TestClient(app_on(db)) as first:
        first.post("/api/staff/login", json={"username": "demo", "password": "demo"})
        cookies = dict(first.cookies)
    with TestClient(app_on(db, secret="another-secret"), cookies=cookies) as second:
        assert second.get("/api/staff/me").status_code == 401


def test_lock_out_survives_a_restart(db):
    with TestClient(app_on(db)) as first:
        for _ in range(10):
            assert first.post("/api/staff/login", json={"username": "x", "password": "y"}).status_code == 401
    with TestClient(app_on(db)) as second:
        assert second.post("/api/staff/login", json={"username": "x", "password": "y"}).status_code == 429


def test_portal_sign_in_code_through_the_database(db):
    with TestClient(app_on(db)) as c:
        assert c.post("/api/portal/otp", json={"phone": "70123344"}).status_code == 200
        code = c.app.state.services.sms.sent[-1][1].split("code is ")[1][:6]
        assert c.post("/api/portal/verify", json={"phone": "70123344", "code": "000000"}).status_code == 401
        r = c.post("/api/portal/verify", json={"phone": "70123344", "code": code})
        assert r.status_code == 200, r.text
        assert c.get("/api/portal/home").status_code == 200
        assert c.post("/api/portal/verify", json={"phone": "70123344", "code": code}).status_code == 401  # used


def test_which_database_urls_are_used():
    assert not usable_url("")
    assert not usable_url("postgresql+psycopg://mclender:@postgresql:5432/mclender")  # password not set up yet
    assert not usable_url("postgresql+psycopg://mclender:change-me-mclender@postgresql:5432/mclender")
    assert usable_url("postgresql+psycopg://mclender:s3cret@postgresql:5432/mclender")
    assert usable_url("sqlite:///x.db")
