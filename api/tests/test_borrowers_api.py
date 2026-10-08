from datetime import date

from conftest import login_staff

PDF = b"%PDF-1.4\n% test\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 20

NEW = {
    "first_name": "Kila",
    "last_name": "Morea",
    "phone": "+675 7555 1212",
    "date_of_birth": "1990-04-12",
    "gender": "female",
    "address": "Section 5, Lot 9, Tokarara, NCD",
    "national_id": "2018 4410 9921",
    "employer": "Department of Education",
    "payroll_number": "DOE-55120",
    "monthly_income": "3800.00",
    "existing_monthly_debt": "200.00",
    "bank": {"bank": "BSP", "branch": "Boroko", "account_name": "Kila Morea", "account_number": "1001 2233 4455"},
    "next_of_kin": {"name": "Ben Morea", "relationship": "Brother", "phone": "70112233"},
}


def create(staff, **changes):
    r = staff.post("/api/staff/borrowers", json={**NEW, **changes})
    assert r.status_code == 201, r.text
    return r.json()


def test_borrowers_need_staff_login(client):
    assert client.get("/api/staff/borrowers").status_code == 401


def test_search_by_name_phone_and_nid(staff):
    assert [b["name"] for b in staff.get("/api/staff/borrowers", params={"q": "wambi"}).json()] == ["Peter Wambi"]
    assert staff.get("/api/staff/borrowers", params={"q": "7123 4567"}).json()[0]["name"] == "Peter Wambi"
    assert staff.get("/api/staff/borrowers", params={"q": "2011-0488-7712"}).json()[0]["name"] == "Peter Wambi"
    assert len(staff.get("/api/staff/borrowers").json()) == 10


def test_create_borrower_and_profile(staff):
    b = create(staff)
    assert b["name"] == "Kila Morea" and b["phone"] == "75551212" and b["bank"]["bank"] == "BSP"
    p = staff.get(f"/api/staff/borrowers/{b['id']}").json()
    assert p["borrower"]["payroll_number"] == "DOE-55120" and p["loans"] == [] and p["documents"] == []
    assert p["kyc"]["complete"] is False and len(p["kyc"]["missing"]) == 4


def test_create_validation(staff):
    under_18 = date(date.today().year - 16, 1, 1).isoformat()  # never 29 February
    r = staff.post("/api/staff/borrowers", json={**NEW, "date_of_birth": under_18})
    assert r.status_code == 422 and "18" in r.text
    r = staff.post("/api/staff/borrowers", json={**NEW, "bank": {**NEW["bank"], "account_number": "abc"}})
    assert r.status_code == 422


def test_duplicate_phone_or_nid_refused(staff):
    assert staff.post("/api/staff/borrowers", json={**NEW, "phone": "7012 3344"}).status_code == 409
    r = staff.post("/api/staff/borrowers", json={**NEW, "national_id": "2009-1182-4410"})
    assert r.status_code == 409 and "Mary Kila" in r.json()["detail"]


def test_update_borrower(staff):
    b = create(staff)
    r = staff.put(f"/api/staff/borrowers/{b['id']}", json={**NEW, "address": "Lot 1, Hohola, NCD"})
    assert r.status_code == 200 and r.json()["address"] == "Lot 1, Hohola, NCD"


