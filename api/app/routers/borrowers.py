"""Staff endpoints for borrowers: sign-up, profile, KYC documents and taking a loan application."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from ..deps import Services, services
from ..domain import idcard
from ..domain.kyc import kyc_status
from ..domain.models import (
    BORROWER_DOCUMENT_KINDS,
    DOCUMENT_LABELS,
    ApplicationIn,
    Borrower,
    BorrowerDocument,
    BorrowerIn,
    BorrowerListItem,
    BorrowerProfile,
    DocumentKind,
    Gender,
    IdScanOut,
    IdSuggestionsOut,
    KycStatus,
    LoanSummary,
    RemoveIn,
)
from ..domain.uploads import UploadRejected, check_upload, content_disposition
from ..security import StaffSession, staff_session
from ..underwriting import assess_loan

log = logging.getLogger("mclender.borrowers")
router = APIRouter(prefix="/api/staff/borrowers", tags=["borrowers"])


@router.get("", response_model=list[BorrowerListItem])
async def search(
    q: str = Query(default="", max_length=60),
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    return await svc.backend.search_borrowers(s.cred, q)


@router.post("", response_model=Borrower, status_code=201)
async def create(body: BorrowerIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return await svc.backend.create_borrower(s.cred, body, svc.today())


@router.get("/{borrower_id}", response_model=BorrowerProfile)
async def profile(borrower_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    borrower, docs, loans, notes = await asyncio.gather(
        svc.backend.get_borrower(s.cred, borrower_id),
        svc.backend.list_documents(s.cred, borrower_id),
        svc.backend.borrower_loan_list(s.cred, borrower_id, svc.today()),
        svc.backend.client_notes(s.cred, borrower_id),
    )
    return BorrowerProfile(
        borrower=borrower,
        documents=docs,
        kyc=kyc_status(docs, svc.settings.kyc_required),
        loans=loans,
        notes=notes[:20],
    )


@router.put("/{borrower_id}", response_model=Borrower)
async def update(
    borrower_id: int, body: BorrowerIn, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    return await svc.backend.update_borrower(s.cred, borrower_id, body)


@router.get("/{borrower_id}/kyc", response_model=KycStatus)
async def kyc(borrower_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    return await borrower_kyc(svc, s.cred, borrower_id)


async def borrower_kyc(svc: Services, cred: str, borrower_id: int) -> KycStatus:
    return kyc_status(await svc.backend.list_documents(cred, borrower_id), svc.settings.kyc_required)


@router.post("/{borrower_id}/documents", response_model=BorrowerDocument, status_code=201)
async def upload(
    borrower_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    if kind not in BORROWER_DOCUMENT_KINDS:  # signed agreements and receipts belong to the loan
        raise HTTPException(422, "Choose what kind of document this is.")
    limit = svc.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        name, ctype = check_upload(file.filename or "document", data, limit)
    except UploadRejected as e:
        raise HTTPException(422, str(e)) from e
    return await svc.backend.add_document(s.cred, borrower_id, cast(DocumentKind, kind), name, ctype, data, svc.today())


@router.get("/{borrower_id}/documents/{doc_id}")
async def download(
    borrower_id: int, doc_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    doc, data = await svc.backend.get_document(s.cred, borrower_id, doc_id)
    # Always a download, never shown inline, so an uploaded file can't run in the app's pages.
    return Response(
        data,
        media_type=doc.content_type if doc.content_type in SAFE_TYPES else "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition(doc.file_name),
            "Cache-Control": "private, no-store",
        },
    )


SAFE_TYPES = {"application/pdf", "image/jpeg", "image/png"}
_scanning = asyncio.Semaphore(2)  # reading a card takes a second or two of CPU: don't run many at once


@router.post("/{borrower_id}/documents/{doc_id}/scan", response_model=IdScanOut)
async def scan_id(
    borrower_id: int, doc_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)
):
    """Find the photo on an uploaded ID card and read its details. Changes nothing: staff check and choose."""
    doc, data = await svc.backend.get_document(s.cred, borrower_id, doc_id)
    if doc.kind != "id":
        raise HTTPException(422, "Only an ID document can be read.")
    async with _scanning:
        try:
            result = await asyncio.to_thread(idcard.scan, data, doc.content_type)
        except idcard.ScanError as e:
            raise HTTPException(422, str(e)) from e
    found = result.suggestions
    return IdScanOut(
        photo="data:image/jpeg;base64," + base64.b64encode(result.photo).decode() if result.photo else None,
        suggestions=IdSuggestionsOut(
            national_id=found.national_id,
            first_name=found.first_name,
            last_name=found.last_name,
            date_of_birth=found.date_of_birth,
            gender=cast(Gender | None, found.gender),
        ),
        text_read=result.text_read,
        problems=result.problems,
    )


@router.put("/{borrower_id}/photo", status_code=204)
async def set_photo(
    borrower_id: int,
    file: UploadFile = File(...),
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    """Save the borrower's photo (cropped from their ID card, or a photo taken at the branch)."""
    data = await file.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise HTTPException(422, "The photo is too big. Use one under 2 MB.")
    async with _scanning:
        try:
            jpeg = await asyncio.to_thread(idcard.clean_photo, data)
        except idcard.ScanError as e:
            raise HTTPException(422, str(e)) from e
    await svc.backend.set_photo(s.cred, borrower_id, jpeg)
    try:  # the photo is saved either way; the note is the record of who changed it
        await svc.backend.add_client_note(s.cred, borrower_id, f"Photo updated by {s.display_name}", svc.today())
    except Exception:
        log.exception("Could not note the photo change for borrower %s", borrower_id)
    return Response(status_code=204)


