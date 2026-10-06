"""Runs the affordability check (domain/risk.py) on a loan and turns it into an API Assessment."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import cast

from .domain.models import Assessment, LoanDetail, Quote, Recommendation
from .domain.risk import FLAT, Applicant, LoanTerms, Policy, assess, installment, money


@lru_cache
def load_policy(path: str = "") -> Policy:
    if path and Path(path).exists():
        return Policy.from_dict(json.loads(Path(path).read_text()))
    return Policy()


def assess_loan(loan: LoanDetail, policy: Policy, today: date) -> Assessment:
    b = loan.borrower
    # The regular installment: the first scheduled one (the last absorbs rounding and can differ by a few toea).
    scheduled = loan.schedule[0].total if loan.schedule else None
    terms = LoanTerms(
        principal=loan.principal,
        annual_rate=loan.annual_rate / 100,
        installments=loan.term_months,
        interest_type=FLAT if loan.interest_method == "FLAT" else "DECLINING_BALANCE",
        scheduled_installment=scheduled,
        periods_per_year=loan.repayments_per_year,
    )
    a = assess(
        Applicant(
            monthly_income=b.monthly_income,
            existing_monthly_debt=b.existing_monthly_debt or Decimal(0),
            credit_score=b.credit_score,
            monthly_business_noi=b.monthly_business_noi,
        ),
        terms,
        policy,
    )
    return Assessment(
        recommendation=cast(Recommendation, a.recommendation),
        risk_score=a.risk_score,
        monthly_payment=a.monthly_payment,
        dti=a.dti,
        dscr=a.dscr,
        max_recommended_principal=a.max_recommended_principal,
        max_dti=policy.max_dti,
        policy_version=policy.version,
        assessed_on=today,
        notes=a.notes,
    )


def quote(amount: Decimal, months: int, annual_rate_pct: Decimal) -> Quote:
    pay = installment(amount, annual_rate_pct / 100, months)
    total = money(pay * months)
    return Quote(
        amount=amount,
        months=months,
        annual_rate=annual_rate_pct,
        monthly_payment=pay,
        total_repayable=total,
        total_interest=total - amount,
    )
