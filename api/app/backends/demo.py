"""In-memory demo back end with sample Breez Lending data, dated relative to today.

Used for development, demos and tests (MCL_BACKEND=demo). Nothing is saved: a restart
resets the data. Staff log in as demo / demo (credit manager) or officer / officer.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..domain.models import (
    ActionResult,
    ApproveIn,
    ArrearsBucket,
    Assessment,
    Borrower,
    CollectionItem,
    Dashboard,
    Installment,
    LoanDetail,
    LoanEvent,
    LoanSummary,
    Payment,
    PortalApplicationIn,
    Receipt,
    RejectIn,
    RepaymentIn,
    StaffUser,
)
from ..domain.risk import DECLINING_BALANCE, FLAT
from ..domain.schedule import Row, add_months, monthly_schedule
from .base import AuthFailed, BackendError, NotFound, normalise_phone

ZERO = Decimal("0")
D = Decimal

STAFF = {
    "demo": ("demo", StaffUser(username="demo", display_name="Grace Pokana", roles=["Credit manager"])),
    "officer": ("officer", StaffUser(username="officer", display_name="John Kerema", roles=["Loan officer"])),
}

METHOD_NAMES = {"cash": "Cash", "bank": "Bank transfer", "mobile": "Mobile money", "payroll": "Payroll deduction"}

PRODUCTS = {
    "personal": ("Personal loan", D("24"), DECLINING_BALANCE),
    "advance": ("Salary advance", D("30"), FLAT),
    "business": ("Small business loan", D("28"), DECLINING_BALANCE),
    "legacy": ("Personal loan", D("10"), DECLINING_BALANCE),
}


@dataclass
class Pay:
    on: date
    amount: Decimal
    method: str
    reference: str


@dataclass
class DemoLoan:
    id: int
    borrower_id: int
    product: str
    principal: Decimal
    months: int
    state: str  # PENDING | APPROVED | REJECTED | ACTIVE | CLOSED
    submitted_on: date
    disbursed_on: date | None = None
    first_due: date | None = None
    payments: list[Pay] = field(default_factory=list)
    assessment: Assessment | None = None
    history: list[LoanEvent] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return f"LN-{self.id:06d}"

    @property
    def rate(self) -> Decimal:
        return PRODUCTS[self.product][1]

    @property
    def method(self) -> str:
        return PRODUCTS[self.product][2]

    def rows(self, today: date) -> list[Row]:
        first = self.first_due or add_months(today, 1)
        return monthly_schedule(self.principal, self.rate, self.months, first, self.method)


class DemoBackend:
    def __init__(self, today: date):
        self._ids = itertools.count(549)
        self._receipts = itertools.count(419)
        self.borrowers: dict[int, Borrower] = {}
        self.loans: dict[int, DemoLoan] = {}
        self._seed(today)

    async def aclose(self) -> None:
        return None

    # ----------------------------------------------------------------- seed
    def _seed(self, t: date) -> None:
        b = [
            (
                1,
                "Mary Kila",
                "70123344",
                "2009 1182 4410",
                "Department of Health",
                "Section 92, Lot 7, Gordons, NCD",
                "5000",
                "400",
                680,
            ),
            (
                2,
                "Samuel Kiap",
                "72550198",
                "2014 0091 2276",
                "Kiap Trading (own business)",
                "Lot 15, Boroko, NCD",
                "9800",
                "600",
                720,
            ),
            (3, "Ruth Kaupa", "71896620", "2017 7720 1904", "Waigani Supermarket", "Erima, NCD", "1900", "0", 640),
            (
                4,
                "Andrew Moka",
                "74612290",
                "2012 4400 9981",
                "PNG Ports Corporation",
                "Hohola, NCD",
                "4600",
                "250",
                655,
            ),
            (
                5,
                "Lucy Gumuno",
                "73901182",
                "2010 3388 1290",
                "Self-employed, market vendor",
                "Gerehu Stage 4, NCD",
                "2600",
                "0",
                610,
            ),
            (6, "Thomas Aisi", "70448811", "2008 2211 7765", "Contract driver", "Morata, NCD", "3100", "900", 590),
            (7, "Grace Tom", "71558802", "2015 6612 0034", "Bank South Pacific", "Tokarara, NCD", "6200", "500", 745),
            (
                8,
                "Peter Wambi",
                "71234567",
                "2011 0488 7712",
                "Lae Port Services Ltd, 6 years",
                "Section 12, Lot 4, Gerehu Stage 2, NCD",
                "4000",
                "360",
                700,
            ),
            (
                9,
                "Daniel Oa",
                "72019944",
                "2013 9902 1188",
                "Oa Hardware (own business)",
                "Badili, NCD",
                "12500",
                "1800",
                690,
            ),
            (10, "Joyce Ilave", "74220876", "2016 3301 5527", "Casual worker", "Six Mile, NCD", "1800", "650", 560),
        ]
        for i, name, phone, nid, emp, addr, inc, debt, score in b:
            self.borrowers[i] = Borrower(
                id=i,
                name=name,
                phone=phone,
                national_id=nid,
                employer=emp,
                address=addr,
                monthly_income=D(inc),
                existing_monthly_debt=D(debt),
                credit_score=score,
                income_verified=True,
            )
        self.borrowers[2].monthly_business_noi = D("4200")
        self.borrowers[9].monthly_business_noi = D("3900")

        def active(id_: int, bid: int, product: str, principal: str, months: int, paid: int, first_unpaid_due: date):
            first_due = add_months(first_unpaid_due, -paid)
            loan = DemoLoan(
                id_,
                bid,
                product,
                D(principal),
                months,
                "ACTIVE",
                first_due - timedelta(days=35),
                disbursed_on=add_months(first_due, -1),
                first_due=first_due,
            )
            for r in loan.rows(t)[:paid]:
                loan.payments.append(Pay(r.due_date, r.total, "bank", f"BSP-{id_}-{r.number}"))
            loan.history = [LoanEvent(when=add_months(first_due, -1).isoformat(), text="Disbursed", who="Grace Pokana")]
            self.loans[id_] = loan

        active(482, 1, "legacy", "15000", 12, 6, t)  # installment 7 due today
        active(455, 2, "business", "40000", 24, 2, t)  # installment 3 due today
        active(498, 3, "advance", "1200", 2, 1, t)  # final payment due today
        active(517, 4, "personal", "12000", 12, 3, t - timedelta(days=12))
        active(431, 5, "personal", "9000", 12, 5, t - timedelta(days=26))
        active(402, 6, "personal", "20000", 18, 4, t - timedelta(days=47))
        active(470, 7, "personal", "5000", 6, 2, t + timedelta(days=9))
        active(388, 9, "business", "25000", 24, 15, t + timedelta(days=4))

        def pending(id_: int, bid: int, product: str, principal: str, months: int, days_ago: int):
            loan = DemoLoan(id_, bid, product, D(principal), months, "PENDING", t - timedelta(days=days_ago))
            loan.history = [
                LoanEvent(
                    when=loan.submitted_on.isoformat(), text="Application submitted", who="John Kerema, loan officer"
                )
            ]
            self.loans[id_] = loan

        pending(533, 7, "personal", "8000", 12, 2)
        pending(536, 8, "personal", "15000", 12, 1)
        pending(538, 3, "advance", "1200", 2, 1)
        pending(541, 9, "business", "30000", 24, 3)
        pending(542, 10, "personal", "6500", 6, 0)

    # ----------------------------------------------------------- derived
    def _installments(self, loan: DemoLoan, today: date) -> list[Installment]:
        paid_pool = sum((p.amount for p in loan.payments), ZERO)
        out: list[Installment] = []
        for r in loan.rows(today):
            pay = min(paid_pool, r.total)
            paid_pool -= pay
            out.append(
                Installment(
                    number=r.number,
                    due_date=r.due_date,
                    principal=r.principal,
                    interest=r.interest,
                    total=r.total,
                    paid=pay,
                    balance_after=r.balance_after,
                    complete=pay >= r.total,
                )
            )
        return out

    def _summary(self, loan: DemoLoan, today: date) -> LoanSummary:
        b = self.borrowers[loan.borrower_id]
        inst = self._installments(loan, today) if loan.state in ("ACTIVE", "CLOSED") else []
        unpaid = [i for i in inst if not i.complete]
        overdue = [i for i in unpaid if i.due_date < today]
        days = (today - overdue[0].due_date).days if overdue else 0
        state = loan.state
        if state == "ACTIVE" and days:
            state = "ARREARS_LATE" if days > 30 else "ARREARS"
        nxt = unpaid[0] if unpaid else None
        return LoanSummary(
            id=loan.id,
            ref=loan.ref,
            borrower_id=b.id,
            borrower_name=b.name,
            product=PRODUCTS[loan.product][0],
            principal=loan.principal,
            annual_rate=loan.rate,
            term_months=loan.months,
            state=state,
            days_overdue=days,
            outstanding=sum((i.total - i.paid for i in unpaid), ZERO),
            overdue_amount=sum((i.total - i.paid for i in overdue), ZERO),
            next_due_date=nxt.due_date if nxt else None,
            next_due_amount=(nxt.total - nxt.paid) if nxt else None,
            submitted_on=loan.submitted_on,
            recommendation=loan.assessment.recommendation if loan.assessment else None,
        )

    def _principal_outstanding(self, loan: DemoLoan, today: date) -> Decimal:
        inst = self._installments(loan, today)
        paid_principal = sum((i.principal for i in inst if i.complete), ZERO)
        return loan.principal - paid_principal

    def _loan(self, loan_id: int) -> DemoLoan:
        if loan_id not in self.loans:
            raise NotFound(f"Loan {loan_id}")
        return self.loans[loan_id]

    # -------------------------------------------------------------- staff
    async def authenticate(self, username: str, password: str) -> tuple[StaffUser, str]:
        entry = STAFF.get(username.strip().lower())
        if not entry or entry[0] != password:
            raise AuthFailed()
        return entry[1], f"demo:{username}"

    async def dashboard(self, cred: str, today: date) -> Dashboard:
        sums = [self._summary(l, today) for l in self.loans.values()]
        live = [
            (l, s)
            for l, s in zip(self.loans.values(), sums, strict=True)
            if s.state in ("ACTIVE", "ARREARS", "ARREARS_LATE")
        ]
        gross = sum((self._principal_outstanding(l, today) for l, _ in live), ZERO)
        par30 = sum((self._principal_outstanding(l, today) for l, s in live if s.days_overdue > 30), ZERO)
        due_amt, due_n, collected = ZERO, 0, 0
        for l, _ in live:
            for i in self._installments(l, today):
                if i.due_date == today:
                    due_n += 1
                    due_amt += i.total
                    collected += 1 if i.complete else 0
        buckets = [("1–30 days", 1, 30), ("31–60 days", 31, 60), ("61–90 days", 61, 90), ("Over 90 days", 91, 10**6)]
        arrears = [
            ArrearsBucket(
                label=lab,
                amount=sum(
                    (self._principal_outstanding(l, today) for l, s in live if lo <= s.days_overdue <= hi), ZERO
                ),
                loans=sum(1 for _, s in live if lo <= s.days_overdue <= hi),
            )
            for lab, lo, hi in buckets
        ]
        return Dashboard(
            as_of=today,
            gross_portfolio=gross,
            active_loans=len(live),
            disbursed_this_month=sum(
                1
                for l, _ in live
                if l.disbursed_on and l.disbursed_on.year == today.year and l.disbursed_on.month == today.month
            ),
            par30_ratio=(par30 / gross).quantize(D("0.0001")) if gross else ZERO,
            due_today_amount=due_amt,
            due_today_count=due_n,
            collected_today_count=collected,
            pending_count=sum(1 for s in sums if s.state == "PENDING"),
            arrears_buckets=arrears,
            arrears_total=sum((a.amount for a in arrears), ZERO),
            arrears_loans=sum(a.loans for a in arrears),
        )

    async def list_loans(self, cred: str, today: date, states: set[str] | None = None) -> list[LoanSummary]:
        out = [self._summary(l, today) for l in self.loans.values()]
        if states:
            out = [s for s in out if s.state in states]
        return sorted(out, key=lambda s: (s.submitted_on or today, s.id), reverse=True)

    async def get_loan(self, cred: str, loan_id: int, today: date) -> LoanDetail:
        loan = self._loan(loan_id)
        s = self._summary(loan, today)
        inst = self._installments(loan, today)
        return LoanDetail(
            **s.model_dump(),
            interest_method=loan.method,
            borrower=self.borrowers[loan.borrower_id],
            schedule=inst,
            total_interest=sum((i.interest for i in inst), ZERO),
            assessment=loan.assessment,
            history=list(reversed(loan.history)),
            payment_reference=f"BL{loan.id}",
            payments=[
                Payment(paid_on=p.on, amount=p.amount, method=METHOD_NAMES.get(p.method, p.method))
                for p in reversed(loan.payments)
            ],
        )

    async def save_assessment(self, cred: str, loan_id: int, assessment: Assessment) -> None:
        loan = self._loan(loan_id)
        loan.assessment = assessment
        loan.history.append(
            LoanEvent(
                when=assessment.assessed_on.isoformat(),
                text=f"Underwriting ({assessment.policy_version}): "
                f"{assessment.recommendation.title()}, score {assessment.risk_score}",
                who="system",
            )
        )

    async def approve(self, cred: str, loan_id: int, body: ApproveIn, today: date) -> ActionResult:
        loan = self._loan(loan_id)
        if loan.state != "PENDING":
            raise BackendError("Only loans pending approval can be approved.", 409)
        if body.amount > loan.principal:
            raise BackendError("The approved amount can't be more than the amount applied for.", 422)
        loan.principal = body.amount
        loan.state = "APPROVED"
        loan.history.append(
            LoanEvent(
                when=today.isoformat(),
                text=f"Approved for K {body.amount:,.2f}. {body.note}".strip(),
                who=cred.removeprefix("demo:"),
            )
        )
        return ActionResult(loan_id=loan_id, state="APPROVED", message=f"{loan.ref} approved for K {body.amount:,.2f}.")

    async def reject(self, cred: str, loan_id: int, body: RejectIn, today: date) -> ActionResult:
        loan = self._loan(loan_id)
        if loan.state != "PENDING":
            raise BackendError("Only loans pending approval can be rejected.", 409)
        loan.state = "REJECTED"
        loan.history.append(
            LoanEvent(when=today.isoformat(), text=f"Rejected. {body.note}", who=cred.removeprefix("demo:"))
        )
        return ActionResult(loan_id=loan_id, state="REJECTED", message=f"{loan.ref} rejected.")

    async def disburse(self, cred: str, loan_id: int, today: date) -> ActionResult:
        loan = self._loan(loan_id)
        if loan.state != "APPROVED":
            raise BackendError("Only approved loans can be disbursed.", 409)
        loan.state, loan.disbursed_on, loan.first_due = "ACTIVE", today, add_months(today, 1)
        loan.history.append(
            LoanEvent(when=today.isoformat(), text=f"Disbursed K {loan.principal:,.2f}", who=cred.removeprefix("demo:"))
        )
        return ActionResult(loan_id=loan_id, state="ACTIVE", message=f"{loan.ref} disbursed.")

    async def collections(self, cred: str, today: date) -> list[CollectionItem]:
        out = []
        for loan in self.loans.values():
            s = self._summary(loan, today)
            if s.state not in ("ACTIVE", "ARREARS", "ARREARS_LATE"):
                continue
            due_today = sum(
                (i.total - i.paid for i in self._installments(loan, today) if i.due_date == today and not i.complete),
                ZERO,
            )
            amount = s.overdue_amount + due_today
            if amount <= 0:
                continue
            b = self.borrowers[loan.borrower_id]
            note = f"{s.days_overdue} days overdue" if s.days_overdue else "installment due today"
            out.append(
                CollectionItem(
                    loan_id=loan.id,
                    ref=loan.ref,
                    borrower_name=b.name,
                    phone=b.phone,
                    state=s.state,
                    days_overdue=s.days_overdue,
                    amount_due=amount,
                    note=note,
                )
            )
        return sorted(out, key=lambda c: (-c.days_overdue, c.borrower_name))

    async def record_repayment(self, cred: str, loan_id: int, body: RepaymentIn, today: date) -> Receipt:
        loan = self._loan(loan_id)
        s = self._summary(loan, today)
        if s.state not in ("ACTIVE", "ARREARS", "ARREARS_LATE"):
            raise BackendError("Repayments can only be recorded on active loans.", 409)
        if body.received_on > today:
            raise BackendError("The date received can't be in the future.", 422)
        if body.amount > s.outstanding:
            raise BackendError(f"That is more than the K {s.outstanding:,.2f} still owed on {loan.ref}.", 422)
        loan.payments.append(Pay(body.received_on, body.amount, body.method, body.reference))
        if self._summary(loan, today).outstanding == 0:
            loan.state = "CLOSED"
        b = self.borrowers[loan.borrower_id]
        receipt = f"RC-{today:%Y-%m}-{next(self._receipts):04d}"
        loan.history.append(
            LoanEvent(
                when=body.received_on.isoformat(),
                text=f"Repayment K {body.amount:,.2f} by {body.method}, receipt {receipt}",
                who=cred.removeprefix("demo:"),
            )
        )
        return Receipt(
            receipt_no=receipt,
            loan_id=loan.id,
            ref=loan.ref,
            borrower_name=b.name,
            amount=body.amount,
            method=body.method,
            reference=body.reference,
            received_on=body.received_on,
            sms_sent_to=b.phone,
        )

    # ------------------------------------------------------------- portal
    async def find_borrower_by_phone(self, phone: str) -> Borrower | None:
        p = normalise_phone(phone)
        return next((b for b in self.borrowers.values() if b.phone == p), None)

    async def borrower_loans(self, borrower_id: int, today: date) -> list[LoanDetail]:
        return [await self.get_loan("portal", l.id, today) for l in self.loans.values() if l.borrower_id == borrower_id]

    async def submit_application(self, borrower_id: int, body: PortalApplicationIn, today: date) -> LoanSummary:
        b = self.borrowers.get(borrower_id)
        if not b:
            raise NotFound("Borrower")
        if any(l.borrower_id == borrower_id and l.state == "PENDING" for l in self.loans.values()):
            raise BackendError("You already have an application waiting. We'll call you about it soon.", 409)
        b.monthly_income, b.existing_monthly_debt, b.income_verified = (
            body.monthly_income,
            body.existing_monthly_debt,
            False,
        )
        loan = DemoLoan(next(self._ids), borrower_id, "personal", body.amount, body.months, "PENDING", today)
        loan.history = [
            LoanEvent(when=today.isoformat(), text="Application submitted in the borrower portal", who=b.name)
        ]
        self.loans[loan.id] = loan
        return self._summary(loan, today)
