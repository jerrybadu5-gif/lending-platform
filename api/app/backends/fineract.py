"""Apache Fineract 1.x back end (MCL_BACKEND=fineract).

Staff calls run with the signed-in staff member's own Fineract credential, so Fineract's
roles, permissions and maker-checker rules still apply. Portal calls run with a technical
user (MCL_FINERACT_PORTAL_USER) that should only have read-client, read-loan and
create-loan permissions.

Borrower financials and assessments live in the data tables created by
underwriting/bootstrap.py (dt_borrower_financials, dt_loan_assessment).
"""

from __future__ import annotations

import asyncio
import base64
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from ..config import Settings
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
from .base import AuthFailed, BackendError, NotFound, normalise_phone

ZERO = Decimal("0")
BORROWER_TABLE = "dt_borrower_financials"
ASSESSMENT_TABLE = "dt_loan_assessment"
DATE_FMT = {"locale": "en", "dateFormat": "yyyy-MM-dd"}
STATUS = {
    100: "PENDING",
    200: "APPROVED",
    300: "ACTIVE",
    400: "WITHDRAWN",
    500: "REJECTED",
    600: "CLOSED",
    601: "WRITTEN_OFF",
    602: "CLOSED",
    700: "CLOSED",
}
LIVE = {"ACTIVE", "ARREARS", "ARREARS_LATE"}


def fdate(v: Any) -> date | None:
    """Fineract dates come as [2026, 10, 6] or '2026-10-06'."""
    if not v:
        return None
    if isinstance(v, list | tuple):
        return date(int(v[0]), int(v[1]), int(v[2]))
    return date.fromisoformat(str(v)[:10])


def dec(v: Any) -> Decimal:
    return ZERO if v is None or v == "" else Decimal(str(v))


def fineract_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"Fineract returned HTTP {resp.status_code}."
    errors = body.get("errors") or []
    if errors and errors[0].get("defaultUserMessage"):
        return str(errors[0]["defaultUserMessage"])
    return str(
        body.get("defaultUserMessage") or body.get("developerMessage") or f"Fineract returned HTTP {resp.status_code}."
    )


