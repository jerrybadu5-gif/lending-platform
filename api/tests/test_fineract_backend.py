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
from app.backends.fineract import FineractBackend, fdate
from app.config import Settings
from app.domain.models import ApproveIn, RepaymentIn

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
    respx.get(f"{BASE}/clients/8/identifiers").respond(200, json=[{"documentKey": "2011 0488 7712"}])
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
    d = run(fb.get_loan("KEY", 536, TODAY))
    assert d.ref == "LN-000000536" and d.state == "PENDING" and d.borrower.phone == "71234567"
    assert d.borrower.monthly_income == D("4000") and d.borrower.credit_score == 700
    assert d.schedule[0].total == D("1418.39") and d.assessment is None
    assert d.history[0].text == "Application submitted"


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