@router.get("/{borrower_id}/photo")
async def get_photo(borrower_id: int, s: StaffSession = Depends(staff_session), svc: Services = Depends(services)):
    data = await svc.backend.get_photo(s.cred, borrower_id)
    if not data:
        raise HTTPException(404, "No photo yet.")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


MAX_PHOTO = 2 * 1024 * 1024
DECIDED = {"APPROVED", "ACTIVE", "ARREARS", "ARREARS_LATE", "CLOSED", "WRITTEN_OFF"}


@router.post("/{borrower_id}/documents/{doc_id}/remove", status_code=204)
async def remove(
    borrower_id: int,
    doc_id: int,
    body: RemoveIn,
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    """Remove a wrong upload. The reason goes on the borrower's file first, so nothing disappears without a trace."""
    today = svc.today()
    docs, loans = await asyncio.gather(
        svc.backend.list_documents(s.cred, borrower_id),
        svc.backend.borrower_loan_list(s.cred, borrower_id, today),
    )
    doc = next((d for d in docs if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    # A document that was on file when a loan was approved is part of that loan's record: keep it.
    for summary in loans:
        if summary.state not in DECIDED:
            continue
        loan = await svc.backend.get_loan(s.cred, summary.id, today)
        if loan.approved_on and (doc.uploaded_on is None or doc.uploaded_on <= loan.approved_on):
            raise HTTPException(
                409,
                f"This document supported the approval of {loan.ref}, so it stays on file. "
                "Upload the correct one alongside it.",
            )
    label = DOCUMENT_LABELS.get(doc.kind, doc.kind)
    reason = " ".join(body.reason.split())
    await svc.backend.add_client_note(s.cred, borrower_id, f"Removed {label}: {doc.file_name}. Reason: {reason}", today)
    await svc.backend.delete_document(s.cred, borrower_id, doc_id)
    return Response(status_code=204)


@router.post("/{borrower_id}/applications", response_model=LoanSummary, status_code=201)
async def apply(
    borrower_id: int,
    body: ApplicationIn,
    s: StaffSession = Depends(staff_session),
    svc: Services = Depends(services),
):
    today = svc.today()
    summary = await svc.backend.create_application(s.cred, borrower_id, body, today)
    detail = await svc.backend.get_loan(s.cred, summary.id, today)
    await svc.backend.save_assessment(s.cred, summary.id, assess_loan(detail, svc.policy, today))
    return summary
