"""How borrowers can pay: shown in the portal and printed on statements and agreements."""

from __future__ import annotations

from .models import PayWay


def ways_to_pay(company_name: str, reference: str) -> list[PayWay]:
    return [
        PayWay(name="CellMoni or MiCash", how=f"Pay merchant {company_name}, reference {reference}"),
        PayWay(name="Bank transfer", how=f"Use reference {reference} so we can match your payment"),
        PayWay(name="Cash at our office", how="Bring your loan number and ID"),
    ]
