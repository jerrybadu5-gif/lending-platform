"""Staff app endpoints: sign-in, dashboard, applications, decisions, collections, repayments."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from .. import pdf
from ..deps import Services, services
from ..domain.models import (
    ActionResult,
    ApproveIn,
    CollectionItem,
    Dashboard,
    DisburseIn,
    LoanDetail,
    LoanReview,
    LoanSummary,
    Receipt,
    RejectIn,
    RepaymentIn,
    ReturnIn,
    StaffUser,
    SubmitIn,
)
from ..security import STAFF_COOKIE, StaffSession, end_session, staff_session, start_session
from ..underwriting import assess_loan
from .borrowers import borrower_kyc
from .documents import company_of
from .payout import PAYOUT_PENDING_MARK, add_note_safely, notify_approved, payout_status

log = logging.getLogger("mclender.staff")

router = APIRouter(prefix="/api/staff", tags=["staff"])
APPROVER_ROLES = {"credit manager", "super user", "branch manager"}


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class StaffLogin(StaffUser):
    tab_token: str


def is_approver(s: StaffSession) -> bool:
    return bool(APPROVER_ROLES & {r.lower() for r in s.roles})


def _require_approver(s: StaffSession) -> None:
    if not is_approver(s):
        raise HTTPException(403, "Only a credit manager can do this.")


REVIEW_NOT_SET_UP = (
    "Sending applications for approval isn't set up in Fineract yet (data table dt_loan_review). "
    "Ask your administrator to run underwriting/bootstrap.py and give staff roles access to it."
)


def _require_submitted(svc: Services, loan: LoanDetail, s: StaffSession | None = None) -> None:
    if not svc.settings.review_required or loan.state != "PENDING":
        return
    if loan.review is None:
        raise HTTPException(503, REVIEW_NOT_SET_UP)
    if loan.review.stage != "SUBMITTED":
        raise HTTPException(409, "The loan officer hasn't sent this application for approval yet.")
    # Four eyes: whoever sent it up doesn't also approve it.
    if s and not svc.settings.allow_self_approval and loan.review.submitted_user == s.username:
        raise HTTPException(
            409, "You sent this application for approval yourself, so another credit manager must decide it."
        )


@router.post("/login", response_model=StaffLogin)
async def login(body: LoginIn, request: Request, response: Response, svc: Services = Depends(services)):
    key = f"{request.client.host if request.client else '-'}:{body.username.lower()}"
    svc.login_limit.check(key)
    user, cred = await svc.backend.authenticate(body.username, body.password)
    svc.login_limit.reset(key)  # only failed attempts count towards the limit
    session = StaffSession(username=user.username, display_name=user.display_name, roles=user.roles, cred=cred)
    start_session(response, svc, STAFF_COOKIE, session)
    return StaffLogin(
        username=user.username,
        display_name=user.display_name,
        roles=user.roles,
        review_required=svc.settings.review_required,
        allow_self_approval=svc.settings.allow_self_approval,
        tab_token=session.tab_token,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, svc: Services = Depends(services)) -> None:
    end_session(request, response, svc, STAFF_COOKIE)


@router.get("/me", response_model=StaffUser)
async def me(s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return StaffUser(
        username=s.username,
        display_name=s.display_name,
        roles=s.roles,
        review_required=svc.settings.review_required,
        allow_self_approval=svc.settings.allow_self_approval,
    )


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
    loan = await _require_kyc(svc, s.cred, loan_id)
    _require_submitted(svc, loan, s)
    result = await svc.backend.approve(s.cred, loan_id, body, svc.today())
    if result.state == "APPROVED":  # not while a second approver still has to confirm (maker-checker)
        try:
            warning = await notify_approved(svc, s.cred, loan_id)
        except Exception:  # the approval stands whatever happens here; staff can send the SMS again
            log.exception("Could not tell the borrower about approved loan %s", loan_id)
            warning = " The SMS to the borrower didn't go: send it again from the loan."
        if warning:
            result.message += warning
    return result


async def _require_kyc(svc: Services, cred: str, loan_id: int, *, submission: bool = False) -> LoanDetail:
    """Approval and payout both need the borrower's KYC documents on file (a loan may have been approved
    elsewhere, e.g. in Mifos X or before this check existed). Submission always requires documents,
    regardless of the approval setting. Returns the loan, so callers needn't load it again."""
    detail = await svc.backend.get_loan(cred, loan_id, svc.today())
    if not submission and not svc.settings.kyc_required_for_approval:
        return detail
    kyc = await borrower_kyc(svc, cred, detail.borrower.id)
    if not kyc.complete:
        raise HTTPException(409, "Upload these documents for the borrower first: " + "; ".join(kyc.missing) + ".")
    return detail


