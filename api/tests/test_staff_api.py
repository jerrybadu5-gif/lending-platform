from decimal import Decimal as D

import pytest


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "backend": "demo"}


def test_requires_login(client):
    assert client.get("/api/staff/dashboard").status_code == 401


def test_wrong_password(client):
    r = client.post("/api/staff/login", json={"username": "demo", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Username or password is wrong."


def test_session_cookie_is_httponly_and_strict(client):
    r = client.post("/api/staff/login", json={"username": "demo", "password": "demo"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    # The cookie carries only a signed random session id; the Fineract credential stays on the server.
    assert "demo:demo" not in r.headers["set-cookie"]
    assert "ZGVtbzpkZW1v" not in r.headers["set-cookie"]  # base64 of demo:demo


def test_logout_ends_session_on_server(staff):
    old = staff.cookies.get("mcl_staff")
    assert staff.post("/api/staff/logout").status_code in (200, 204)
    staff.cookies.set("mcl_staff", old)  # replaying the old cookie must not work
    assert staff.get("/api/staff/me").status_code == 401


def test_tampered_cookie_rejected(client):
    client.cookies.set("mcl_staff", "garbage.value.sig")
    assert client.get("/api/staff/me").status_code == 401


def test_dashboard_figures_add_up(staff):
    d = staff.get("/api/staff/dashboard").json()
    assert d["active_loans"] == 8
    assert d["pending_count"] == 5
    assert d["due_today_count"] == 3  # Mary, Samuel, Ruth
    assert D(d["due_today_amount"]) > 0
    buckets = {b["label"]: b["loans"] for b in d["arrears_buckets"]}
    assert buckets == {"1–30 days": 2, "31–60 days": 1, "61–90 days": 0, "Over 90 days": 0}
    assert D(d["arrears_total"]) == sum(D(b["amount"]) for b in d["arrears_buckets"])
    assert D("0") < D(d["par30_ratio"]) < D("1")
    assert staff.get("/api/staff/loans").headers["cache-control"] == "no-store"


def test_pending_loan_is_assessed_on_open(staff):
    loans = staff.get("/api/staff/loans", params={"state": "PENDING"}).json()
    assert {l["ref"] for l in loans} >= {"LN-000536", "LN-000542"}
    d = staff.get("/api/staff/loans/536").json()
    a = d["assessment"]
    # Peter Wambi: K 15,000 at 24% over 12 months, income 4,000, debt 360 -> DTI 44.46%, REFER
    assert a["recommendation"] == "REFER"
    assert a["dti"] == "0.4446" and a["monthly_payment"] == "1418.39"
    assert a["max_recommended_principal"] == "13113.42"
    assert d["schedule"][0]["total"] == "1418.39"
    assert any("Underwriting" in h["text"] for h in d["history"])


def test_approve_disburse_flow(staff):
    staff.get("/api/staff/loans/536")
    r = staff.post("/api/staff/loans/536/approve", json={"amount": "13000.00", "note": "Reduced to fit DTI"})
    assert r.status_code == 200 and r.json()["state"] == "APPROVED"
    assert staff.post("/api/staff/loans/536/approve", json={"amount": "13000.00"}).status_code == 409
    signed = staff.post(
        "/api/staff/loans/536/signed-agreement", files={"file": ("signed.pdf", b"%PDF-1.4 signed", "x")}
    )
    assert signed.status_code == 201
    r = staff.post("/api/staff/loans/536/disburse", json={"method": "bank", "reference": "BSP-TT-77120"})
    assert r.json()["state"] == "ACTIVE"
    d = staff.get("/api/staff/loans/536").json()
    assert d["principal"] == "13000.00" and d["state"] == "ACTIVE" and d["next_due_date"]


def test_cannot_approve_more_than_applied(staff):
    r = staff.post("/api/staff/loans/533/approve", json={"amount": "9000"})
    assert r.status_code == 422


def test_loan_officer_cannot_approve(client):
    client.post("/api/staff/login", json={"username": "officer", "password": "officer"})
    r = client.post("/api/staff/loans/533/approve", json={"amount": "8000"})
    assert r.status_code == 403


def test_reject_needs_note_and_sends_sms(staff, sms):
    assert staff.post("/api/staff/loans/542/reject", json={"note": ""}).status_code == 422
    r = staff.post("/api/staff/loans/542/reject", json={"note": "DTI too high"})
    assert r.json()["state"] == "REJECTED"
    assert sms.sent[-1][0] == "74220876"


def test_collections_views(staff):
    today = staff.get("/api/staff/collections", params={"view": "today"}).json()
    arrears = staff.get("/api/staff/collections", params={"view": "arrears"}).json()
    assert {c["borrower_name"] for c in today} == {"Mary Kila", "Samuel Kiap", "Ruth Kaupa"}
    assert [c["days_overdue"] for c in arrears] == [47, 26, 12]


def test_record_repayment_and_receipt_sms(staff, sms):
    mary = next(c for c in staff.get("/api/staff/collections").json() if c["borrower_name"] == "Mary Kila")
    assert mary["amount_due"] == "1318.74"
    d = staff.get("/api/health")  # noqa: F841
    r = staff.post(
        f"/api/staff/loans/{mary['loan_id']}/repayments",
        json={
            "amount": "1318.74",
            "method": "mobile",
            "reference": "CM8841203377",
            "received_on": staff.get("/api/staff/dashboard").json()["as_of"],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["receipt_no"].startswith("RC-")
    filed = staff.get(f"/api/staff/loans/{mary['loan_id']}/documents").json()
    assert [(d["kind"], d["file_name"]) for d in filed] == [("receipt", f"{r.json()['receipt_no']}.pdf")]
    pdf = staff.get(f"/api/staff/loans/{mary['loan_id']}/documents/{filed[0]['id']}")
    assert pdf.content.startswith(b"%PDF")
    assert "K 1,318.74" in sms.sent[-1][1]
    names = {c["borrower_name"] for c in staff.get("/api/staff/collections", params={"view": "today"}).json()}
    assert "Mary Kila" not in names


def test_repayment_validation(staff):
    today = staff.get("/api/staff/dashboard").json()["as_of"]
    r = staff.post(
        "/api/staff/loans/482/repayments",
        json={"amount": "999999", "method": "cash", "reference": "0041", "received_on": today},
    )
    assert r.status_code == 422 and "still owed" in r.json()["detail"]
    r = staff.post(
        "/api/staff/loans/482/repayments",
        json={"amount": "-5", "method": "cash", "reference": "0041", "received_on": today},
    )
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "amount"
    r = staff.post(
        "/api/staff/loans/533/repayments",
        json={"amount": "5", "method": "cash", "reference": "0041", "received_on": today},
    )
    assert r.status_code == 409


def test_unknown_loan(staff):
    assert staff.get("/api/staff/loans/99999").status_code == 404


def test_login_rate_limited(client):
    for _ in range(10):
        client.post("/api/staff/login", json={"username": "x", "password": "y"})
    assert client.post("/api/staff/login", json={"username": "x", "password": "y"}).status_code == 429


def officer(client):
    r = client.post("/api/staff/login", json={"username": "officer", "password": "officer"})
    assert r.status_code == 200
    return client


@pytest.mark.parametrize("gate", [True, False])
def test_officer_reviews_then_manager_decides(client, gate):
    client.app.state.services.settings.kyc_required_for_approval = gate
    # 538 is still with the loan officer: the credit manager can't decide it yet.
    officer(client)
    loan = client.get("/api/staff/loans/538").json()
    assert loan["review"]["stage"] == "DRAFT" and loan["review_stage"] == "DRAFT"
    assert client.post("/api/staff/loans/538/approve", json={"amount": "1200"}).status_code == 403
    assert (
        client.post("/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "short"}).status_code
        == 422
    )
    r = client.post(
        "/api/staff/loans/538/submit",
        json={"recommendation": "APPROVE", "amount": "1000", "note": "Payslips match, employer confirmed."},
    )
    assert r.status_code == 200 and r.json()["review"]["stage"] == "SUBMITTED"
    assert r.json()["review"]["officer_amount"] == "1000" and r.json()["review"]["submitted_by"] == "John Kerema"
    assert any("recommends approving K 1,000.00" in h["text"] for h in r.json()["history"])
    assert client.post("/api/staff/loans/538/return", json={"note": "Need a newer payslip"}).status_code == 403
    again = client.post("/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "Sending again now."})
    assert again.status_code == 409

    client.post("/api/staff/logout")
    client.post("/api/staff/login", json={"username": "demo", "password": "demo"})
    pending = {l["id"]: l["review_stage"] for l in client.get("/api/staff/loans", params={"state": "PENDING"}).json()}
    assert pending[538] == "SUBMITTED" and pending[542] == "DRAFT"
    r = client.post("/api/staff/loans/538/return", json={"note": "Need a newer payslip"})
    assert r.status_code == 200 and r.json()["review"]["stage"] == "RETURNED"
    assert r.json()["review"]["returned_note"] == "Need a newer payslip"
    r = client.post("/api/staff/loans/538/approve", json={"amount": "1000"})
    assert r.status_code == 409 and "hasn't sent" in r.json()["detail"]


def test_recommended_amount_cannot_exceed_application(staff):
    staff.app.state.services.settings.allow_self_approval = True
    r = staff.post(
        "/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "amount": "5000", "note": "Checked it all."}
    )
    assert r.status_code == 422


def test_review_gate_can_be_turned_off(staff):
    staff.app.state.services.settings.review_required = False
    assert staff.post("/api/staff/loans/538/approve", json={"amount": "1200"}).json()["state"] == "APPROVED"


def test_credit_manager_decides_and_does_not_send_up(staff):
    r = staff.post("/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "Checked it all myself."})
    assert r.status_code == 403 and "credit manager decides" in r.json()["detail"]
    # A one-manager branch can allow it; even then the same person can't approve what they sent up.
    staff.app.state.services.settings.allow_self_approval = True
    r = staff.post("/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "Checked it all myself."})
    assert r.json()["review"]["submitted_user"] == "demo"
    staff.app.state.services.settings.allow_self_approval = False
    r = staff.post("/api/staff/loans/538/approve", json={"amount": "1200"})
    assert r.status_code == 409 and "another credit manager" in r.json()["detail"]


def test_manager_can_decline_or_send_back_before_the_officer_review(staff):
    # 538 is still with the loan officer (DRAFT).
    r = staff.post("/api/staff/loans/538/return", json={"note": "Please get the latest payslip first"})
    assert r.status_code == 200 and r.json()["review"]["stage"] == "RETURNED"
    assert r.json()["review"]["returned_note"] == "Please get the latest payslip first"
    assert staff.post("/api/staff/loans/538/approve", json={"amount": "1200"}).status_code == 409
    r = staff.post("/api/staff/loans/538/reject", json={"note": "Too many loans elsewhere"})
    assert r.status_code == 200 and r.json()["state"] == "REJECTED"


@pytest.mark.parametrize("gate", [True, False])
def test_officer_cannot_send_up_without_documents(client, gate):
    client.app.state.services.settings.kyc_required_for_approval = gate
    officer(client)
    before = client.get("/api/staff/loans/542").json()["review"]
    # Joyce Ilave (542) has no bank statement or payroll deduction authority: neither advice can go up.
    for advice in ("APPROVE", "DECLINE"):
        r = client.post("/api/staff/loans/542/submit", json={"recommendation": advice, "note": "Checked what we have."})
        assert r.status_code == 409 and "Bank statement" in r.json()["detail"]
        assert client.get("/api/staff/loans/542").json()["review"] == before


def test_review_not_set_up_says_so(staff):
    backend = staff.app.state.services.backend
    original = backend.get_loan

    async def no_review(cred, loan_id, today):
        d = await original(cred, loan_id, today)
        return d.model_copy(update={"review": None})

    backend.get_loan = no_review
    r = staff.post("/api/staff/loans/533/approve", json={"amount": "8000"})
    assert r.status_code == 503 and "dt_loan_review" in r.json()["detail"]
    staff.app.state.services.settings.allow_self_approval = True
    r = staff.post("/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "Checked it all myself."})
    assert r.status_code == 503


def test_two_people_signed_in_in_one_browser(client):
    # Grace signs in in one tab, John in another: each tab names its person and keeps it.
    grace_login = client.post("/api/staff/login", json={"username": "demo", "password": "demo"}).json()
    john_login = client.post("/api/staff/login", json={"username": "officer", "password": "officer"}).json()
    grace = {"X-MCL-User": "demo", "X-MCL-Tab": grace_login["tab_credential"]}
    john = {"X-MCL-User": "officer", "X-MCL-Tab": john_login["tab_credential"]}
    client.headers.pop("X-MCL-User")
    client.headers.pop("X-MCL-Tab")
    assert client.get("/api/staff/me", headers=grace).json()["display_name"] == "Grace Pokana"
    assert client.get("/api/staff/me", headers=john).json()["display_name"] == "John Kerema"
    assert client.get("/api/staff/me").status_code == 401
    for forged in ({"X-MCL-User": "demo"}, {**john, "X-MCL-User": "demo"}, {**grace, "X-MCL-Tab": "wrong"}):
        assert client.get("/api/staff/me", headers=forged).status_code == 401
        assert client.post("/api/staff/logout", headers=forged).status_code == 401
    assert "tab_credential" not in client.get("/api/staff/me", headers=grace).json()
    assert client.get("/api/staff/me", headers={**grace, "X-MCL-User": "DEMO"}).status_code == 200
    assert client.post("/api/staff/loans/533/approve", json={"amount": "8000"}, headers=john).status_code == 403
    # John signs out in his tab; Grace stays signed in in hers.
    client.post("/api/staff/logout", headers=john)
    assert client.get("/api/staff/me", headers=john).status_code == 401
    assert client.get("/api/staff/me", headers=grace).status_code == 200
    # A tab can't borrow another person's session by naming them.
    assert client.get("/api/staff/me", headers={"X-MCL-User": "someone"}).status_code == 401


def test_successful_sign_ins_do_not_lock_anyone_out(client):
    for _ in range(12):
        assert client.post("/api/staff/login", json={"username": "demo", "password": "demo"}).status_code == 200


@pytest.mark.parametrize("enabled", [True, False])
def test_self_approval_setting_and_decision(staff, enabled):
    settings = staff.app.state.services.settings
    settings.allow_self_approval = True
    assert (
        staff.post(
            "/api/staff/loans/538/submit", json={"recommendation": "APPROVE", "note": "Checked all documents myself."}
        ).status_code
        == 200
    )
    settings.allow_self_approval = enabled
    assert staff.get("/api/staff/me").json()["allow_self_approval"] is enabled
    assert staff.post("/api/staff/loans/538/approve", json={"amount": "1200"}).status_code == (200 if enabled else 409)


def test_expired_and_tampered_staff_sessions(staff):
    from app.security import staff_cookie_for

    cookie = staff_cookie_for("demo")
    original = staff.cookies.get(cookie)
    staff.cookies.set(cookie, "tampered", domain="testserver.local", path="/")
    assert staff.get("/api/staff/me").status_code == 401
    assert staff.post("/api/staff/logout").status_code == 401
    staff.cookies.set(cookie, original, domain="testserver.local", path="/")
    store = staff.app.state.services.sessions
    for sid, (_, data) in list(store._items.items()):
        store._items[sid] = (0, data)
    assert staff.get("/api/staff/me").status_code == 401
    assert staff.post("/api/staff/logout").status_code == 401


def test_staff_cookie_names_bind_the_complete_canonical_username():
    from app.security import staff_cookie_for

    for left, right in [("a.b", "ab"), ("a" * 32 + "x", "a" * 32 + "y"), ("!!!", "???")]:
        assert staff_cookie_for(left) != staff_cookie_for(right)
    assert staff_cookie_for(" Demo ") == staff_cookie_for("demo")
    assert staff_cookie_for("!!!") == staff_cookie_for(" !!! ")


def test_staff_lookup_rejects_wrong_session_type_and_username(staff):
    from app.security import PortalSession

    store = staff.app.state.services.sessions
    sid, (expiry, session) = next(iter(store._items.items()))
    session.username = "officer"
    assert staff.get("/api/staff/me").status_code == 401
    assert staff.post("/api/staff/logout").status_code == 401
    store._items[sid] = (expiry, PortalSession(borrower_id=1, first_name="Mary"))
    assert staff.get("/api/staff/me").status_code == 401
    assert staff.post("/api/staff/logout").status_code == 401
    assert sid in store._items