class FineractBackend:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.http = client or httpx.AsyncClient(
            base_url=settings.fineract_url.rstrip("/") + "/fineract-provider/api/v1",
            headers={"Fineract-Platform-TenantId": settings.fineract_tenant, "Accept": "application/json"},
            verify=settings.fineract_verify_tls,
            timeout=30,
        )
        self._portal_key = base64.b64encode(
            f"{settings.fineract_portal_user}:{settings.fineract_portal_password}".encode()
        ).decode()
        self._payment_types: dict[str, int] | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._sem = asyncio.Semaphore(8)

    async def aclose(self) -> None:
        await self.http.aclose()

    # ------------------------------------------------------------------ http
    def _auth(self, cred: str) -> dict[str, str]:
        key = self._portal_key if cred == "portal" else cred
        return {"Authorization": f"Basic {key}"}

    async def _req(self, cred: str, method: str, path: str, body: dict | None = None) -> Any:
        async with self._sem:
            resp = await self.http.request(method, path, json=body, headers=self._auth(cred))
        if resp.status_code == 401:
            raise BackendError("Your session with Fineract has ended. Please sign in again.", 401)
        if resp.status_code == 403:
            raise BackendError(fineract_message(resp) or "You don't have permission to do this.", 403)
        if resp.status_code == 404:
            raise NotFound("That record")
        if resp.status_code >= 400:
            raise BackendError(fineract_message(resp), 422 if resp.status_code < 500 else 502)
        return resp.json() if resp.content else None

    async def _get(self, cred: str, path: str) -> Any:
        return await self._req(cred, "GET", path)

    async def _post(self, cred: str, path: str, body: dict) -> Any:
        return await self._req(cred, "POST", path, body)

    async def _cached(self, key: str, ttl: float, make):
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        value = await make()
        self._cache[key] = (time.monotonic(), value)
        return value

    def _invalidate(self) -> None:
        self._cache.clear()

    # ----------------------------------------------------------- mapping
    @staticmethod
    def _state(raw: dict, days: int) -> str:
        state = STATUS.get(int(raw.get("status", {}).get("id", 0)), "PENDING")
        if state == "ACTIVE" and days > 0:
            return "ARREARS_LATE" if days > 30 else "ARREARS"
        return state

    @staticmethod
    def _days_overdue(raw: dict, today: date) -> int:
        since = fdate((raw.get("summary") or {}).get("overdueSinceDate"))
        if since:
            return max((today - since).days, 0)
        return 1 if raw.get("inArrears") else 0

    def _summary(self, raw: dict, today: date, assessment: dict | None = None) -> LoanSummary:
        days = self._days_overdue(raw, today)
        summ = raw.get("summary") or {}
        tl = raw.get("timeline") or {}
        return LoanSummary(
            id=int(raw["id"]),
            ref=f"LN-{raw.get('accountNo', raw['id'])}",
            borrower_id=int(raw.get("clientId", 0)),
            borrower_name=raw.get("clientName", ""),
            product=raw.get("loanProductName", "Loan"),
            principal=dec(raw.get("approvedPrincipal") or raw.get("principal") or raw.get("proposedPrincipal")),
            annual_rate=dec(raw.get("annualInterestRate")),
            term_months=int(raw.get("numberOfRepayments") or 0),
            state=self._state(raw, days),
            days_overdue=days,
            outstanding=dec(summ.get("totalOutstanding")),
            overdue_amount=dec(summ.get("totalOverdue")),
            submitted_on=fdate(tl.get("submittedOnDate")),
            recommendation=(assessment or {}).get("recommendation"),
        )

    async def _all_loans(self, cred: str) -> list[dict]:
        out, offset = [], 0
        while True:
            page = await self._get(cred, f"/loans?offset={offset}&limit=200&orderBy=id&sortOrder=DESC")
            items = page.get("pageItems", [])
            out.extend(items)
            offset += 200
            if not items or offset >= page.get("totalFilteredRecords", 0):
                return out

    async def _datatable(self, cred: str, table: str, entity_id: int) -> dict | None:
        try:
            rows = await self._get(cred, f"/datatables/{table}/{entity_id}?genericResultSet=false")
        except NotFound:
            return None
        return rows[0] if rows else None

    async def _upsert(self, cred: str, table: str, entity_id: int, values: dict) -> None:
        body = {
            **DATE_FMT,
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in values.items() if v is not None},
        }
        if await self._datatable(cred, table, entity_id):
            await self._req(cred, "PUT", f"/datatables/{table}/{entity_id}", body)
        else:
            await self._post(cred, f"/datatables/{table}/{entity_id}", body)

    # -------------------------------------------------------------- staff
    async def authenticate(self, username: str, password: str) -> tuple[StaffUser, str]:
        resp = await self.http.post("/authentication", json={"username": username, "password": password})
        if resp.status_code in (400, 401, 403):
            raise AuthFailed()
        if resp.status_code >= 400:
            raise BackendError("Fineract is not answering. Try again in a minute.", 502)
        body = resp.json()
        if not body.get("authenticated", True):
            raise AuthFailed()
        roles = [r.get("name", "") for r in body.get("roles", [])]
        return (
            StaffUser(
                username=body.get("username", username),
                display_name=body.get("staffDisplayName") or body.get("username", username),
                roles=roles,
            ),
            body["base64EncodedAuthenticationKey"],
        )

    async def list_loans(self, cred: str, today: date, states: set[str] | None = None) -> list[LoanSummary]:
        raws = await self._all_loans(cred)
        out = [self._summary(r, today) for r in raws]
        if states:
            out = [s for s in out if s.state in states]
        if states == {"PENDING"}:  # show the recommendation in the approvals list
            for s in out:
                a = await self._datatable(cred, ASSESSMENT_TABLE, s.id)
                s.recommendation = (a or {}).get("recommendation")
        return out

    async def _schedule(self, cred: str, loan_id: int) -> tuple[dict, list[Installment]]:
        raw = await self._get(cred, f"/loans/{loan_id}?associations=repaymentSchedule,transactions")
        inst = []
        for p in (raw.get("repaymentSchedule") or {}).get("periods", []):
            if not p.get("period"):
                continue
            total = dec(p.get("totalDueForPeriod"))
            inst.append(
                Installment(
                    number=int(p["period"]),
                    due_date=fdate(p["dueDate"]),
                    principal=dec(p.get("principalDue") or p.get("principalOriginalDue")),
                    interest=dec(p.get("interestDue")),
                    fees=dec(p.get("feeChargesDue")) + dec(p.get("penaltyChargesDue")),
                    total=total,
                    paid=dec(p.get("totalPaidForPeriod")),
                    balance_after=dec(p.get("principalLoanBalanceOutstanding")),
                    complete=bool(p.get("complete")),
                )
            )
        return raw, inst

    async def get_loan(self, cred: str, loan_id: int, today: date) -> LoanDetail:
        raw, inst = await self._schedule(cred, loan_id)
        client_id = int(raw["clientId"])
        client, fin, ids, a = await asyncio.gather(
            self._get(cred, f"/clients/{client_id}"),
            self._datatable(cred, BORROWER_TABLE, client_id),
            self._get(cred, f"/clients/{client_id}/identifiers"),
            self._datatable(cred, ASSESSMENT_TABLE, loan_id),
        )
        fin = fin or {}
        borrower = Borrower(
            id=client_id,
            name=client.get("displayName", ""),
            phone=normalise_phone(client.get("mobileNo") or "") or None,
            national_id=(ids[0].get("documentKey") if ids else None),
            employer=fin.get("income_source"),
            monthly_income=dec(fin["monthly_income"]) if fin.get("monthly_income") is not None else None,
            existing_monthly_debt=dec(fin.get("existing_monthly_debt")),
            credit_score=int(fin["credit_score"]) if fin.get("credit_score") not in (None, "") else None,
            monthly_business_noi=dec(fin["monthly_business_noi"])
            if fin.get("monthly_business_noi") not in (None, "")
            else None,
            income_verified=fin.get("income_verified"),
        )
        s = self._summary(raw, today, a)
        unpaid = [i for i in inst if not i.complete]
        nxt = unpaid[0] if unpaid and s.state in LIVE else None
        assessment = None
        if a:
            assessment = Assessment(
                recommendation=a["recommendation"],
                risk_score=dec(a.get("risk_score")),
                monthly_payment=dec(a.get("monthly_payment")),
                dti=dec(a["dti"]) if a.get("dti") is not None else None,
                dscr=dec(a["dscr"]) if a.get("dscr") is not None else None,
                max_recommended_principal=dec(a.get("max_recommended_principal")),
                max_dti=Decimal("0.40"),
                policy_version=a.get("policy_version", ""),
                assessed_on=fdate(a.get("assessed_on")) or today,
                notes=[n for n in (a.get("notes") or "").split(" | ") if n],
            )
        tl = raw.get("timeline") or {}
        events = [
            (tl.get("submittedOnDate"), "Application submitted", tl.get("submittedByUsername")),
            (tl.get("approvedOnDate"), "Approved", tl.get("approvedByUsername")),
            (tl.get("rejectedOnDate"), "Rejected", tl.get("rejectedByUsername")),
            (tl.get("actualDisbursementDate"), "Disbursed", tl.get("disbursedByUsername")),
            (tl.get("closedOnDate"), "Closed", tl.get("closedByUsername")),
        ]
        history = [LoanEvent(when=fdate(d).isoformat(), text=t, who=w) for d, t, w in events if fdate(d)]  # type: ignore[union-attr]
        payments = [
            Payment(
                paid_on=fdate(t["date"]),
                amount=dec(t.get("amount")),
                method=((t.get("paymentDetailData") or {}).get("paymentType") or {}).get("name", "Repayment"),
            )
            for t in reversed(raw.get("transactions") or [])
            if (t.get("type") or {}).get("repayment") and not t.get("manuallyReversed")
        ]
        return LoanDetail(
            **s.model_dump(exclude={"next_due_date", "next_due_amount"}),
            next_due_date=nxt.due_date if nxt else None,
            next_due_amount=(nxt.total - nxt.paid) if nxt else None,
            interest_method="FLAT" if (raw.get("interestType") or {}).get("id") == 1 else "DECLINING_BALANCE",
            borrower=borrower,
            schedule=inst,
            total_interest=sum((i.interest for i in inst), ZERO),
            assessment=assessment,
            history=list(reversed(history)),
            payments=payments,
            payment_reference=f"BL{raw.get('accountNo', loan_id)}",
        )

    async def save_assessment(self, cred: str, loan_id: int, assessment: Assessment) -> None:
        await self._upsert(
            cred,
            ASSESSMENT_TABLE,
            loan_id,
            {
                "recommendation": assessment.recommendation,
                "risk_score": assessment.risk_score,
                "monthly_payment": assessment.monthly_payment,
                "dti": assessment.dti,
                "dscr": assessment.dscr,
                "max_recommended_principal": assessment.max_recommended_principal,
                "policy_version": assessment.policy_version,
                "assessed_on": assessment.assessed_on.isoformat(),
                "notes": " | ".join(assessment.notes),
            },
        )
        self._invalidate()

    @staticmethod
    def _pending_checker(result: Any) -> bool:
        """Fineract answers a maker-checker action with a commandId and no change yet."""
        return isinstance(result, dict) and bool(result.get("commandId")) and not result.get("changes")

    async def approve(self, cred: str, loan_id: int, body: ApproveIn, today: date) -> ActionResult:
        result = await self._post(
            cred,
            f"/loans/{loan_id}?command=approve",
            {
                **DATE_FMT,
                "approvedOnDate": today.isoformat(),
                "approvedLoanAmount": str(body.amount),
                "expectedDisbursementDate": (body.expected_disbursement or today + timedelta(days=1)).isoformat(),
                "note": body.note,
            },
        )
        self._invalidate()
        if self._pending_checker(result):
            return ActionResult(
                loan_id=loan_id, state="PENDING", message="Approval saved. A second approver must confirm it."
            )
        return ActionResult(loan_id=loan_id, state="APPROVED", message=f"Loan approved for K {body.amount:,.2f}.")

    async def reject(self, cred: str, loan_id: int, body: RejectIn, today: date) -> ActionResult:
        await self._post(
            cred,
            f"/loans/{loan_id}?command=reject",
            {**DATE_FMT, "rejectedOnDate": today.isoformat(), "note": body.note},
        )
        self._invalidate()
        return ActionResult(loan_id=loan_id, state="REJECTED", message="Application rejected.")

    async def disburse(self, cred: str, loan_id: int, today: date) -> ActionResult:
        result = await self._post(
            cred, f"/loans/{loan_id}?command=disburse", {**DATE_FMT, "actualDisbursementDate": today.isoformat()}
        )
        self._invalidate()
        if self._pending_checker(result):
            return ActionResult(
                loan_id=loan_id, state="APPROVED", message="Disbursement saved. A second approver must confirm it."
            )
        return ActionResult(loan_id=loan_id, state="ACTIVE", message="Loan disbursed.")

    async def _live_with_schedules(self, cred: str, today: date) -> list[tuple[dict, list[Installment]]]:
        async def build():
            live = [r for r in await self._all_loans(cred) if int(r.get("status", {}).get("id", 0)) == 300]
            return await asyncio.gather(*(self._schedule(cred, int(r["id"])) for r in live))

        return await self._cached(f"live:{cred[:12]}:{today}", 60, build)

    async def dashboard(self, cred: str, today: date) -> Dashboard:
        raws = await self._all_loans(cred)
        live = await self._live_with_schedules(cred, today)
        gross = par30 = due_amt = ZERO
        due_n = collected = disbursed = 0
        buckets: dict[str, list] = {
            "1–30 days": [ZERO, 0],
            "31–60 days": [ZERO, 0],
            "61–90 days": [ZERO, 0],
            "Over 90 days": [ZERO, 0],
        }
        for raw, inst in live:
            p_out = dec((raw.get("summary") or {}).get("principalOutstanding"))
            gross += p_out
            days = self._days_overdue(raw, today)
            if days > 30:
                par30 += p_out
            if days:
                key = (
                    "1–30 days"
                    if days <= 30
                    else "31–60 days"
                    if days <= 60
                    else "61–90 days"
                    if days <= 90
                    else "Over 90 days"
                )
                buckets[key][0] += p_out
                buckets[key][1] += 1
            d = fdate((raw.get("timeline") or {}).get("actualDisbursementDate"))
            disbursed += 1 if d and (d.year, d.month) == (today.year, today.month) else 0
            for i in inst:
                if i.due_date == today:
                    due_n += 1
                    due_amt += i.total
                    collected += 1 if i.complete else 0
        arrears = [ArrearsBucket(label=k, amount=v[0], loans=v[1]) for k, v in buckets.items()]
        return Dashboard(
            as_of=today,
            gross_portfolio=gross,
            active_loans=len(live),
            disbursed_this_month=disbursed,
            par30_ratio=(par30 / gross).quantize(Decimal("0.0001")) if gross else ZERO,
            due_today_amount=due_amt,
            due_today_count=due_n,
            collected_today_count=collected,
            pending_count=sum(1 for r in raws if int(r.get("status", {}).get("id", 0)) == 100),
            arrears_buckets=arrears,
            arrears_total=sum((a.amount for a in arrears), ZERO),
            arrears_loans=sum(a.loans for a in arrears),
        )

    async def collections(self, cred: str, today: date) -> list[CollectionItem]:
        out = []
        for raw, inst in await self._live_with_schedules(cred, today):
            days = self._days_overdue(raw, today)
            overdue = sum((i.total - i.paid for i in inst if not i.complete and i.due_date < today), ZERO)
            due_today = sum((i.total - i.paid for i in inst if not i.complete and i.due_date == today), ZERO)
            if overdue + due_today <= 0:
                continue
            out.append(
                CollectionItem(
                    loan_id=int(raw["id"]),
                    ref=f"LN-{raw.get('accountNo', raw['id'])}",
                    borrower_name=raw.get("clientName", ""),
                    phone=None,
                    state=self._state(raw, days),
                    days_overdue=days,
                    amount_due=overdue + due_today,
                    note=f"{days} days overdue" if days else "installment due today",
                )
            )
        return sorted(out, key=lambda c: (-c.days_overdue, c.borrower_name))

    async def _payment_type_id(self, cred: str, method: str) -> int:
        if self._payment_types is None:
            types = await self._get(cred, "/paymenttypes")
            self._payment_types = {t["name"].strip().lower(): int(t["id"]) for t in types}
        name = self.s.payment_types.get(method, method)
        if name.lower() not in self._payment_types:
            raise BackendError(
                f'Add a payment type called "{name}" in Fineract (Admin > Organization > '
                "Payment types), then try again.",
                422,
            )
        return self._payment_types[name.lower()]

    async def record_repayment(self, cred: str, loan_id: int, body: RepaymentIn, today: date) -> Receipt:
        if body.received_on > today:
            raise BackendError("The date received can't be in the future.", 422)
        type_id = await self._payment_type_id(cred, body.method)
        result = await self._post(
            cred,
            f"/loans/{loan_id}/transactions?command=repayment",
            {
                **DATE_FMT,
                "transactionDate": body.received_on.isoformat(),
                "transactionAmount": str(body.amount),
                "paymentTypeId": type_id,
                "receiptNumber": body.reference,
                "note": f"Recorded in McLender ({body.method})",
            },
        )
        self._invalidate()
        detail = await self.get_loan(cred, loan_id, today)
        return Receipt(
            receipt_no=f"RC-{(result or {}).get('resourceId', '')}",
            loan_id=loan_id,
            ref=detail.ref,
            borrower_name=detail.borrower.name,
            amount=body.amount,
            method=body.method,
            reference=body.reference,
            received_on=body.received_on,
            sms_sent_to=detail.borrower.phone,
        )

    # ------------------------------------------------------------- portal
    async def find_borrower_by_phone(self, phone: str) -> Borrower | None:
        p = normalise_phone(phone)
        hits = await self._get("portal", f"/search?query={p}&resource=clients&exactMatch=false")
        for h in hits or []:
            if h.get("entityType", "").upper() != "CLIENT":
                continue
            client = await self._get("portal", f"/clients/{int(h['entityId'])}")
            if normalise_phone(client.get("mobileNo") or "") == p:
                return Borrower(id=int(client["id"]), name=client.get("displayName", ""), phone=p)
        return None

    async def borrower_loans(self, borrower_id: int, today: date) -> list[LoanDetail]:
        accounts = await self._get("portal", f"/clients/{borrower_id}/accounts")
        ids = [int(a["id"]) for a in (accounts or {}).get("loanAccounts", [])]
        return [await self.get_loan("portal", i, today) for i in ids]

    async def submit_application(self, borrower_id: int, body: PortalApplicationIn, today: date) -> LoanSummary:
        pid = self.s.portal_product_id
        tpl = await self._get(
            "portal", f"/loans/template?templateType=individual&clientId={borrower_id}&productId={pid}"
        )
        await self._upsert(
            "portal",
            BORROWER_TABLE,
            borrower_id,
            {
                "monthly_income": body.monthly_income,
                "existing_monthly_debt": body.existing_monthly_debt,
                "income_verified": False,
            },
        )
        result = await self._post(
            "portal",
            "/loans",
            {
                **DATE_FMT,
                "loanType": "individual",
                "clientId": borrower_id,
                "productId": pid,
                "principal": str(body.amount),
                "loanTermFrequency": body.months,
                "loanTermFrequencyType": 2,
                "numberOfRepayments": body.months,
                "repaymentEvery": 1,
                "repaymentFrequencyType": 2,
                "interestRatePerPeriod": tpl.get("interestRatePerPeriod"),
                "amortizationType": (tpl.get("amortizationType") or {}).get("id", 1),
                "interestType": (tpl.get("interestType") or {}).get("id", 0),
                "interestCalculationPeriodType": (tpl.get("interestCalculationPeriodType") or {}).get("id", 1),
                "transactionProcessingStrategyCode": tpl.get(
                    "transactionProcessingStrategyCode", "mifos-standard-strategy"
                ),
                "submittedOnDate": today.isoformat(),
                "expectedDisbursementDate": (today + timedelta(days=7)).isoformat(),
            },
        )
        self._invalidate()
        raw = await self._get("portal", f"/loans/{int(result['loanId'])}")
        return self._summary(raw, today)
