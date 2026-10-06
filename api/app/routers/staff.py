"""Staff app endpoints: sign-in, dashboard, applications, decisions, collections, repayments."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..deps import Services, services
from ..domain.models import (
    ActionResult,
    ApproveIn,
    CollectionItem,
    Dashboard,
    LoanDetail,
    LoanSummary,
    Receipt,
    RejectIn,
    RepaymentIn,
    StaffUser,
)
from ..security import STAFF_COOKIE, StaffSession, end_session, staff_session, start_session
from ..underwriting import assess_loan
from .borrowers import borrower_kyc

router = APIRouter(prefix="/api/staff", tags=["staff"])
APPROVER_ROLES = {"credit manager", "super user", "branch manager"}


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


def _require_approver(s: StaffSession) -> None:
    if not APPROVER_ROLES & {r.lower() for r in s.roles}:
        raise HTTPException(403, "Only a credit manager can do this.")


@router.post("/login", response_model=StaffUser)
async def login(body: LoginIn, request: Request, response: Response, svc: Services = Depends(services)):
    svc.login_limit.check(f"{request.client.host if request.client else '-'}:{body.username.lower()}")
    user, cred = await svc.backend.authenticate(body.username, body.password)
    start_session(
        response,
        svc,
        STAFF_COOKIE,
        StaffSession(username=user.username, display_name=user.display_name, roles=user.roles, cred=cred),
    )
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, svc: Services = Depends(services)) -> None:
    end_session(request, response, svc, STAFF_COOKIE)


@router.get("/me", response_model=StaffUser)
async def me(s: StaffSession = Depends(staff_session)):
    return StaffUser(username=s.username, display_name=s.display_name, roles=s.roles)


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return await svc.backend.dashboard(s.cred, svc.today())


@router.get("/loans", response_model=list[LoanSummary])
async def loans(
    state: list[str] = Query(default=[]), s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    today = svc.today()
    out = await svc.backend.list_loans(s.cred, today, set(state) or None)
    # Run the affordability check on any pending loan that hasn't had one, so the list shows it.
    stale = [l.id for l in out if l.state == "PENDING" and l.recommendation is None]
    for loan_id in stale:
        await _assess(loan_id, s.cred, svc)
    if stale:
        out = await svc.backend.list_loans(s.cred, today, set(state) or None)
    return out


@router.get("/loans/{loan_id}", response_model=LoanDetail)
async def loan(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    detail = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if detail.state == "PENDING" and detail.assessment is None:
        detail = await _assess(loan_id, s.cred, svc)
    return detail


async def _assess(loan_id: int, cred: str, svc: Services) -> LoanDetail:
    today = svc.today()
    detail = await svc.backend.get_loan(cred, loan_id, today)
    await svc.backend.save_assessment(cred, loan_id, assess_loan(detail, svc.policy, today))
    return await svc.backend.get_loan(cred, loan_id, today)


@router.post("/loans/{loan_id}/assess", response_model=LoanDetail)
async def reassess(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return await _assess(loan_id, s.cred, svc)


@router.post("/loans/{loan_id}/approve", response_model=ActionResult)
async def approve(
    loan_id: int, body: ApproveIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    _require_approver(s)
    if svc.settings.kyc_required_for_approval:
        detail = await svc.backend.get_loan(s.cred, loan_id, svc.today())
        kyc = await borrower_kyc(svc, s.cred, detail.borrower.id)
        if not kyc.complete:
            raise HTTPException(409, "Upload these documents for the borrower first: " + "; ".join(kyc.missing) + ".")
    return await svc.backend.approve(s.cred, loan_id, body, svc.today())


@router.post("/loans/{loan_id}/reject", response_model=ActionResult)
async def reject(
    loan_id: int, body: RejectIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    _require_approver(s)
    result = await svc.backend.reject(s.cred, loan_id, body, svc.today())
    if result.state != "REJECTED":  # waiting for a second approver (maker-checker): tell no one yet
        return result
    detail = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if detail.borrower.phone:
        await svc.sms.send(
            detail.borrower.phone,
            f"{svc.settings.company_name}: we can't offer you loan {detail.ref} "
            "at this time. Call us if you have questions.",
        )
    return result


@router.post("/loans/{loan_id}/disburse", response_model=ActionResult)
async def disburse(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    _require_approver(s)
    return await svc.backend.disburse(s.cred, loan_id, svc.today())


@router.get("/collections", response_model=list[CollectionItem])
async def collections(
    view: Literal["today", "arrears", "all"] = "all",
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    items = await svc.backend.collections(s.cred, svc.today())
    if view == "today":
        return [c for c in items if c.days_overdue == 0]
    if view == "arrears":
        return [c for c in items if c.days_overdue > 0]
    return items


@router.post("/loans/{loan_id}/repayments", response_model=Receipt, status_code=201)
async def repayment(
    loan_id: int, body: RepaymentIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    receipt = await svc.backend.record_repayment(s.cred, loan_id, body, svc.today())
    if receipt.sms_sent_to:
        await svc.sms.send(
            receipt.sms_sent_to,
            f"{svc.settings.company_name}: we received K {receipt.amount:,.2f} "
            f"for loan {receipt.ref} on {receipt.received_on:%d/%m/%Y}. "
            f"Receipt {receipt.receipt_no}. Thank you.",
        )
    return receipt
