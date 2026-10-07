"""Which KYC documents a borrower still needs before a loan can be approved."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from .models import DOCUMENT_LABELS, BorrowerDocument, KycStatus


def kyc_status(docs: Iterable[BorrowerDocument], required: Mapping[str, int]) -> KycStatus:
    have: Counter[str] = Counter(str(d.kind) for d in docs)
    missing = [DOCUMENT_LABELS.get(kind, kind) for kind, n in required.items() if have[kind] < n]
    return KycStatus(complete=not missing, missing=missing, have=dict(have))
