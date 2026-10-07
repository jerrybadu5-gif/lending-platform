"""Fineract back end against a mocked Fineract API (payload shapes from Fineract 1.15).

These prove the mapping and the calls we make; they are not a substitute for a run
against a real Fineract server (see docs/MCLENDER.md, "Checking against Fineract").
"""

import asyncio
import json
from datetime import date
from decimal import Decimal as D

import httpx
import pytest
import respx

from app.backends.base import AuthFailed, BackendError
from app.backends.fineract import FineractBackend, fdate, repayments_per_year
from app.config import Settings
from app.domain.models import ApproveIn, RejectIn, RepaymentIn

BASE = "http://fin.test/fineract-provider/api/v1"
TODAY = date(2026, 10, 6)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fb():
    s = Settings(
        backend="fineract",
        fineract_url="http://fin.test",
        session_secret="x",
        fineract_portal_user="portal",
        fineract_portal_password="pw",
    )
    return FineractBackend(s)


LOAN = {
    "id": 536,
    "accountNo": "000000536",
    "clientId": 8,
    "clientName": "Peter Wambi",
    "loanProductName": "Personal loan",
    "principal": 15000.0,
    "annualInterestRate": 24.0,
    "numberOfRepayments": 12,
    "status": {"id": 100, "code": "loanStatusType.submitted.and.pending.approval"},
    "interestType": {"id": 0},
    "timeline": {"submittedOnDate": [2026, 10, 5], "submittedByUsername": "jkerema"},
    "summary": None,
    "repaymentSchedule": {
        "periods": [
            {"dueDate": [2026, 10, 5], "principalDisbursed": 15000},
            {
                "period": 1,
                "dueDate": [2026, 11, 5],
                "principalDue": 1118.39,
                "interestDue": 300.0,
                "feeChargesDue": 0,
                "penaltyChargesDue": 0,
                "totalDueForPeriod": 1418.39,
                "totalPaidForPeriod": 0,
                "principalLoanBalanceOutstanding": 13881.61,
                "complete": False,
            },
        ]
    },
    "transactions": [],
}


def test_fdate():
    assert fdate([2026, 10, 6]) == TODAY and fdate("2026-10-06") == TODAY and fdate(None) is None


@respx.mock
def test_login_maps_user_and_key(fb):
    route = respx.post(f"{BASE}/authentication").respond(
        200,
        json={
            "username": "gpokana",
            "base64EncodedAuthenticationKey": "Z3Bva2FuYTpwdw==",
            "authenticated": True,
            "staffDisplayName": "Pokana, Grace",
            "roles": [{"name": "Credit manager"}],
        },
    )
    user, key = run(fb.authenticate("gpokana", "pw"))
    assert key == "Z3Bva2FuYTpwdw==" and user.roles == ["Credit manager"] and user.display_name == "Pokana, Grace"
    assert route.calls[0].request.headers["Fineract-Platform-TenantId"] == "default"


@respx.mock
def test_login_failure(fb):
    respx.post(f"{BASE}/authentication").respond(401, json={"defaultUserMessage": "Unauthenticated"})
    with pytest.raises(AuthFailed):
        run(fb.authenticate("x", "y"))


