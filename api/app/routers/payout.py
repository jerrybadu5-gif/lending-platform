"""After approval: tell the borrower, take back the signed agreement, then pay out.

Steps on an approved loan:
  1. Print the agreement (GET /api/staff/loans/{id}/agreement.pdf).
  2. Tell the borrower to come in and sign: an SMS goes automatically on approval; staff can send it
     again or log a phone call. Each contact is a loan note, so it shows in the loan's history.
  3. Upload the signed agreement to the loan.
  4. Record the disbursement (method, reference, account), which needs step 3 when
     MCL_SIGNED_AGREEMENT_REQUIRED is on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..deps import Services, services
from ..domain.models import BorrowerDocument, ContactIn, LoanDetail, LoanEvent, PayoutStatus
from ..domain.uploads import UploadRejected, check_upload, content_disposition
from ..security import StaffSession, staff_session

router = APIRouter(prefix="/api/staff/loans", tags=["payout"])

SMS_MARK = "SMS sent to borrower"
PHONE_MARK = "Phoned borrower"


def sign_sms(svc: Services, loan: LoanDetail) -> str:
    return (
        f"{svc.settings.company_name}: good news, your loan {loan.ref} for K {loan.principal:,.2f} is approved. "
        "Please come to our office with your ID to sign your loan agreement."
    )


async def notify_approved(svc: Services, cred: str, loan_id: int) -> None:
    """Tell the borrower to come and sign, and note it on the loan. Never fails the approval."""
    loan = await svc.backend.get_loan(cred, loan_id, svc.today())
    if not loan.borrower.phone:
        await svc.backend.add_loan_note(cred, loan_id, "No phone on file: contact the borrower to sign", svc.today())
        return
    await svc.sms.send(loan.borrower.phone, sign_sms(svc, loan))
    await svc.backend.add_loan_note(
        cred, loan_id, f"{SMS_MARK} ({loan.borrower.phone}): agreement ready to sign", svc.today()
    )


async def payout_status(svc: Services, cred: str, loan_id: int) -> PayoutStatus:
    loan = await svc.backend.get_loan(cred, loan_id, svc.today())
    docs = await svc.backend.list_loan_documents(cred, loan_id)
    signed = next((d for d in docs if d.kind == "signed_agreement"), None)
    # loan.history is newest first; the contact log reads oldest first.
    told = [e for e in reversed(loan.history) if e.text.startswith((SMS_MARK, PHONE_MARK))]
    missing = []
    if svc.settings.signed_agreement_required and signed is None:
        missing.append("Upload the borrower's signed loan agreement.")
    return PayoutStatus(
        loan_id=loan_id,
        borrower_told=told,
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
    note = body.note.strip()
    if body.channel == "sms":
        if not loan.borrower.phone:
            raise HTTPException(422, "There is no phone number for this borrower. Add one on their profile.")
        await svc.sms.send(loan.borrower.phone, sign_sms(svc, loan))
        text = f"{SMS_MARK} ({loan.borrower.phone}): agreement ready to sign"
    else:
        text = f"{PHONE_MARK}" + (f": {note}" if note else "")
    await svc.backend.add_loan_note(s.cred, loan_id, text, svc.today())
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
    await svc.backend.add_loan_note(s.cred, loan_id, f"Signed agreement uploaded ({name})", svc.today())
    return doc


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
