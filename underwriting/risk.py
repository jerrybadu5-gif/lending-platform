"""
Affordability and risk assessment for loan applications.

Pure functions, no I/O, Decimal-only money maths (no float anywhere), so the
results can be unit-tested and reproduced exactly from what is stored in Fineract.

The output is a *recommendation*. A loan officer still approves or rejects the
loan in Mifos X, under maker-checker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext
from typing import Optional

CENT = Decimal("0.01")
ZERO = Decimal("0")

DECLINING_BALANCE = "DECLINING_BALANCE"
FLAT = "FLAT"


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Payment maths
# ---------------------------------------------------------------------------

def installment(principal: Decimal, annual_rate: Decimal, n: int,
                periods_per_year: Decimal = Decimal(12),
                interest_type: str = DECLINING_BALANCE) -> Decimal:
    """Payment per period. annual_rate is a fraction (0.24 = 24% p.a.)."""
    if n <= 0:
        raise ValueError("number of installments must be positive")
    with localcontext() as ctx:
        ctx.prec = 40
        if interest_type == FLAT:
            interest = principal * annual_rate * Decimal(n) / periods_per_year
            return money((principal + interest) / Decimal(n))
        r = annual_rate / periods_per_year
        if r == 0:
            return money(principal / Decimal(n))
        growth = (1 + r) ** n
        return money(principal * r * growth / (growth - 1))


def max_principal(payment: Decimal, annual_rate: Decimal, n: int,
                  periods_per_year: Decimal = Decimal(12),
                  interest_type: str = DECLINING_BALANCE) -> Decimal:
    """Largest principal whose installment does not exceed `payment` (inverse of installment())."""
    if payment <= 0 or n <= 0:
        return ZERO.quantize(CENT)
    with localcontext() as ctx:
        ctx.prec = 40
        if interest_type == FLAT:
            p = payment * Decimal(n) / (1 + annual_rate * Decimal(n) / periods_per_year)
        else:
            r = annual_rate / periods_per_year
            if r == 0:
                p = payment * Decimal(n)
            else:
                growth = (1 + r) ** n
                p = payment * (growth - 1) / (r * growth)
        return p.quantize(CENT, rounding=ROUND_DOWN)


# ---------------------------------------------------------------------------
# Policy and assessment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    version: str = "2026-10"
    max_dti: Decimal = Decimal("0.40")        # total debt payments / gross income
    refer_dti_band: Decimal = Decimal("0.05")  # DTI up to max+band -> REFER, above -> DECLINE
    min_credit_score: int = 600
    refer_credit_band: int = 30                # score down to min-band -> REFER
    min_dscr: Decimal = Decimal("1.25")        # only for business borrowers who report NOI
    dti_best: Decimal = Decimal("0.20")        # DTI at/below this scores 100 on the DTI component
    dti_worst: Decimal = Decimal("0.60")       # DTI at/above this scores 0
    credit_floor: int = 300
    credit_ceiling: int = 850
    credit_weight: Decimal = Decimal("0.5")    # risk score = w*credit + (1-w)*dti component

    @classmethod
    def from_dict(cls, d: dict) -> "Policy":
        conv = {k: (Decimal(str(v)) if isinstance(getattr(cls, k, None), Decimal) else v)
                for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**conv)


@dataclass
class Applicant:
    monthly_income: Optional[Decimal]
    existing_monthly_debt: Decimal = ZERO
    credit_score: Optional[int] = None
    monthly_business_noi: Optional[Decimal] = None   # net operating income, business loans


@dataclass
class LoanTerms:
    principal: Decimal
    annual_rate: Decimal          # fraction
    installments: int
    periods_per_year: Decimal = Decimal(12)
    interest_type: str = DECLINING_BALANCE
    scheduled_installment: Optional[Decimal] = None  # from Fineract's own schedule, if known


@dataclass
class Assessment:
    recommendation: str                # APPROVE | REFER | DECLINE
    risk_score: Decimal                # 0-100, higher = lower risk
    monthly_payment: Decimal
    dti: Optional[Decimal]
    dscr: Optional[Decimal]
    max_recommended_principal: Decimal
    notes: list[str] = field(default_factory=list)


def _clamp(x: Decimal, lo: Decimal = ZERO, hi: Decimal = Decimal(100)) -> Decimal:
    return max(lo, min(hi, x))


def assess(app: Applicant, loan: LoanTerms, policy: Policy = Policy()) -> Assessment:
    notes: list[str] = []
    decline, refer = False, False

    per_period = loan.scheduled_installment or installment(
        loan.principal, loan.annual_rate, loan.installments, loan.periods_per_year, loan.interest_type)
    monthly_payment = money(per_period * loan.periods_per_year / Decimal(12))

    # --- Missing data never auto-approves
    if app.monthly_income is None or app.monthly_income <= 0:
        return Assessment("REFER", ZERO, monthly_payment, None, None, ZERO.quantize(CENT),
                          ["Monthly income missing or zero: capture borrower financials first."])
    if app.credit_score is None:
        refer = True
        notes.append("No credit score recorded: manual credit check required.")

    # --- Debt-to-income
    total_debt = app.existing_monthly_debt + monthly_payment
    dti = (total_debt / app.monthly_income).quantize(Decimal("0.0001"))
    if dti > policy.max_dti + policy.refer_dti_band:
        decline = True
        notes.append(f"DTI {dti:.2%} is above the {policy.max_dti:.0%} limit by more than "
                     f"{policy.refer_dti_band:.0%}.")
    elif dti > policy.max_dti:
        refer = True
        notes.append(f"DTI {dti:.2%} slightly above the {policy.max_dti:.0%} limit.")

    # --- Credit score
    if app.credit_score is not None:
        if app.credit_score < policy.min_credit_score - policy.refer_credit_band:
            decline = True
            notes.append(f"Credit score {app.credit_score} well below minimum {policy.min_credit_score}.")
        elif app.credit_score < policy.min_credit_score:
            refer = True
            notes.append(f"Credit score {app.credit_score} just below minimum {policy.min_credit_score}.")

    # --- Debt service coverage (business borrowers)
    dscr = None
    if app.monthly_business_noi is not None and total_debt > 0:
        dscr = (app.monthly_business_noi / total_debt).quantize(Decimal("0.01"))
        if dscr < policy.min_dscr:
            refer = True
            notes.append(f"DSCR {dscr} below {policy.min_dscr}.")

    # --- Capacity: largest loan on the same terms that keeps DTI at the limit
    headroom_monthly = app.monthly_income * policy.max_dti - app.existing_monthly_debt
    headroom_per_period = headroom_monthly * Decimal(12) / loan.periods_per_year
    cap = max_principal(headroom_per_period, loan.annual_rate, loan.installments,
                        loan.periods_per_year, loan.interest_type)

    # --- Risk score (documented, linear, explainable)
    if app.credit_score is not None:
        span = Decimal(policy.credit_ceiling - policy.credit_floor)
        credit_pts = _clamp(Decimal(app.credit_score - policy.credit_floor) * 100 / span)
    else:
        credit_pts = ZERO
    dti_pts = _clamp((policy.dti_worst - dti) * 100 / (policy.dti_worst - policy.dti_best))
    w = policy.credit_weight
    score = (w * credit_pts + (1 - w) * dti_pts).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    if decline:
        rec = "DECLINE"
    elif refer:
        rec = "REFER"
    else:
        rec = "APPROVE"
        notes.append("Meets affordability and credit policy.")
    if loan.principal > cap and not decline:
        notes.append(f"Requested principal exceeds policy capacity of {cap:,.2f}; consider reducing.")

    return Assessment(rec, score, monthly_payment, dti, dscr, cap, notes)