def test_upload_list_and_download_documents(staff):
    b = create(staff)
    r = staff.post(
        f"/api/staff/borrowers/{b['id']}/documents",
        data={"kind": "payslip"},
        files={"file": ("../../etc/payslip sept<1>.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "payslip" and doc["file_name"] == "payslip sept_1.pdf"
    p = staff.get(f"/api/staff/borrowers/{b['id']}").json()
    assert p["kyc"]["have"] == {"payslip": 1} and len(p["kyc"]["missing"]) == 3
    d = staff.get(f"/api/staff/borrowers/{b['id']}/documents/{doc['id']}")
    assert d.status_code == 200 and d.content == PDF
    assert d.headers["content-disposition"].startswith("attachment;")
    assert d.headers["content-type"] == "application/pdf"


def test_upload_type_comes_from_content_not_name(staff):
    b = create(staff)
    url = f"/api/staff/borrowers/{b['id']}/documents"
    r = staff.post(url, data={"kind": "id"}, files={"file": ("id.pdf", PNG, "application/pdf")})
    assert r.status_code == 201 and r.json()["file_name"] == "id.png" and r.json()["content_type"] == "image/png"
    r = staff.post(url, data={"kind": "id"}, files={"file": ("virus.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]
    r = staff.post(url, data={"kind": "selfie"}, files={"file": ("a.pdf", PDF, "application/pdf")})
    assert r.status_code == 422


def test_upload_size_limit(staff):
    staff.app.state.services.settings.max_upload_mb = 1
    b = create(staff)
    big = PDF + b"0" * (1024 * 1024)
    r = staff.post(
        f"/api/staff/borrowers/{b['id']}/documents", data={"kind": "id"}, files={"file": ("big.pdf", big, "x")}
    )
    assert r.status_code == 422 and "too big" in r.json()["detail"]


def test_staff_application_is_assessed(staff):
    b = create(staff)
    r = staff.post(f"/api/staff/borrowers/{b['id']}/applications", json={"amount": "3000", "months": 12})
    assert r.status_code == 201, r.text
    loan = staff.get(f"/api/staff/loans/{r.json()['id']}").json()
    assert loan["state"] == "PENDING" and loan["assessment"]["recommendation"] in ("APPROVE", "REFER", "DECLINE")
    again = staff.post(f"/api/staff/borrowers/{b['id']}/applications", json={"amount": "1000", "months": 6})
    assert again.status_code == 409


def send_up(staff, loan_id, advice="APPROVE"):
    # These tests are about documents: let the credit manager send up and decide alone.
    staff.app.state.services.settings.allow_self_approval = True
    r = staff.post(f"/api/staff/loans/{loan_id}/submit", json={"recommendation": advice, "note": "Checked and ready."})
    assert r.status_code == 200, r.text
    return r.json()


def test_approval_needs_kyc_documents(staff):
    # Joyce Ilave (loan 542) has no bank statement or payroll deduction authority yet.
    r = staff.post("/api/staff/loans/542/approve", json={"amount": "6500"})
    assert r.status_code == 409
    assert "Bank statement" in r.json()["detail"] and "deduction authority" in r.json()["detail"]
    for kind in ("bank_statement", "deduction_authority"):
        up = staff.post(
            "/api/staff/borrowers/10/documents", data={"kind": kind}, files={"file": (f"{kind}.pdf", PDF, "x")}
        )
        assert up.status_code == 201
    send_up(staff, 542)
    assert staff.post("/api/staff/loans/542/approve", json={"amount": "6500"}).json()["state"] == "APPROVED"


def test_kyc_gate_can_be_turned_off(staff):
    staff.app.state.services.settings.kyc_required_for_approval = False
    staff.app.state.services.settings.review_required = False  # exercise approval independently of submission
    assert staff.post("/api/staff/loans/542/approve", json={"amount": "6500"}).status_code == 200


def test_loan_officer_can_sign_up_borrowers(client):
    login_staff(client, "officer")
    assert client.post("/api/staff/borrowers", json=NEW).status_code == 201


def test_safe_file_names():
    from app.domain.uploads import safe_file_name

    assert safe_file_name("C:\\Users\\me\\Scan 01.JPG", ".jpg") == "Scan 01.jpg"
    assert safe_file_name("", ".pdf") == "document.pdf"
    assert safe_file_name("....", ".png") == "document.png"


def test_disbursement_also_needs_kyc(staff):
    # A loan approved elsewhere (or before the check existed) can't be paid out without documents.
    staff.app.state.services.settings.kyc_required_for_approval = False
    staff.app.state.services.settings.review_required = False  # exercise approval independently of submission
    assert staff.post("/api/staff/loans/542/approve", json={"amount": "6500"}).status_code == 200
    staff.app.state.services.settings.kyc_required_for_approval = True
    r = staff.post("/api/staff/loans/542/disburse", json={"reference": "TT-1"})
    assert r.status_code == 409 and "Bank statement" in r.json()["detail"]


def test_download_header_survives_odd_file_names(staff):
    backend = staff.app.state.services.backend
    doc = backend._store_document(1, "other", 'payslip–Oct "final".pdf', "application/pdf", PDF, date.today())
    r = staff.get(f"/api/staff/borrowers/1/documents/{doc.id}")
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="') and "filename*=UTF-8''payslip%E2%80%93Oct" in cd


def test_webp_is_refused(staff):
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    r = staff.post("/api/staff/borrowers/1/documents", data={"kind": "id"}, files={"file": ("a.webp", webp, "x")})
    assert r.status_code == 422


def test_remove_wrong_upload_needs_a_reason_and_is_logged(staff):
    b = create(staff)
    url = f"/api/staff/borrowers/{b['id']}/documents"
    doc = staff.post(url, data={"kind": "payslip"}, files={"file": ("wrong.pdf", PDF, "application/pdf")}).json()
    assert staff.post(f"{url}/{doc['id']}/remove", json={"reason": ""}).status_code == 422
    r = staff.post(f"{url}/{doc['id']}/remove", json={"reason": "Wrong   person's payslip"})
    assert r.status_code == 204
    p = staff.get(f"/api/staff/borrowers/{b['id']}").json()
    assert p["documents"] == [] and p["kyc"]["have"] == {}
    assert p["notes"][0]["text"] == "Removed Latest 3 payslips: wrong.pdf. Reason: Wrong person's payslip"
    assert staff.post(f"{url}/{doc['id']}/remove", json={"reason": "again"}).status_code == 404


def test_documents_behind_an_approval_stay_on_file(staff):
    p = staff.get("/api/staff/borrowers/1").json()  # Mary Kila has an active loan
    assert any(lo["state"] == "ACTIVE" for lo in p["loans"])
    doc = p["documents"][0]
    r = staff.post(f"/api/staff/borrowers/1/documents/{doc['id']}/remove", json={"reason": "tidy up"})
    assert r.status_code == 409 and "supported the approval" in r.json()["detail"]
