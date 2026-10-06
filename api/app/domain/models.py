"""API data shapes. Money is Decimal and travels as a string ("1318.74"); dates are ISO (yyyy-mm-dd)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

LoanState = Literal[
    "PENDING", "APPROVED", "REJECTED", "ACTIVE", "ARREARS", "ARREARS_LATE", "CLOSED", "WRITTEN_OFF", "WITHDRAWN"
]
Recommendation = Literal["APPROVE", "REFER", "DECLINE"]
InterestMethod = Literal["DECLINING_BALANCE", "FLAT"]
PaymentMethod = Literal["cash", "bank", "mobile", "payroll"]


class StaffUser(BaseModel):
    username: str
    display_name: str
    roles: list[str] = []


class Borrower(BaseModel):
    id: int
    name: str
    phone: str | None = None
    national_id: str | None = None
    employer: str | None = None
    address: str | None = None
    monthly_income: Decimal | None = None
    existing_monthly_debt: Decimal | None = None
    credit_score: int | None = None
    monthly_business_noi: Decimal | None = None
    income_verified: bool | None = None


class Installment(BaseModel):
    number: int
    due_date: date
    principal: Decimal
    interest: Decimal
    fees: Decimal = Decimal("0")
    total: Decimal
    paid: Decimal = Decimal("0")
    balance_after: Decimal
    complete: bool = False


class Assessment(BaseModel):
    recommendation: Recommendation
    risk_score: Decimal
    monthly_payment: Decimal
    dti: Decimal | None = None
    dscr: Decimal | None = None
    max_recommended_principal: Decimal
    max_dti: Decimal
    policy_version: str
    assessed_on: date
    notes: list[str] = []


class LoanSummary(BaseModel):
    id: int
    ref: str
    borrower_id: int
    borrower_name: str
    product: str
    principal: Decimal
    annual_rate: Decimal  # percent, e.g. 24.0
    term_months: int
    state: LoanState
    days_overdue: int = 0
    outstanding: Decimal = Decimal("0")
    overdue_amount: Decimal = Decimal("0")
    next_due_date: date | None = None
    next_due_amount: Decimal | None = None
    submitted_on: date | None = None
    recommendation: Recommendation | None = None


class Payment(BaseModel):
    paid_on: date
    amount: Decimal
    method: str


class LoanEvent(BaseModel):
    when: str
    text: str
    who: str | None = None


class LoanDetail(LoanSummary):
    interest_method: InterestMethod = "DECLINING_BALANCE"
    repayments_per_year: Decimal = Decimal(12)  # 12 monthly, 26 fortnightly, 52 weekly
    borrower: Borrower
    schedule: list[Installment] = []
    total_interest: Decimal = Decimal("0")
    assessment: Assessment | None = None
    history: list[LoanEvent] = []
    payments: list[Payment] = []
    payment_reference: str


class Dashboard(BaseModel):
    as_of: date
    gross_portfolio: Decimal
    active_loans: int
    disbursed_this_month: int
    par30_ratio: Decimal  # 0.068 = 6.8%
    due_today_amount: Decimal
    due_today_count: int
    collected_today_count: int
    pending_count: int
    arrears_buckets: list[ArrearsBucket]
    arrears_total: Decimal
    arrears_loans: int


class ArrearsBucket(BaseModel):
    label: str
    amount: Decimal
    loans: int


class CollectionItem(BaseModel):
    loan_id: int
    ref: str
    borrower_name: str
    phone: str | None
    state: LoanState
    days_overdue: int
    amount_due: Decimal
    note: str


class ApproveIn(BaseModel):
    amount: Decimal = Field(gt=0)
    note: str = Field(default="", max_length=1000)
    expected_disbursement: date | None = None


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class RepaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    method: PaymentMethod
    reference: str = Field(min_length=2, max_length=60)
    received_on: date


class Receipt(BaseModel):
    receipt_no: str
    loan_id: int
    ref: str
    borrower_name: str
    amount: Decimal
    method: PaymentMethod
    reference: str
    received_on: date
    sms_sent_to: str | None = None


class ActionResult(BaseModel):
    loan_id: int
    state: LoanState
    message: str


# --- Borrower portal ---------------------------------------------------------


class OtpRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=20)


class OtpVerify(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    code: str = Field(pattern=r"^\d{6}$")


class PayWay(BaseModel):
    name: str
    how: str


class PortalHome(BaseModel):
    first_name: str
    company_name: str
    loan: PortalLoan | None


class PortalLoan(BaseModel):
    ref: str
    borrowed: Decimal
    left_to_pay: Decimal
    payments_made: int
    payments_total: int
    next_due_date: date | None
    next_due_amount: Decimal | None
    days_overdue: int
    payment_reference: str
    ways_to_pay: list[PayWay]
    recent_payments: list[Payment]
    schedule: list[Installment]


class QuoteIn(BaseModel):
    amount: Decimal = Field(ge=200, le=50000)
    months: int = Field(ge=1, le=36)


class Quote(BaseModel):
    amount: Decimal
    months: int
    annual_rate: Decimal
    monthly_payment: Decimal
    total_repayable: Decimal
    total_interest: Decimal


class PortalApplicationIn(QuoteIn):
    monthly_income: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    existing_monthly_debt: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    purpose: str = Field(default="", max_length=200)


class PortalApplicationOut(BaseModel):
    ref: str
    amount: Decimal
    months: int
    monthly_payment: Decimal
    message: str


Dashboard.model_rebuild()
PortalHome.model_rebuild()