@respx.mock
def test_get_loan_maps_everything(fb):
    respx.get(f"{BASE}/loans/536").respond(200, json=LOAN)
    respx.get(f"{BASE}/clients/8").respond(
        200, json={"id": 8, "displayName": "Peter Wambi", "mobileNo": "+675 7123 4567"}
    )
    respx.get(f"{BASE}/clients/8/identifiers").respond(
        200,
        json=[
            {"documentType": {"name": "Passport"}, "documentKey": "P1234567"},
            {"documentType": {"name": "National ID (NID)"}, "documentKey": "2011 0488 7712"},
        ],
    )
    respx.get(f"{BASE}/datatables/dt_borrower_financials/8").respond(
        200,
        json=[
            {
                "monthly_income": 4000,
                "existing_monthly_debt": 360,
                "credit_score": 700,
                "income_source": "Lae Port Services",
            }
        ],
    )
    respx.get(f"{BASE}/datatables/dt_loan_assessment/536").respond(200, json=[])
    respx.get(f"{BASE}/datatables/dt_loan_review").respond(200, json={"registeredTableName": "dt_loan_review"})
    respx.get(f"{BASE}/datatables/dt_loan_review/536").respond(
        200,
        json=[
            {
                "stage": "SUBMITTED",
                "officer_recommendation": "APPROVE",
                "officer_amount": 13000,
                "officer_note": "Checked",
                "submitted_by": "John Kerema",
                "submitted_on": [2026, 10, 5],
            }
        ],
    )
    respx.get(f"{BASE}/loans/536/notes").respond(
        200, json=[{"note": "Phoned borrower: coming Friday", "createdByUsername": "grace", "createdOn": [2026, 10, 5]}]
    )
    respx.get(f"{BASE}/datatables/dt_borrower_profile/8").respond(
        200,
        json=[
            {
                "address": "Gerehu Stage 2",
                "employer": "Lae Port Services Ltd",
                "payroll_number": "LPS-0451",
                "bank_name": "Kina Bank",
                "bank_account_name": "Peter Wambi",
                "bank_account_number": "2003 1188 0091",
                "nok_name": "Rose Wambi",
                "nok_relationship": "Wife",
                "nok_phone": "71440023",
            }
        ],
    )
    d = run(fb.get_loan("KEY", 536, TODAY))
    assert d.borrower.employer == "Lae Port Services Ltd" and d.borrower.payroll_number == "LPS-0451"
    assert d.borrower.bank and d.borrower.bank.bank == "Kina Bank"
    assert d.borrower.next_of_kin and d.borrower.next_of_kin.name == "Rose Wambi"
    assert d.ref == "LN-000000536" and d.state == "PENDING" and d.borrower.phone == "71234567"
    assert d.borrower.monthly_income == D("4000") and d.borrower.credit_score == 700
    assert d.schedule[0].total == D("1418.39") and d.assessment is None
    assert d.review_stage == "SUBMITTED" and d.review and d.review.officer_amount == D("13000")
    assert d.review.submitted_on == date(2026, 10, 5) and d.review.submitted_by == "John Kerema"
    assert d.history[-1].text == "Application submitted"  # newest first; notes merged in by date
    assert d.history[0].text == "Phoned borrower: coming Friday" and d.history[0].who == "grace"


@respx.mock
def test_staff_credential_is_forwarded(fb):
    route = respx.get(f"{BASE}/datatables/dt_loan_assessment/536").respond(200, json=[])
    run(fb._datatable("STAFFKEY", "dt_loan_assessment", 536))
    assert route.calls[0].request.headers["Authorization"] == "Basic STAFFKEY"


@respx.mock
def test_approve_and_maker_checker(fb):
    route = respx.post(f"{BASE}/loans/536", params={"command": "approve"}).mock(
        side_effect=[
            httpx.Response(200, json={"loanId": 536, "resourceId": 536, "changes": {"status": {"id": 200}}}),
            httpx.Response(200, json={"commandId": 91, "rollbackTransaction": False}),
        ]
    )
    r1 = run(fb.approve("K", 536, ApproveIn(amount=D("13000")), TODAY))
    sent = json.loads(route.calls[0].request.content)
    assert sent["approvedLoanAmount"] == "13000" and sent["approvedOnDate"] == "2026-10-06" and sent["locale"] == "en"
    assert r1.state == "APPROVED"
    r2 = run(fb.approve("K", 536, ApproveIn(amount=D("13000")), TODAY))
    assert r2.state == "PENDING" and "second approver" in r2.message


