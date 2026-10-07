"""After approval: SMS to the borrower, contact log, signed agreement, then pay-out."""

import re

SIGNED = {"file": ("signed agreement.pdf", b"%PDF-1.4 signed", "application/pdf")}


def approve_peter(staff):
    r = staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    assert r.status_code == 200 and r.json()["state"] == "APPROVED"


def test_approval_texts_the_borrower_and_logs_it(staff, sms):
    approve_peter(staff)
    to, text = sms.sent[-1]
    assert to == "71234567" and "LN-000536" in text and "sign" in text
    p = staff.get("/api/staff/loans/536/payout").json()
    assert len(p["borrower_told"]) == 1 and p["borrower_told"][0]["text"].startswith("SMS sent to borrower")
    assert p["ready"] is False and "signed loan agreement" in p["missing"][0]
    assert p["bank"]["bank"] == "Kina Bank"


def test_send_again_and_log_a_phone_call(staff, sms):
    approve_peter(staff)
    before = len(sms.sent)
    r = staff.post("/api/staff/loans/536/contact", json={"channel": "sms"})
    assert r.status_code == 201 and len(sms.sent) == before + 1
    r = staff.post("/api/staff/loans/536/contact", json={"channel": "phone", "note": "Coming Friday 10am"})
    assert r.status_code == 201 and len(sms.sent) == before + 1
    told = staff.get("/api/staff/loans/536/payout").json()["borrower_told"]
    assert [t["text"] for t in told][-1] == "Phoned borrower: Coming Friday 10am"
    history = staff.get("/api/staff/loans/536").json()["history"]
    assert any("Coming Friday" in h["text"] for h in history)


def test_contact_only_while_approved(staff):
    assert staff.post("/api/staff/loans/536/contact", json={"channel": "phone"}).status_code == 409


def test_no_payout_without_signed_agreement(staff, sms):
    approve_peter(staff)
    r = staff.post("/api/staff/loans/536/disburse", json={"method": "bank", "reference": "TT-001"})
    assert r.status_code == 409 and "signed" in r.json()["detail"]
    up = staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED)
    assert up.status_code == 201 and up.json()["kind"] == "signed_agreement"
    p = staff.get("/api/staff/loans/536/payout").json()
    assert p["ready"] is True and p["signed_agreement"]["file_name"] == "signed agreement.pdf"
    d = staff.get(f"/api/staff/loans/536/documents/{up.json()['id']}")
    assert d.status_code == 200 and d.content == b"%PDF-1.4 signed"
    r = staff.post(
        "/api/staff/loans/536/disburse", json={"method": "bank", "reference": "TT-001", "account": "2003 1188 0091"}
    )
    assert r.status_code == 200 and r.json()["state"] == "ACTIVE"
    assert "paid out" in sms.sent[-1][1] and "TT-001" in sms.sent[-1][1]
    history = staff.get("/api/staff/loans/536").json()["history"]
    assert any(
        re.search(r"Disbursed K 13,000.00 by bank transfer into 2003 1188 0091, reference TT-001", h["text"])
        for h in history
    )


def test_signed_agreement_only_while_approved(staff):
    assert staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED).status_code == 409


def test_payout_needs_reference(staff):
    approve_peter(staff)
    staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED)
    assert staff.post("/api/staff/loans/536/disburse", json={"method": "bank"}).status_code == 422


def test_signed_agreement_rule_can_be_turned_off(staff):
    staff.app.state.services.settings.signed_agreement_required = False
    approve_peter(staff)
    r = staff.post("/api/staff/loans/536/disburse", json={"method": "cash", "reference": "CV-0091"})
    assert r.status_code == 200


def test_loan_officer_cannot_pay_out(client):
    client.post("/api/staff/login", json={"username": "officer", "password": "officer"})
    assert client.post("/api/staff/loans/536/disburse", json={"reference": "X1"}).status_code == 403
