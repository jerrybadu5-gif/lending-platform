import re


def login(client, sms, phone="+675 7012 3344"):
    r = client.post("/api/portal/otp", json={"phone": phone})
    assert r.status_code == 200
    code = re.search(r"\b(\d{6})\b", sms.sent[-1][1]).group(1)
    r = client.post("/api/portal/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def test_otp_same_answer_for_unknown_number(client, sms):
    known = client.post("/api/portal/otp", json={"phone": "70123344"}).json()
    unknown = client.post("/api/portal/otp", json={"phone": "79999999"}).json()
    assert known == unknown
    assert [to for to, _ in sms.sent] == ["70123344"]


def test_wrong_code_then_lockout(client, sms):
    client.post("/api/portal/otp", json={"phone": "70123344"})
    for _ in range(5):
        assert client.post("/api/portal/verify", json={"phone": "70123344", "code": "000000"}).status_code == 401
    real = re.search(r"\b(\d{6})\b", sms.sent[-1][1]).group(1)
    assert client.post("/api/portal/verify", json={"phone": "70123344", "code": real}).status_code == 401


def test_home_shows_only_own_loan(client, sms):
    assert login(client, sms)["first_name"] == "Mary"
    h = client.get("/api/portal/home").json()
    loan = h["loan"]
    assert h["company_name"] == "Breez Lending"
    assert loan["ref"] == "LN-000482" and loan["payments_made"] == 6 and loan["payments_total"] == 12
    assert loan["left_to_pay"] == "7912.43"
    assert loan["next_due_amount"] == "1318.74" and loan["payment_reference"] == "BL482"
    assert len(loan["recent_payments"]) == 3


def test_home_without_any_loan(client, sms, monkeypatch):
    login(client, sms)

    async def no_loans(borrower_id, today):
        return []

    monkeypatch.setattr(client.app.state.services.backend, "borrower_loans", no_loans)
    r = client.get("/api/portal/home")
    assert r.status_code == 200
    assert r.json()["first_name"] == "Mary" and r.json()["loan"] is None


def test_portal_needs_session(client):
    assert client.get("/api/portal/home").status_code == 401


def test_staff_cookie_does_not_open_portal(staff):
    assert staff.get("/api/portal/home").status_code == 401


def test_quote(client):
    q = client.post("/api/portal/quote", json={"amount": "5000", "months": 12}).json()
    assert q["monthly_payment"] == "472.80" and q["annual_rate"] == "24"
    assert client.post("/api/portal/quote", json={"amount": "100", "months": 12}).status_code == 422


def test_apply_creates_assessed_pending_loan(client, sms):
    login(client, sms, "71558802")  # Grace Tom already has a pending application
    r = client.post(
        "/api/portal/applications",
        json={"amount": "2000", "months": 6, "monthly_income": "6200", "existing_monthly_debt": "500"},
    )
    assert r.status_code == 409

    login(client, sms)  # Mary Kila
    r = client.post(
        "/api/portal/applications",
        json={"amount": "3000", "months": 6, "monthly_income": "5000", "existing_monthly_debt": "400"},
    )
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert "application" in sms.sent[-1][1]
    client.post("/api/staff/login", json={"username": "demo", "password": "demo"})
    pending = client.get("/api/staff/loans", params={"state": "PENDING"}).json()
    mine = next(p for p in pending if p["ref"] == ref)
    assert mine["recommendation"] in {"APPROVE", "REFER", "DECLINE"}


def test_dev_sms_inbox_only_when_enabled(client):
    assert client.get("/api/dev/sms/70123344").status_code == 404


def test_dev_sms_inbox_never_with_fineract():
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(backend="fineract", session_secret="s", dev_sms_inbox=True))
    assert not any(getattr(r, "path", "") == "/api/dev/sms/{phone}" for r in app.routes)