@respx.mock
def test_fineract_error_message_is_passed_on(fb):
    respx.post(f"{BASE}/loans/536", params={"command": "reject"}).respond(
        400,
        json={
            "defaultUserMessage": "Validation errors exist.",
            "errors": [{"defaultUserMessage": "The date on which a loan is rejected cannot be before submittal."}],
        },
    )
    from app.domain.models import RejectIn

    with pytest.raises(BackendError) as e:
        run(fb.reject("K", 536, RejectIn(note="DTI too high"), TODAY))
    assert "cannot be before submittal" in e.value.message and e.value.status == 422


@respx.mock
def test_repayment_needs_payment_type(fb):
    respx.get(f"{BASE}/paymenttypes").respond(200, json=[{"id": 1, "name": "Cash"}])
    with pytest.raises(BackendError) as e:
        run(
            fb.record_repayment(
                "K", 536, RepaymentIn(amount=D("10"), method="mobile", reference="CM1", received_on=TODAY), TODAY
            )
        )
    assert "Mobile Money" in e.value.message


@respx.mock
def test_find_borrower_by_phone_checks_exact_number(fb):
    respx.get(f"{BASE}/search").respond(
        200, json=[{"entityId": 3, "entityType": "CLIENT"}, {"entityId": 8, "entityType": "CLIENT"}]
    )
    respx.get(f"{BASE}/clients/3").respond(200, json={"id": 3, "displayName": "Other", "mobileNo": "71234560"})
    respx.get(f"{BASE}/clients/8").respond(200, json={"id": 8, "displayName": "Peter Wambi", "mobileNo": "67571234567"})
    b = run(fb.find_borrower_by_phone("7123 4567"))
    assert b is not None and b.id == 8
    portal_auth = respx.calls[0].request.headers["Authorization"]
    assert portal_auth == "Basic cG9ydGFsOnB3"  # portal:pw, never a staff key


@respx.mock
def test_reject_waits_for_second_approver(fb):
    respx.post(f"{BASE}/loans/536", params={"command": "reject"}).respond(200, json={"commandId": 92})
    r = run(fb.reject("K", 536, RejectIn(note="Income not verified"), TODAY))
    assert r.state == "PENDING" and "second approver" in r.message


def test_repayment_frequency():
    assert repayments_per_year({}) == 12
    assert repayments_per_year({"repaymentFrequencyType": {"id": 1}, "repaymentEvery": 2}) == 26
    assert repayments_per_year({"repaymentFrequencyType": {"id": 1}, "repaymentEvery": 1}) == 52
    assert repayments_per_year({"repaymentFrequencyType": {"id": 2}, "repaymentEvery": 1}) == 12


def test_console_sms_masks_outside_demo(caplog):
    from app.sms import ConsoleSms

    with caplog.at_level("INFO", logger="mclender.sms"):
        run(ConsoleSms(reveal=False).send("70123344", "Your code is 123456"))
    assert "123456" not in caplog.text and "70123344" not in caplog.text and "*****344" in caplog.text


