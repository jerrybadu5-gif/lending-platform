"""After approval: tell the borrower, take back the signed agreement, then pay out.

Steps on an approved loan:
  1. Print the agreement (GET /api/staff/loans/{id}/agreement.pdf).
  2. Tell the borrower to come in and sign: an SMS goes automatically on approval; staff can send it
     again or log a phone call. Each contact is a loan note, so it shows in the loan's history.
  3. Upload the signed agreement to the loan.
  4. Record the disbursement (method, reference, account), which needs step 3 when
     MCL_SIGNED_AGREEMENT_REQUIRED is on.

Loan officers may do steps 2 and 3 (they deal with borrowers day to day); pay-out needs a credit manager.
A side effect that has happened (SMS sent, file stored) is never reported as failed because the
note recording it couldn't be saved; that would invite a second SMS or a duplicate upload.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..deps import Services, services
from ..domain.models import BorrowerDocument, ContactIn, LoanDetail, LoanEvent, PayoutStatus, RemoveIn
from ..domain.uploads import UploadRejected, check_upload, content_disposition
from ..security import StaffSession, staff_session

router = APIRouter(prefix="/api/staff/loans", tags=["payout"])
log = logging.getLogger("mclender.payout")

SMS_MARK = "SMS sent to borrower"
SMS_LOGGED_MARK = "SMS not delivered (no SMS provider set up yet)"
PHONE_MARK = "Phoned borrower"
PAYOUT_PENDING_MARK = "Pay-out recorded, waiting for a second approver"


def sms_delivers(svc: Services) -> bool:
    """Sample data treats the log as the phone; with Fineract, only a real SMS provider delivers."""
    return svc.settings.backend == "demo" or svc.settings.sms_provider != "console"


def sign_sms(svc: Services, loan: LoanDetail) -> str:
    return (
        f"{svc.settings.company_name}: good news, your loan {loan.ref} for K {loan.principal:,.2f} is approved. "
        "Please come to our office with your ID to sign your loan agreement."
    )


async def add_note_safely(svc: Services, cred: str, loan_id: int, text: str) -> bool:
    try:
        await svc.backend.add_loan_note(cred, loan_id, text, svc.today())
        return True
    except Exception:
        log.exception("Could not save the note on loan %s: %s", loan_id, text)
        return False


async def _send_sign_sms(svc: Services, cred: str, loan: LoanDetail) -> str:
    """Send the 'come and sign' SMS (raises if sending fails) and note it. Returns the note text."""
    phone = loan.borrower.phone
    await svc.sms.send(phone or "", sign_sms(svc, loan))
    text = (
        f"{SMS_MARK} ({phone}): agreement ready to sign"
        if sms_delivers(svc)
        else f"{SMS_LOGGED_MARK}: phone the borrower on {phone}"
    )
    await add_note_safely(svc, cred, loan.id, text)
    return text


async def notify_approved(svc: Services, cred: str, loan_id: int) -> str | None:
    """Tell the borrower to come and sign. Returns a warning for staff if the SMS couldn't be sent."""
    loan = await svc.backend.get_loan(cred, loan_id, svc.today())
    if not loan.borrower.phone:
        await add_note_safely(svc, cred, loan_id, "No phone on file: contact the borrower to sign")
        return " There is no phone number on file: contact the borrower to sign."
    try:
        await _send_sign_sms(svc, cred, loan)
    except Exception:
        log.exception("Could not send the approval SMS for loan %s", loan_id)
        return " The SMS to the borrower didn't go: send it again from the loan."
    if not sms_delivers(svc):
        return " No SMS provider is set up yet, so phone the borrower to come and sign."
    return None


async def payout_status(svc: Services, cred: str, loan_id: int, loan: LoanDetail | None = None) -> PayoutStatus:
    loan = loan or await svc.backend.get_loan(cred, loan_id, svc.today())
    docs = await svc.backend.list_loan_documents(cred, loan_id)
    signed = next((d for d in docs if d.kind == "signed_agreement"), None)
    # loan.history is newest first; the contact log reads oldest first.
    told = [e for e in reversed(loan.history) if e.text.startswith((SMS_MARK, SMS_LOGGED_MARK, PHONE_MARK))]
    pending = any(e.text.startswith(PAYOUT_PENDING_MARK) for e in loan.history)
    missing = []
    if svc.settings.signed_agreement_required and signed is None:
        missing.append("Upload the borrower's signed loan agreement.")
    if pending:
        missing.append("A pay-out is already waiting for a second approver in Fineract.")
    return PayoutStatus(
        loan_id=loan_id,
        borrower_told=told,
        told_done=any(e.text.startswith((SMS_MARK, PHONE_MARK)) for e in told),
        sms_delivers=sms_delivers(svc),
        payout_pending=pending,
        signed_agreement=signed,
        bank=loan.borrower.bank,
        phone=loan.borrower.phone,
        ready=loan.state == "APPROVED" and not missing,
        missing=missing,
    )


