"""Staff endpoints for borrowers: sign-up, profile, KYC documents and taking a loan application."""

from __future__ import annotations

import asyncio
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from ..deps import Services, services
from ..domain.kyc import kyc_status
from ..domain.models import (
    DOCUMENT_LABELS,
    ApplicationIn,
    Borrower,
    BorrowerDocument,
    BorrowerIn,
    BorrowerListItem,
    BorrowerProfile,
    DocumentKind,
    KycStatus,
    LoanSummary,
)
from ..domain.uploads import UploadRejected, check_upload
from ..security import StaffSession, staff_session
from ..underwriting import assess_loan

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
    borrower, docs, loans = await asyncio.gather(
        svc.backend.get_borrower(s.cred, borrower_id),
        svc.backend.list_documents(s.cred, borrower_id),
        svc.backend.borrower_loan_list(s.cred, borrower_id, svc.today()),
    )
    return BorrowerProfile(
        borrower=borrower, documents=docs, kyc=kyc_status(docs, svc.settings.kyc_required), loans=loans
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
    if kind not in DOCUMENT_LABELS:
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
            "Content-Disposition": f'attachment; filename="{doc.file_name}"',
            "Cache-Control": "private, no-store",
        },
    )


SAFE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


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