@respx.mock
def test_create_borrower_writes_client_identifier_and_tables(fb):
    from app.domain.models import BorrowerIn

    respx.get(f"{BASE}/codes").respond(
        200, json=[{"id": 4, "name": "Gender"}, {"id": 1, "name": "Customer Identifier"}]
    )
    respx.get(f"{BASE}/codes/4/codevalues").respond(
        200, json=[{"id": 21, "name": "Female"}, {"id": 22, "name": "Male"}]
    )
    respx.get(f"{BASE}/codes/1/codevalues").respond(200, json=[{"id": 31, "name": "National ID (NID)"}])
    respx.get(f"{BASE}/search").respond(200, json=[])
    client = respx.post(f"{BASE}/clients").respond(200, json={"clientId": 77, "resourceId": 77})
    ident = respx.post(f"{BASE}/clients/77/identifiers").respond(200, json={"resourceId": 5})
    respx.get(f"{BASE}/datatables/dt_borrower_profile/77").respond(200, json=[])
    profile = respx.post(f"{BASE}/datatables/dt_borrower_profile/77").respond(200, json={})
    respx.get(f"{BASE}/datatables/dt_borrower_financials/77").respond(200, json=[])
    fin = respx.post(f"{BASE}/datatables/dt_borrower_financials/77").respond(200, json={})
    respx.get(f"{BASE}/clients/77").respond(
        200, json={"id": 77, "displayName": "Kila Morea", "mobileNo": "75551212", "gender": {"name": "Female"}}
    )
    respx.get(f"{BASE}/clients/77/identifiers").respond(
        200, json=[{"documentType": {"id": 31, "name": "National ID (NID)"}, "documentKey": "2018 4410 9921"}]
    )
    body = BorrowerIn(
        first_name="Kila",
        last_name="Morea",
        phone="+675 7555 1212",
        date_of_birth=date(1990, 4, 12),
        gender="female",
        address="Tokarara",
        national_id="2018 4410 9921",
        employer="Dept of Education",
        payroll_number="DOE-55120",
        monthly_income=D("3800"),
    )
    b = run(fb.create_borrower("K", body, TODAY))
    sent = json.loads(client.calls[0].request.content)
    assert sent["mobileNo"] == "75551212" and sent["genderId"] == 21 and sent["dateOfBirth"] == "1990-04-12"
    assert sent["activationDate"] == "2026-10-06" and sent["legalFormId"] == 1
    assert json.loads(ident.calls[0].request.content)["documentTypeId"] == 31
    assert json.loads(profile.calls[0].request.content)["payroll_number"] == "DOE-55120"
    assert json.loads(fin.calls[0].request.content)["monthly_income"] == "3800"
    assert b.national_id == "2018 4410 9921" and b.gender == "female"


@respx.mock
def test_missing_nid_type_explains_the_fix(fb):
    from app.domain.models import BorrowerIn

    respx.get(f"{BASE}/codes").respond(200, json=[{"id": 1, "name": "Customer Identifier"}])
    respx.get(f"{BASE}/codes/1/codevalues").respond(200, json=[{"id": 30, "name": "Passport"}])
    respx.get(f"{BASE}/search").respond(200, json=[])
    created = respx.post(f"{BASE}/clients").respond(200, json={"clientId": 78})
    body = BorrowerIn(
        first_name="A",
        last_name="B",
        phone="75550000",
        date_of_birth=date(1990, 1, 1),
        gender="male",
        address="Hohola",
        national_id="1234 5678",
    )
    with pytest.raises(BackendError) as e:
        run(fb.create_borrower("K", body, TODAY))
    assert "National ID" in e.value.message and not created.called  # nothing half-created


@respx.mock
def test_documents_upload_list_download(fb):
    up = respx.post(f"{BASE}/clients/8/documents").respond(200, json={"resourceId": 41})
    d = run(fb.add_document("K", 8, "payslip", "slip.pdf", "application/pdf", b"%PDF-1.4", TODAY))
    req = up.calls[0].request
    assert d.id == 41 and b'name="name"\r\n\r\npayslip' in req.content and b'filename="slip.pdf"' in req.content
    respx.get(f"{BASE}/clients/8/documents").respond(
        200,
        json=[
            {
                "id": 41,
                "name": "payslip",
                "fileName": "slip.pdf",
                "size": 8,
                "type": "application/pdf",
                "description": "McLender upload 2026-10-06",
            },
            {"id": 7, "name": "Old scan", "fileName": "x.jpg", "size": 3, "type": "image/jpeg"},
        ],
    )
    docs = run(fb.list_documents("K", 8))
    assert [(x.id, x.kind) for x in docs] == [(41, "payslip"), (7, "other")] and docs[0].uploaded_on == TODAY
    respx.get(f"{BASE}/clients/8/documents/41").respond(
        200, json={"id": 41, "name": "payslip", "fileName": "slip.pdf", "type": "application/pdf"}
    )
    respx.get(f"{BASE}/clients/8/documents/41/attachment").respond(200, content=b"%PDF-1.4")
    meta, data = run(fb.get_document("K", 8, 41))
    assert data == b"%PDF-1.4" and meta.file_name == "slip.pdf"


