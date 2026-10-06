"""PDF documents: loan agreement, repayment schedule, statement and receipt (staff), and the borrower's
own schedule and statement (portal)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .. import pdf
from ..deps import Services, services
from ..domain.models import LoanDetail
from ..domain.payways import ways_to_pay
from ..security import PortalSession, StaffSession, portal_session, staff_session

router = APIRouter(tags=["documents"])

AGREEMENT_STATES = {"APPROVED", "ACTIVE", "ARREARS", "ARREARS_LATE", "CLOSED"}
STATEMENT_STATES = {"ACTIVE", "ARREARS", "ARREARS_LATE", "CLOSED", "WRITTEN_OFF"}


def _company(svc: Services) -> pdf.Company:
    s = svc.settings
    return pdf.Company(s.company_name, s.company_address, s.company_phone, s.company_email)


def _pdf(data: bytes, name: str) -> Response:
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )


def _render(svc: Services, loan: LoanDetail, kind: str) -> Response:
    today, company = svc.today(), _company(svc)
    ways = ways_to_pay(svc.settings.company_name, loan.payment_reference)
    builders: dict[str, tuple[set[str] | None, Callable[[], bytes], str]] = {
        "agreement": (
            AGREEMENT_STATES,
            lambda: pdf.loan_agreement(loan, company, today, ways, svc.settings.agreement_reviewed),
            "An agreement can be printed once the loan is approved.",
        ),
        "schedule": (None, lambda: pdf.repayment_schedule(loan, company, today), ""),
        "statement": (
            STATEMENT_STATES,
            lambda: pdf.statement(loan, company, today, ways),
            "A statement can be printed once the loan is paid out.",
        ),
    }
    allowed, build, refusal = builders[kind]
    if allowed is not None and loan.state not in allowed:
        raise HTTPException(409, refusal)
    return _pdf(build(), f"{loan.ref}-{kind}.pdf")


@router.get("/api/staff/loans/{loan_id}/agreement.pdf")
async def agreement(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return _render(svc, await svc.backend.get_loan(s.cred, loan_id, svc.today()), "agreement")


@router.get("/api/staff/loans/{loan_id}/schedule.pdf")
async def schedule(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return _render(svc, await svc.backend.get_loan(s.cred, loan_id, svc.today()), "schedule")


@router.get("/api/staff/loans/{loan_id}/statement.pdf")
async def statement(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return _render(svc, await svc.backend.get_loan(s.cred, loan_id, svc.today()), "statement")


@router.get("/api/staff/loans/{loan_id}/payments/{payment_id}/receipt.pdf")
async def receipt(
    loan_id: int, payment_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    payment = next((p for p in loan.payments if p.id == payment_id), None)
    if payment is None:
        raise HTTPException(404, "That payment was not found on this loan.")
    return _pdf(pdf.receipt(loan, payment, _company(svc), svc.today()), f"RC-{payment_id}.pdf")


async def _portal_loan(me: PortalSession, svc: Services) -> LoanDetail:
    loans = await svc.backend.borrower_loans(me.borrower_id, svc.today())
    live = [l for l in loans if l.state in ("ACTIVE", "ARREARS", "ARREARS_LATE")]
    if not live:
        raise HTTPException(404, "You don't have a loan with us at the moment.")
    return live[0]


@router.get("/api/portal/loan/schedule.pdf")
async def portal_schedule(me: PortalSession = Depends(portal_session), svc: Services = Depends(services)):
    return _render(svc, await _portal_loan(me, svc), "schedule")


@router.get("/api/portal/loan/statement.pdf")
async def portal_statement(me: PortalSession = Depends(portal_session), svc: Services = Depends(services)):
    return _render(svc, await _portal_loan(me, svc), "statement")
