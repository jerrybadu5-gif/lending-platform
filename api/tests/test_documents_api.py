import pytest
from reportlab import rl_config


@pytest.fixture(autouse=True)
def readable_pdfs(monkeypatch):
    # Uncompressed page streams, so the tests can look for text in the PDF bytes.
    monkeypatch.setattr(rl_config, "pageCompression", 0)


def text_in(pdf: bytes, phrase: str) -> bool:
    return f"({phrase}".encode() in pdf or phrase.encode() in pdf


def test_schedule_pdf(staff):
    r = staff.get("/api/staff/loans/482/schedule.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and 'filename="LN-000482-schedule.pdf"' in r.headers["content-disposition"]
    assert text_in(r.content, "Repayment schedule") and text_in(r.content, "BL482")


def test_agreement_only_after_approval_and_marked_draft(staff):
    assert staff.get("/api/staff/loans/536/agreement.pdf").status_code == 409
    staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    r = staff.get("/api/staff/loans/536/agreement.pdf")
    assert r.status_code == 200
    assert text_in(r.content, "Loan agreement") and text_in(r.content, "Peter Wambi")
    assert text_in(r.content, "K 13,000.00") and text_in(r.content, "DRAFT TEMPLATE")
    assert text_in(r.content, "Kina Bank")


def test_agreement_without_draft_note_once_reviewed(staff):
    staff.app.state.services.settings.agreement_reviewed = True
    r = staff.get("/api/staff/loans/482/agreement.pdf")
    assert r.status_code == 200 and not text_in(r.content, "DRAFT TEMPLATE")


def test_statement_and_receipt(staff):
    s = staff.get("/api/staff/loans/482/statement.pdf")
    assert s.status_code == 200 and text_in(s.content, "Loan statement")
    loan = staff.get("/api/staff/loans/482").json()
    pay = loan["payments"][0]
    r = staff.get(f"/api/staff/loans/482/payments/{pay['id']}/receipt.pdf")
    assert r.status_code == 200 and text_in(r.content, "Payment receipt") and text_in(r.content, pay["reference"])
    assert staff.get("/api/staff/loans/482/payments/1/receipt.pdf").status_code == 404
    assert staff.get("/api/staff/loans/536/statement.pdf").status_code == 409


def test_documents_need_login(client):
    assert client.get("/api/staff/loans/482/schedule.pdf").status_code == 401
    assert client.get("/api/portal/loan/statement.pdf").status_code == 401


def test_portal_borrower_gets_own_statement(client, sms):
    from test_portal_api import login

    login(client, sms)
    r = client.get("/api/portal/loan/statement.pdf")
    assert r.status_code == 200 and text_in(r.content, "Mary Kila") and text_in(r.content, "LN-000482")
    assert client.get("/api/portal/loan/schedule.pdf").status_code == 200


def test_agreement_is_dated_on_approval_not_reprint(staff):
    staff.post("/api/staff/loans/536/approve", json={"amount": "13000"})
    loan = staff.get("/api/staff/loans/536").json()
    assert loan["approved_on"]
    day = loan["approved_on"]
    dmy = f"{day[8:10]}/{day[5:7]}/{day[0:4]}"
    assert text_in(staff.get("/api/staff/loans/536/agreement.pdf").content, f"dated {dmy}")