CLIENTS = {
    "totalFilteredRecords": 3,
    "pageItems": [
        {"id": 1, "displayName": "Mary Kila", "mobileNo": "70123344"},
        {"id": 8, "displayName": "Peter Wambi", "mobileNo": "71234567"},
        {"id": 9, "displayName": "Kila Morea", "mobileNo": "75551212"},
    ],
}


@respx.mock
def test_search_ignores_case_and_word_order(fb):
    listing = respx.get(f"{BASE}/clients").respond(200, json=CLIENTS)
    respx.get(f"{BASE}/search").respond(403, json={"defaultUserMessage": "no"})  # an NID search failing is fine
    assert [h.name for h in run(fb.search_borrowers("K", "WAMBI"))] == ["Peter Wambi"]
    assert [h.name for h in run(fb.search_borrowers("K", "kila mary"))] == ["Mary Kila"]
    assert [h.name for h in run(fb.search_borrowers("K", "kila"))] == ["Kila Morea", "Mary Kila"]
    assert [h.name for h in run(fb.search_borrowers("K", "Petr"))] == ["Peter Wambi"]  # a typo
    assert [h.name for h in run(fb.search_borrowers("K", "7012 3344"))] == ["Mary Kila"]
    assert listing.call_count == 1  # the client list is kept for a minute


@respx.mock
def test_search_finds_nid_however_it_is_typed(fb):
    respx.get(f"{BASE}/clients").respond(200, json=CLIENTS)
    nid = respx.get(f"{BASE}/search").respond(
        200,
        json=[
            {"entityType": "CLIENTIDENTIFIER", "entityName": "2011 0488 7712", "parentId": 8, "parentName": "PW"},
            {"entityType": "CLIENTIDENTIFIER", "entityName": "2009 7712", "parentId": 1, "parentName": "MK"},
        ],
    )
    hits = run(fb.search_borrowers("K", "2011-0488-7712"))
    assert [(h.id, h.national_id) for h in hits] == [(8, "2011 0488 7712")]
    # A name and part of an NID must both match the same person.
    assert [h.name for h in run(fb.search_borrowers("K", "mary 7712"))] == ["Mary Kila"]
    assert run(fb.search_borrowers("K", "wambi 9999")) == []
    assert nid.calls[0].request.url.params["query"] == "2011"


@respx.mock
def test_document_download_does_not_ask_for_json(fb):
    respx.get(f"{BASE}/clients/8/documents/41").respond(200, json={"id": 41, "name": "id", "fileName": "a.pdf"})
    route = respx.get(f"{BASE}/clients/8/documents/41/attachment").respond(200, content=b"%PDF")
    run(fb.get_document("K", 8, 41))
    assert route.calls[0].request.headers["Accept"] == "*/*"


@respx.mock
def test_duplicate_phone_or_nid_is_refused_before_anything_is_created(fb):
    from app.domain.models import BorrowerIn

    body = BorrowerIn(
        first_name="Kila",
        last_name="Morea",
        phone="7012 3344",
        date_of_birth=date(1990, 4, 12),
        gender="female",
        address="Tokarara",
        national_id="2009 1182 4410",
    )
    created = respx.post(f"{BASE}/clients").respond(200, json={"clientId": 99})
    respx.get(f"{BASE}/search", params={"resource": "clients"}).respond(
        200, json=[{"entityId": 1, "entityType": "CLIENT", "entityName": "Mary Kila"}]
    )
    respx.get(f"{BASE}/clients/1").respond(200, json={"id": 1, "displayName": "Mary Kila", "mobileNo": "70123344"})
    with pytest.raises(BackendError) as e:
        run(fb.create_borrower("K", body, TODAY))
    assert e.value.status == 409 and "Mary Kila" in e.value.message and not created.called

    respx.get(f"{BASE}/search", params={"resource": "clients"}).respond(200, json=[])
    respx.get(f"{BASE}/search", params={"resource": "clientIdentifiers"}).respond(
        200,
        json=[
            {
                "entityId": 3,
                "entityType": "CLIENTIDENTIFIER",
                "entityName": "2009-1182-4410",
                "parentId": 1,
                "parentName": "Mary Kila",
            }
        ],
    )
    with pytest.raises(BackendError) as e:
        run(fb.create_borrower("K", body.model_copy(update={"phone": "75550000"}), TODAY))
    assert "NID" in e.value.message and not created.called