@router.post("/loans/{loan_id}/reject", response_model=ActionResult)
async def reject(
    loan_id: int, body: RejectIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    _require_approver(s)
    # The credit manager has the final say: an application can be declined at any stage, with a reason.
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if loan.state != "PENDING":
        raise HTTPException(409, "Only an application waiting for a decision can be rejected.")
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


@router.post("/loans/{loan_id}/submit", response_model=LoanDetail)
async def submit(
    loan_id: int, body: SubmitIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    """The loan officer's part: documents checked, assessment done, recommendation written. Sends it to the
    credit manager's queue."""
    if is_approver(s) and not svc.settings.allow_self_approval:
        # The credit manager decides (approve, reject, or send back for more work); sending up is the officer's step.
        raise HTTPException(403, "A credit manager decides applications. Approve, reject, or send it back instead.")
    # The officer sends an application up only with the borrower's documents complete.
    loan = await _require_kyc(svc, s.cred, loan_id, submission=True)
    if loan.state != "PENDING":
        raise HTTPException(409, "Only an application waiting for a decision can be sent for approval.")
    prior = loan.review
    if prior is None:
        raise HTTPException(503, REVIEW_NOT_SET_UP)
    if prior.stage == "SUBMITTED":
        raise HTTPException(409, "This application is already with the credit manager.")
    if loan.assessment is None:
        loan = await _assess(loan_id, s.cred, svc)
    if body.recommendation == "APPROVE" and body.amount is not None and body.amount > loan.principal:
        raise HTTPException(422, "The recommended amount can't be more than the borrower applied for.")
    today = svc.today()
    review = LoanReview(
        stage="SUBMITTED",
        officer_recommendation=body.recommendation,
        officer_amount=(body.amount or loan.principal) if body.recommendation == "APPROVE" else None,
        officer_note=body.note.strip(),
        submitted_by=s.display_name,
        submitted_user=s.username,
        submitted_on=today,
        # Keep the manager's last reply so it's clear what was asked for, until a decision is made.
        returned_note=prior.returned_note,
        returned_by=prior.returned_by,
        returned_on=prior.returned_on,
    )
    await svc.backend.save_review(s.cred, loan_id, review)
    advice = (
        f"recommends approving K {review.officer_amount:,.2f}"
        if body.recommendation == "APPROVE"
        else "recommends declining"
    )
    await add_note_safely(svc, s.cred, loan_id, f"Sent for approval: {advice}. {review.officer_note}")
    return await svc.backend.get_loan(s.cred, loan_id, today)


@router.post("/loans/{loan_id}/return", response_model=LoanDetail)
async def send_back(
    loan_id: int, body: ReturnIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    """The credit manager asks the loan officer for more work, with a note. Works whether or not the officer
    has sent it up yet (e.g. to ask for a document before the officer's review)."""
    _require_approver(s)
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if loan.state != "PENDING":
        raise HTTPException(409, "Only an application waiting for a decision can be sent back.")
    if loan.review is None:
        raise HTTPException(503, REVIEW_NOT_SET_UP)
    today = svc.today()
    note = body.note.strip()
    review = loan.review.model_copy(
        update={"stage": "RETURNED", "returned_note": note, "returned_by": s.display_name, "returned_on": today}
    )
    await svc.backend.save_review(s.cred, loan_id, review)
    await add_note_safely(svc, s.cred, loan_id, f"Sent back to the loan officer: {note}")
    return await svc.backend.get_loan(s.cred, loan_id, today)


@router.post("/loans/{loan_id}/disburse", response_model=ActionResult)
async def disburse(
    loan_id: int, body: DisburseIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    _require_approver(s)
    loan = await _require_kyc(svc, s.cred, loan_id)
    if loan.state != "APPROVED":
        raise HTTPException(409, "Only an approved loan can be paid out.")
    payout = await payout_status(svc, s.cred, loan_id, loan)
    if payout.missing:
        raise HTTPException(409, " ".join(payout.missing))
    result = await svc.backend.disburse(s.cred, loan_id, body, svc.today())
    if result.state == "APPROVED":  # maker-checker: a second approver must confirm in Fineract
        await add_note_safely(svc, s.cred, loan_id, f"{PAYOUT_PENDING_MARK} (reference {body.reference})")
    if result.state == "ACTIVE" and payout.phone:
        try:
            await svc.sms.send(
                payout.phone,
                f"{svc.settings.company_name}: we have paid out your loan. Reference {body.reference}. "
                "Your repayment schedule is in your signed agreement.",
            )
        except Exception:
            log.exception("Could not send the pay-out SMS for loan %s", loan_id)
    return result


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
    receipt.filed = await _file_receipt(svc, s.cred, receipt)
    return receipt


async def _file_receipt(svc: Services, cred: str, receipt: Receipt) -> bool:
    """Keep a PDF copy of the receipt on the loan, so it can be found and printed again later. Best effort:
    the repayment is recorded whatever happens here."""
    if receipt.payment_id is None:
        return False
    try:
        today = svc.today()
        loan = await svc.backend.get_loan(cred, receipt.loan_id, today)
        payment = next((p for p in loan.payments if p.id == receipt.payment_id), None)
        if payment is None:
            return False
        data = pdf.receipt(loan, payment, company_of(svc), today)
        await svc.backend.add_loan_document(
            cred, receipt.loan_id, "receipt", f"{receipt.receipt_no}.pdf", "application/pdf", data, today
        )
        return True
    except Exception:
        log.exception("Could not file receipt %s on loan %s", receipt.receipt_no, receipt.loan_id)
        return False