@router.get("/{loan_id}/payout", response_model=PayoutStatus)
async def status(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return await payout_status(svc, s.cred, loan_id)


@router.post("/{loan_id}/contact", response_model=LoanEvent, status_code=201)
async def contact(
    loan_id: int, body: ContactIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if loan.state != "APPROVED":
        raise HTTPException(
            409, "The borrower is told to come and sign only while the loan is approved and not yet paid out."
        )
    if body.channel == "sms":
        if not loan.borrower.phone:
            raise HTTPException(422, "There is no phone number for this borrower. Add one on their profile.")
        try:
            svc.resend_limit.check(f"sign-sms:{loan_id}")
        except HTTPException:
            raise HTTPException(429, "An SMS was just sent. Wait 10 minutes before sending another.") from None
        text = await _send_sign_sms(svc, s.cred, loan)
    else:
        note = body.note.strip()
        text = PHONE_MARK + (f": {note}" if note else "")
        if not await add_note_safely(svc, s.cred, loan_id, text):
            raise HTTPException(502, "The call couldn't be saved in Fineract. Try again in a moment.")
    return LoanEvent(when=svc.today().isoformat(), text=text, who=s.display_name)


@router.post("/{loan_id}/signed-agreement", response_model=BorrowerDocument, status_code=201)
async def upload_signed(
    loan_id: int,
    file: UploadFile = File(...),
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    if loan.state != "APPROVED":
        raise HTTPException(409, "The signed agreement is uploaded after approval and before pay-out.")
    limit = svc.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        name, ctype = check_upload(file.filename or "signed-agreement", data, limit)
    except UploadRejected as e:
        raise HTTPException(422, str(e)) from e
    doc = await svc.backend.add_loan_document(s.cred, loan_id, "signed_agreement", name, ctype, data, svc.today())
    await add_note_safely(svc, s.cred, loan_id, f"Signed agreement uploaded ({name})")
    return doc


@router.get("/{loan_id}/documents", response_model=list[BorrowerDocument])
async def loan_documents(loan_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    """Files kept on the loan: the signed agreement and a PDF receipt for every repayment."""
    return await svc.backend.list_loan_documents(s.cred, loan_id)


@router.post("/{loan_id}/documents/{doc_id}/remove", status_code=204)
async def remove_document(
    loan_id: int,
    doc_id: int,
    body: RemoveIn,
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    """Only a signed agreement can be removed, and only before pay-out. Receipts are part of the payment record."""
    loan = await svc.backend.get_loan(s.cred, loan_id, svc.today())
    docs = await svc.backend.list_loan_documents(s.cred, loan_id)
    doc = next((d for d in docs if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if doc.kind != "signed_agreement" or loan.state != "APPROVED":
        raise HTTPException(409, "This document is part of the loan record and can't be removed.")
    if any(h.text.startswith(PAYOUT_PENDING_MARK) for h in loan.history):  # pay-out waiting for a second approver
        raise HTTPException(409, "The pay-out has been recorded, so the signed agreement stays on file.")
    reason = " ".join(body.reason.split())
    # The note is the audit trail, so it must be written before the file goes.
    await svc.backend.add_loan_note(
        s.cred, loan_id, f"Signed agreement removed ({doc.file_name}). Reason: {reason}", svc.today()
    )
    await svc.backend.delete_loan_document(s.cred, loan_id, doc_id)
    return Response(status_code=204)


@router.get("/{loan_id}/documents/{doc_id}")
async def download(
    loan_id: int, doc_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    doc, data = await svc.backend.get_loan_document(s.cred, loan_id, doc_id)
    safe = {"application/pdf", "image/jpeg", "image/png"}
    return Response(
        data,
        media_type=doc.content_type if doc.content_type in safe else "application/octet-stream",
        headers={"Content-Disposition": content_disposition(doc.file_name), "Cache-Control": "private, no-store"},
    )