@respx.mock
def test_clearing_bank_details_sends_nulls(fb):
    respx.get(f"{BASE}/datatables/dt_borrower_profile/8").respond(200, json=[{"bank_name": "BSP"}])
    put = respx.put(f"{BASE}/datatables/dt_borrower_profile/8").respond(200, json={})
    run(fb._upsert("K", "dt_borrower_profile", 8, {"bank_name": None, "address": "Hohola"}, clear_empty=True))
    sent = json.loads(put.calls[0].request.content)
    assert sent["bank_name"] is None and sent["address"] == "Hohola"


@respx.mock
def test_staff_application_refused_when_one_is_waiting(fb):
    from app.domain.models import ApplicationIn

    respx.get(f"{BASE}/clients/8/accounts").respond(200, json={"loanAccounts": [{"id": 536, "status": {"id": 100}}]})
    with pytest.raises(BackendError) as e:
        run(fb.create_application("K", 8, ApplicationIn(amount=D("1000"), months=6), TODAY))
    assert e.value.status == 409


@respx.mock
def test_disburse_sends_payment_details(fb):
    from app.domain.models import DisburseIn

    respx.get(f"{BASE}/paymenttypes").respond(200, json=[{"id": 2, "name": "Bank Transfer"}])
    route = respx.post(f"{BASE}/loans/536", params={"command": "disburse"}).respond(
        200, json={"loanId": 536, "changes": {"status": {"id": 300}}}
    )
    r = run(fb.disburse("K", 536, DisburseIn(method="bank", reference="TT-9", account="2003 1188"), TODAY))
    sent = json.loads(route.calls[0].request.content)
    assert r.state == "ACTIVE" and sent["paymentTypeId"] == 2 and sent["receiptNumber"] == "TT-9"
    assert sent["accountNumber"] == "2003 1188" and sent["actualDisbursementDate"] == "2026-10-06"


@respx.mock
def test_loan_notes_and_signed_agreement(fb):
    note = respx.post(f"{BASE}/loans/536/notes").respond(200, json={"resourceId": 1})
    run(fb.add_loan_note("K", 536, "Phoned borrower", TODAY))
    assert json.loads(note.calls[0].request.content) == {"note": "Phoned borrower"}
    up = respx.post(f"{BASE}/loans/536/documents").respond(200, json={"resourceId": 77})
    d = run(fb.add_loan_document("K", 536, "signed_agreement", "s.pdf", "application/pdf", b"%PDF", TODAY))
    assert d.id == 77 and b"signed_agreement" in up.calls[0].request.content


@respx.mock
def test_portal_cannot_read_notes_is_fine(fb):
    respx.get(f"{BASE}/loans/536/notes").respond(403, json={"defaultUserMessage": "no"})
    assert run(fb._loan_notes("portal", 536)) == []


def test_note_times_are_port_moresby_days():
    from app.backends.fineract import _note_time
    from app.deps import local_zone

    pom = local_zone("Pacific/Port_Moresby")
    # 23:30 UTC on the 5th is 09:30 on the 6th in Port Moresby
    assert _note_time("2026-10-05T23:30:00Z", pom).date() == date(2026, 10, 6)
    assert _note_time([2026, 10, 5, 23, 30, 0], pom).date() == date(2026, 10, 6)
    epoch = 1791243000000  # 2026-10-05 23:30 UTC
    assert _note_time(epoch, pom).date() == date(2026, 10, 6)
    assert _note_time("2026-10-05", pom).date() == date(2026, 10, 5)
    assert _note_time("rubbish", pom) is None


