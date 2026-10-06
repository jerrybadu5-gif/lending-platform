"""Borrower portal endpoints: sign in with phone + SMS code, see the loan, get a quote, apply."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..backends.base import normalise_phone
from ..deps import Services, services
from ..domain.models import (
    OtpRequest,
    OtpVerify,
    PortalApplicationIn,
    PortalApplicationOut,
    PortalHome,
    PortalLoan,
    Quote,
    QuoteIn,
)
from ..domain.payways import ways_to_pay
from ..security import PORTAL_COOKIE, PortalSession, end_session, portal_session, start_session
from ..underwriting import assess_loan, quote

router = APIRouter(prefix="/api/portal", tags=["portal"])
PORTAL_RATE = Decimal("24")  # personal loan rate shown in quotes; the agreement confirms the final rate
SENT = {"message": "If this number is registered with us, we have sent a 6-digit code by SMS."}


@router.post("/otp")
async def request_code(body: OtpRequest, request: Request, svc: Services = Depends(services)):
    phone = normalise_phone(body.phone)
    svc.otp_limit.check(f"otp:{phone}")
    svc.otp_limit.check(f"otp-ip:{request.client.host if request.client else '-'}")
    borrower = await svc.backend.find_borrower_by_phone(phone)
    if borrower:
        code = svc.otp.issue(phone)
        await svc.sms.send(
            phone,
            f"{svc.settings.company_name}: your sign-in code is {code}. "
            "It expires in 5 minutes. Never share this code.",
        )
    return SENT  # same answer either way, so the form can't be used to find out who borrows from us


@router.post("/verify")
async def verify(body: OtpVerify, response: Response, svc: Services = Depends(services)):
    phone = normalise_phone(body.phone)
    if not svc.otp.verify(phone, body.code):
        raise HTTPException(401, "That code is wrong or has expired. Ask for a new code.")
    borrower = await svc.backend.find_borrower_by_phone(phone)
    if not borrower:
        raise HTTPException(401, "That code is wrong or has expired. Ask for a new code.")
    first_name = borrower.name.split()[0] if borrower.name.strip() else "there"
    start_session(response, svc, PORTAL_COOKIE, PortalSession(borrower_id=borrower.id, first_name=first_name))
    return {"first_name": first_name}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, svc: Services = Depends(services)) -> None:
    end_session(request, response, svc, PORTAL_COOKIE)


@router.get("/home", response_model=PortalHome)
async def home(me: PortalSession = Depends(portal_session), svc: Services = Depends(services)):
    today = svc.today()
    loans = await svc.backend.borrower_loans(me.borrower_id, today)
    name = me.first_name  # a borrower with no loan yet still gets a home page and can apply
    live = [l for l in loans if l.state in ("ACTIVE", "ARREARS", "ARREARS_LATE")]
    if not live:
        return PortalHome(first_name=name, company_name=svc.settings.company_name, loan=None)
    l = live[0]
    paid = [i for i in l.schedule if i.complete]
    ways = ways_to_pay(svc.settings.company_name, l.payment_reference)
    history = l.payments[:3]
    return PortalHome(
        first_name=name,
        company_name=svc.settings.company_name,
        loan=PortalLoan(
            ref=l.ref,
            borrowed=l.principal,
            left_to_pay=l.outstanding,
            payments_made=len(paid),
            payments_total=len(l.schedule),
            next_due_date=l.next_due_date,
            next_due_amount=l.next_due_amount,
            days_overdue=l.days_overdue,
            payment_reference=l.payment_reference,
            ways_to_pay=ways,
            recent_payments=history,
            schedule=l.schedule,
        ),
    )


@router.post("/quote", response_model=Quote)
async def get_quote(body: QuoteIn):
    return quote(body.amount, body.months, PORTAL_RATE)


@router.post("/applications", response_model=PortalApplicationOut, status_code=201)
async def apply(
    body: PortalApplicationIn, me: PortalSession = Depends(portal_session), svc: Services = Depends(services)
):
    today = svc.today()
    summary = await svc.backend.submit_application(me.borrower_id, body, today)
    detail = await svc.backend.get_loan("portal", summary.id, today)
    await svc.backend.save_assessment("portal", summary.id, assess_loan(detail, svc.policy, today))
    q = quote(body.amount, body.months, PORTAL_RATE)
    if detail.borrower.phone:
        await svc.sms.send(
            detail.borrower.phone,
            f"{svc.settings.company_name}: we have your application {summary.ref} "
            f"for K {body.amount:,.2f}. A loan officer will call you within 2 working days.",
        )
    return PortalApplicationOut(
        ref=summary.ref,
        amount=body.amount,
        months=body.months,
        monthly_payment=q.monthly_payment,
        message="A loan officer will call you within 2 working days.",
    )
