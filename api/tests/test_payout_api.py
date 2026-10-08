"""After approval: SMS to the borrower, contact log, signed agreement, then pay-out."""

import re

from conftest import login_staff

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
    login_staff(client, "officer")
    assert client.post("/api/staff/loans/536/disburse", json={"reference": "X1"}).status_code == 403


def test_no_sms_while_approval_waits_for_second_approver(staff, sms, monkeypatch):
    from app.domain.models import ActionResult

    async def pending(cred, loan_id, body, today):
        return ActionResult(
            loan_id=loan_id, state="PENDING", message="Approval saved. A second approver must confirm it."
        )

    monkeypatch.setattr(staff.app.state.services.backend, "approve", pending)
    before = len(sms.sent)
    r = staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    assert r.json()["state"] == "PENDING" and len(sms.sent) == before


def test_pending_payout_is_not_announced_or_repeated(staff, sms, monkeypatch):
    from app.domain.models import ActionResult

    approve_peter(staff)
    staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED)

    async def pending(cred, loan_id, body, today):
        return ActionResult(
            loan_id=loan_id, state="APPROVED", message="Disbursement saved. A second approver must confirm it."
        )

    monkeypatch.setattr(staff.app.state.services.backend, "disburse", pending)
    before = len(sms.sent)
    r = staff.post("/api/staff/loans/536/disburse", json={"reference": "TT-5"})
    assert r.json()["state"] == "APPROVED" and len(sms.sent) == before  # no "paid out" SMS yet
    p = staff.get("/api/staff/loans/536/payout").json()
    assert p["payout_pending"] is True and p["ready"] is False
    again = staff.post("/api/staff/loans/536/disburse", json={"reference": "TT-5"})
    assert again.status_code == 409 and "second approver" in again.json()["detail"]


def test_sms_that_went_is_not_reported_as_failed_when_the_note_fails(staff, sms, monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("Fineract 500")

    monkeypatch.setattr(staff.app.state.services.backend, "add_loan_note", broken)
    r = staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    assert r.status_code == 200 and "didn't go" not in r.json()["message"] and "LN-000536" in sms.sent[-1][1]
    up = staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED)
    assert up.status_code == 201  # stored, so not reported as failed (a retry would upload it twice)


def test_resend_is_limited(staff):
    approve_peter(staff)
    assert staff.post("/api/staff/loans/536/contact", json={"channel": "sms"}).status_code == 201
    assert staff.post("/api/staff/loans/536/contact", json={"channel": "sms"}).status_code == 201
    r = staff.post("/api/staff/loans/536/contact", json={"channel": "sms"})
    assert r.status_code == 429 and "10 minutes" in r.json()["detail"]


def test_without_sms_provider_staff_are_told_to_phone(staff, sms):
    staff.app.state.services.settings.backend = "fineract"  # sample data, but act as if live without a provider
    r = staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    assert "phone the borrower" in r.json()["message"]
    p = staff.get("/api/staff/loans/536/payout").json()
    assert p["sms_delivers"] is False and p["told_done"] is False
    assert p["borrower_told"][0]["text"].startswith("SMS not delivered")
    staff.post("/api/staff/loans/536/contact", json={"channel": "phone", "note": "Coming Monday"})
    assert staff.get("/api/staff/loans/536/payout").json()["told_done"] is True


def test_loan_officer_can_log_contact_and_upload_signed_copy(client, staff):
    approve_peter(staff)
    staff.post("/api/staff/logout")
    login_staff(client, "officer")
    assert client.post("/api/staff/loans/536/contact", json={"channel": "phone", "note": "ok"}).status_code == 201
    assert client.post("/api/staff/loans/536/signed-agreement", files=SIGNED).status_code == 201


def test_signed_agreement_cannot_be_filed_on_the_borrower(staff):
    r = staff.post("/api/staff/borrowers/8/documents", data={"kind": "signed_agreement"}, files=SIGNED)
    assert r.status_code == 422


def test_wrong_signed_agreement_can_be_removed_before_payout(staff):
    approve_peter(staff)
    up = staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED).json()
    url = f"/api/staff/loans/536/documents/{up['id']}/remove"
    assert staff.post(url, json={}).status_code == 422
    assert staff.post(url, json={"reason": "Page 2 missing"}).status_code == 204
    p = staff.get("/api/staff/loans/536/payout").json()
    assert p["signed_agreement"] is None and p["ready"] is False
    history = staff.get("/api/staff/loans/536").json()["history"]
    assert any(h["text"].endswith("Reason: Page 2 missing") for h in history)


def test_signed_agreement_stays_once_payout_is_waiting_for_a_checker(staff):
    approve_peter(staff)
    up = staff.post("/api/staff/loans/536/signed-agreement", files=SIGNED).json()
    backend = staff.app.state.services.backend
    from datetime import date

    from app.routers.payout import PAYOUT_PENDING_MARK

    run_note = backend.add_loan_note("demo:demo", 536, f"{PAYOUT_PENDING_MARK}: TT-1", date.today())
    import asyncio

    asyncio.run(run_note)
    r = staff.post(f"/api/staff/loans/536/documents/{up['id']}/remove", json={"reason": "wrong"})
    assert r.status_code == 409


def test_only_an_approved_loan_is_paid_out(staff):
    staff.app.state.services.settings.signed_agreement_required = False
    r = staff.post("/api/staff/loans/533/disburse", json={"method": "cash", "reference": "CV-1"})
    assert r.status_code == 409 and "approved" in r.json()["detail"]