@respx.mock
def test_history_orders_same_day_events_sensibly(fb):
    loan = {
        **LOAN,
        "status": {"id": 300},
        "timeline": {
            "submittedOnDate": [2026, 10, 6],
            "approvedOnDate": [2026, 10, 6],
            "actualDisbursementDate": [2026, 10, 6],
        },
    }
    respx.get(f"{BASE}/loans/536").respond(200, json=loan)
    respx.get(f"{BASE}/clients/8").respond(200, json={"id": 8, "displayName": "Peter Wambi"})
    respx.get(f"{BASE}/clients/8/identifiers").respond(200, json=[])
    respx.get(url__regex=rf"{BASE}/datatables/.*").respond(200, json=[])
    respx.get(f"{BASE}/loans/536/notes").respond(
        200,
        json=[  # Fineract lists newest first
            {"id": 3, "note": "Signed agreement uploaded (s.pdf)", "createdOn": "2026-10-06T01:00:00Z"},
            {"id": 4, "note": "Paid out in McLender (bank), reference TT-1", "createdOn": "2026-10-06T02:00:00Z"},
            {"id": 2, "note": "Phoned borrower: coming at 11", "createdOn": "2026-10-05T23:10:00Z"},
            {
                "id": 1,
                "note": "SMS sent to borrower (71234567): agreement ready to sign",
                "createdOn": "2026-10-05T23:00:00Z",
            },
        ],
    )
    d = run(fb.get_loan("K", 536, TODAY))
    oldest_first = [h.text for h in reversed(d.history)]
    assert oldest_first == [
        "Application submitted",
        "Approved",
        "SMS sent to borrower (71234567): agreement ready to sign",
        "Phoned borrower: coming at 11",
        "Signed agreement uploaded (s.pdf)",
        "Disbursed",
    ]


@respx.mock
def test_notes_failure_never_blocks_loading_a_loan(fb):
    respx.get(f"{BASE}/loans/536/notes").respond(500, text="boom")
    assert run(fb._loan_notes("K", 536)) == []


@respx.mock
def test_portal_user_refused_is_not_shown_as_a_sign_in_problem(fb, caplog):
    respx.get(f"{BASE}/clients/8/accounts").respond(401, json={})
    with pytest.raises(BackendError) as e:
        run(fb.borrower_loans(8, TODAY))
    assert e.value.status == 503 and "Fineract" not in e.value.message
    assert "MCL_FINERACT_PORTAL_PASSWORD" in caplog.text
    respx.get(f"{BASE}/loans/1").respond(401, json={})
    with pytest.raises(BackendError) as e:
        run(fb._get("STAFFKEY", "/loans/1"))
    assert e.value.status == 401  # staff are asked to sign in again


@respx.mock
def test_remove_documents_and_client_notes(fb):
    d1 = respx.delete(f"{BASE}/clients/8/documents/5").respond(200, json={"resourceId": 5})
    d2 = respx.delete(f"{BASE}/loans/536/documents/6").respond(200, json={"resourceId": 6})
    run(fb.delete_document("K", 8, 5))
    run(fb.delete_loan_document("K", 536, 6))
    assert d1.called and d2.called
    note = respx.post(f"{BASE}/clients/8/notes").respond(200, json={"resourceId": 3})
    run(fb.add_client_note("K", 8, "Removed payslip", TODAY))
    assert json.loads(note.calls[0].request.content) == {"note": "Removed payslip"}
    respx.get(f"{BASE}/clients/8/notes").respond(
        200,
        json=[
            {"id": 1, "note": "older", "createdOn": "2026-10-01T01:00:00Z", "createdByUsername": "jk"},
            {"id": 2, "note": "newer", "createdOn": "2026-10-05T23:30:00Z", "createdByUsername": "gp"},
        ],
    )
    notes = run(fb.client_notes("K", 8))
    assert [(n.text, n.when, n.who) for n in notes] == [("newer", "2026-10-06", "gp"), ("older", "2026-10-01", "jk")]


@respx.mock
def test_save_review_creates_then_updates_the_row(fb):
    from app.domain.models import LoanReview

    respx.get(f"{BASE}/datatables/dt_loan_review/536").respond(200, json=[])
    created = respx.post(f"{BASE}/datatables/dt_loan_review/536").respond(200, json={"resourceId": 536})
    review = LoanReview(
        stage="SUBMITTED",
        officer_recommendation="APPROVE",
        officer_amount=D("13000"),
        officer_note="ok",
        submitted_by="John Kerema",
        submitted_on=TODAY,
    )
    run(fb.save_review("K", 536, review))
    body = json.loads(created.calls[0].request.content)
    assert body["stage"] == "SUBMITTED" and body["officer_amount"] == "13000" and body["submitted_on"] == "2026-10-06"
    assert body["returned_note"] is None and body["dateFormat"] == "yyyy-MM-dd"


@respx.mock
def test_missing_review_table_is_not_mistaken_for_not_reviewed(fb):
    table = respx.get(f"{BASE}/datatables/dt_loan_review")
    table.respond(404, json={"defaultUserMessage": "Datatable not found."})
    assert run(fb._review("K", 536)) is None
    table.respond(200, json={})
    fb._invalidate()
    respx.get(f"{BASE}/datatables/dt_loan_review/536").respond(200, json=[])
    assert run(fb._review("K", 536)).stage == "DRAFT"  # the table is there, with no row yet


@respx.mock
def test_client_photo_is_saved_and_read_back(fb):
    up = respx.post(f"{BASE}/clients/8/images").respond(200, json={"resourceId": 8})
    run(fb.set_photo("K", 8, b"\xff\xd8\xffjpeg"))
    assert b'filename="photo.jpg"' in up.calls[0].request.content
    import base64

    respx.get(f"{BASE}/clients/8/images").respond(
        200, content=b"data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xffjpeg")
    )
    assert run(fb.get_photo("K", 8)) == b"\xff\xd8\xffjpeg"


@respx.mock
def test_no_client_photo(fb):
    respx.get(f"{BASE}/clients/8/images").respond(404, json={})
    assert run(fb.get_photo("K", 8)) is None


@respx.mock
def test_review_table_check_does_not_cache_other_errors(fb):
    table = respx.get(f"{BASE}/datatables/dt_loan_review")
    table.respond(502, json={"defaultUserMessage": "gateway"})
    with pytest.raises(BackendError):
        run(fb._review("K", 536))
    table.respond(200, json={})
    respx.get(f"{BASE}/datatables/dt_loan_review/536").respond(200, json=[])
    assert run(fb._review("K", 536)).stage == "DRAFT"  # the 502 wasn't remembered as "missing"


@respx.mock
def test_duplicate_nid_found_however_it_was_stored(fb):
    from app.domain.models import BorrowerIn

    respx.get(f"{BASE}/search", params={"resource": "clients"}).respond(200, json=[])
    nid = respx.get(f"{BASE}/search", params={"resource": "clientIdentifiers"}).respond(
        200, json=[{"entityName": "2009-1182-4410", "parentId": 1, "parentName": "Mary Kila"}]
    )
    body = BorrowerIn(
        first_name="Kila",
        last_name="Morea",
        phone="75551212",
        date_of_birth=date(1990, 4, 12),
        gender="female",
        address="Tokarara",
        national_id="2009 1182 4410",
        existing_monthly_debt=D("0"),
    )
    with pytest.raises(BackendError, match="Mary Kila"):
        run(fb._check_unique("K", body))
    assert nid.calls[0].request.url.params["query"] == "2009"
