"""Apache Fineract 1.x back end (MCL_BACKEND=fineract).

Staff calls run with the signed-in staff member's own Fineract credential, so Fineract's
roles, permissions and maker-checker rules still apply. Portal calls run with a technical
user (MCL_FINERACT_PORTAL_USER). Give its role only these permissions:
READ_CLIENT, READ_CLIENTIDENTIFIER (finding a borrower by phone uses client search),
READ_LOAN, CREATE_LOAN, READ_LOANPRODUCT, and READ/CREATE/UPDATE on the data tables
dt_borrower_financials and dt_loan_assessment. It needs no access to dt_borrower_profile
(bank and next-of-kin details), so the portal never reads them.

Borrower financials, profile (address, employer, bank, next of kin) and assessments live in
the data tables created by underwriting/bootstrap.py. KYC files are Fineract client documents,
with the McLender document kind (id, payslip, ...) as the document name.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import time
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal
from typing import Any, cast
from urllib.parse import quote

import httpx

from ..config import Settings
from ..deps import local_zone as _local_zone
from ..domain.models import (
    DOCUMENT_LABELS,
    ActionResult,
    ApplicationIn,
    ApproveIn,
    ArrearsBucket,
    Assessment,
    BankAccount,
    Borrower,
    BorrowerDocument,
    BorrowerIn,
    BorrowerListItem,
    CollectionItem,
    Dashboard,
    DisburseIn,
    DocumentKind,
    Installment,
    LoanDetail,
    LoanEvent,
    LoanState,
    LoanSummary,
    NextOfKin,
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
PROFILE_TABLE = "dt_borrower_profile"
ASSESSMENT_TABLE = "dt_loan_assessment"
DATE_FMT = {"locale": "en", "dateFormat": "yyyy-MM-dd"}
STATUS: dict[int, LoanState] = {
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
log = logging.getLogger("mclender.fineract")


def fdate(v: Any) -> date | None:
    """Fineract dates come as [2026, 10, 6] or '2026-10-06'."""
    if not v:
        return None
    if isinstance(v, list | tuple):
        return date(int(v[0]), int(v[1]), int(v[2]))
    return date.fromisoformat(str(v)[:10])


def req_date(v: Any, what: str) -> date:
    """A date Fineract must always send; a missing one means the response is not what we expect."""
    d = fdate(v)
    if d is None:
        raise BackendError(f"Fineract sent a {what} without a date.")
    return d


# repaymentFrequencyType id -> repayments per year when repaymentEvery is 1
FREQUENCY_PER_YEAR = {0: Decimal(365), 1: Decimal(52), 2: Decimal(12), 3: Decimal(1)}


def repayments_per_year(raw: dict) -> Decimal:
    ftype = int((raw.get("repaymentFrequencyType") or {}).get("id", 2))
    every = max(int(raw.get("repaymentEvery") or 1), 1)
    return FREQUENCY_PER_YEAR.get(ftype, Decimal(12)) / every


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
        self._zone = _local_zone(settings.timezone)

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

    async def _send(self, cred: str, method: str, path: str, accept: str = "*/*", **kw: Any) -> httpx.Response:
        """A request whose body or answer isn't JSON (file upload or download). Fineract answers a file
        download only as application/octet-stream, so the client's default Accept: application/json
        would get 406 Not Acceptable."""
        async with self._sem:
            resp = await self.http.request(method, path, headers={**self._auth(cred), "Accept": accept}, **kw)
        if resp.status_code == 401:
            raise BackendError("Your session with Fineract has ended. Please sign in again.", 401)
        if resp.status_code == 404:
            raise NotFound("That document")
        if resp.status_code >= 400:
            raise BackendError(fineract_message(resp), resp.status_code if resp.status_code < 500 else 502)
        return resp

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
    def _state(raw: dict, days: int) -> LoanState:
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

    async def _upsert(self, cred: str, table: str, entity_id: int, values: dict, clear_empty: bool = False) -> None:
        """Create or update a data table row. With clear_empty, None values are sent as null so a field
        the user emptied is cleared in Fineract (otherwise None means "leave as it is")."""
        body = {
            **DATE_FMT,
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in values.items() if v is not None or clear_empty},
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
        pending = [s for s in out if s.state == "PENDING"]  # show the recommendation in the approvals list
        found = await asyncio.gather(*(self._datatable(cred, ASSESSMENT_TABLE, s.id) for s in pending))
        for s, a in zip(pending, found, strict=True):
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
                    due_date=req_date(p.get("dueDate"), "repayment schedule line"),
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
        borrower, a, notes = await asyncio.gather(
            self._borrower(cred, client_id),
            self._datatable(cred, ASSESSMENT_TABLE, loan_id),
            self._loan_notes(cred, loan_id),
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
        # Fineract's timeline has dates only. Within a day: submitted and approved come before that day's notes
        # (contact, signed copy), which come before a disbursement, rejection or closing.
        rank = {"Application submitted": 0, "Approved": 1, "Rejected": 3, "Disbursed": 3, "Closed": 4}
        keyed = [
            ((fdate(d).isoformat(), rank[t], ""), LoanEvent(when=fdate(d).isoformat(), text=t, who=w))  # type: ignore[union-attr]
            for d, t, w in events
            if fdate(d)
        ] + [((e.when, 2, order), e) for order, e in notes]
        history = [e for _, e in sorted(keyed, key=lambda pair: pair[0])]
        payments = [
            Payment(
                id=int(t["id"]) if t.get("id") is not None else None,
                paid_on=req_date(t.get("date"), "repayment"),
                amount=dec(t.get("amount")),
                method=((t.get("paymentDetailData") or {}).get("paymentType") or {}).get("name", "Repayment"),
                reference=(t.get("paymentDetailData") or {}).get("receiptNumber"),
            )
            for t in reversed(raw.get("transactions") or [])
            if (t.get("type") or {}).get("repayment") and not t.get("manuallyReversed")
        ]
        return LoanDetail(
            **s.model_dump(exclude={"next_due_date", "next_due_amount"}),
            next_due_date=nxt.due_date if nxt else None,
            next_due_amount=(nxt.total - nxt.paid) if nxt else None,
            interest_method="FLAT" if (raw.get("interestType") or {}).get("id") == 1 else "DECLINING_BALANCE",
            repayments_per_year=repayments_per_year(raw),
            approved_on=fdate(tl.get("approvedOnDate")),
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
        result = await self._post(
            cred,
            f"/loans/{loan_id}?command=reject",
            {**DATE_FMT, "rejectedOnDate": today.isoformat(), "note": body.note},
        )
        self._invalidate()
        if self._pending_checker(result):
            return ActionResult(
                loan_id=loan_id, state="PENDING", message="Rejection saved. A second approver must confirm it."
            )
        return ActionResult(loan_id=loan_id, state="REJECTED", message="Application rejected.")

    async def disburse(self, cred: str, loan_id: int, body: DisburseIn, today: date) -> ActionResult:
        details: dict[str, Any] = {
            "paymentTypeId": await self._payment_type_id(cred, body.method),
            "receiptNumber": body.reference,
            "note": f"Paid out in McLender ({body.method}), reference {body.reference}",
        }
        if body.account:
            details["accountNumber"] = body.account
        result = await self._post(
            cred,
            f"/loans/{loan_id}?command=disburse",
            {**DATE_FMT, "actualDisbursementDate": today.isoformat(), **details},
        )
        self._invalidate()
        if self._pending_checker(result):
            return ActionResult(
                loan_id=loan_id, state="APPROVED", message="Disbursement saved. A second approver must confirm it."
            )
        return ActionResult(loan_id=loan_id, state="ACTIVE", message="Loan disbursed.")

    async def _loan_notes(self, cred: str, loan_id: int) -> list[tuple[str, LoanEvent]]:
        """Loan notes (contact log, signed agreement, purpose) for the loan's history, each with a sort key
        (full timestamp, then id). Never blocks loading a loan: notes are extra information."""
        if cred == "portal":  # borrowers don't see the loan history, and the portal user can't read notes
            return []
        try:
            raws = await self._get(cred, f"/loans/{loan_id}/notes")
        except BackendError as e:
            log.warning("Could not read notes for loan %s: %s", loan_id, e.message)
            return []
        out = []
        for n in raws or []:
            text = (n.get("note") or "").strip()
            when = _note_time(n.get("createdOn"), self._zone)
            # Skip notes McLender writes on transactions; the transactions show in history already.
            if not text or when is None or text.startswith(("Recorded in McLender", "Paid out in McLender")):
                continue
            order = f"{when.isoformat()}#{int(n.get('id') or 0):012d}"
            out.append((order, LoanEvent(when=when.date().isoformat(), text=text, who=n.get("createdByUsername"))))
        return out

    async def add_loan_note(self, cred: str, loan_id: int, text: str, today: date) -> None:
        await self._post(cred, f"/loans/{loan_id}/notes", {"note": text[:1000]})

    async def list_loan_documents(self, cred: str, loan_id: int) -> list[BorrowerDocument]:
        raws = await self._get(cred, f"/loans/{loan_id}/documents")
        return sorted((self._document(r) for r in raws or []), key=lambda d: d.id, reverse=True)

    async def add_loan_document(
        self, cred: str, loan_id: int, kind: str, file_name: str, content_type: str, data: bytes, today: date
    ) -> BorrowerDocument:
        resp = await self._send(
            cred,
            "POST",
            f"/loans/{loan_id}/documents",
            data={"name": kind, "description": f"McLender upload {today.isoformat()}"},
            files={"file": (file_name, data, content_type)},
        )
        return BorrowerDocument(
            id=int(resp.json()["resourceId"]),
            kind=cast(DocumentKind, kind),
            file_name=file_name,
            content_type=content_type,
            size=len(data),
            uploaded_on=today,
        )

    async def get_loan_document(self, cred: str, loan_id: int, doc_id: int) -> tuple[BorrowerDocument, bytes]:
        meta = await self._get(cred, f"/loans/{loan_id}/documents/{doc_id}")
        resp = await self._send(cred, "GET", f"/loans/{loan_id}/documents/{doc_id}/attachment")
        return self._document(meta), resp.content

    async def _live_with_schedules(self, cred: str, today: date) -> list[tuple[dict, list[Installment]]]:
        async def build():
            live = [r for r in await self._all_loans(cred) if int(r.get("status", {}).get("id", 0)) == 300]
            return await asyncio.gather(*(self._schedule(cred, int(r["id"])) for r in live))

        # Key by a hash of the whole credential: a prefix of it could be shared by two users.
        who = hashlib.sha256(cred.encode()).hexdigest()
        return await self._cached(f"live:{who}:{today}", 60, build)

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
            payment_id=int(result["resourceId"]) if (result or {}).get("resourceId") else None,
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
        return await self._submit_loan("portal", borrower_id, body.amount, body.months, today)

    async def _submit_loan(self, cred: str, borrower_id: int, amount: Decimal, months: int, today: date) -> LoanSummary:
        pid = self.s.portal_product_id
        tpl = await self._get(cred, f"/loans/template?templateType=individual&clientId={borrower_id}&productId={pid}")
        result = await self._post(
            cred,
            "/loans",
            {
                **DATE_FMT,
                "loanType": "individual",
                "clientId": borrower_id,
                "productId": pid,
                "principal": str(amount),
                "loanTermFrequency": months,
                "loanTermFrequencyType": 2,
                "numberOfRepayments": months,
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
        raw = await self._get(cred, f"/loans/{int(result['loanId'])}")
        return self._summary(raw, today)

    # ---------------------------------------------------------- borrowers
    async def _borrower(self, cred: str, client_id: int) -> Borrower:
        client, fin, ids, prof = await asyncio.gather(
            self._get(cred, f"/clients/{client_id}"),
            self._datatable(cred, BORROWER_TABLE, client_id),
            self._get(cred, f"/clients/{client_id}/identifiers"),
            self._profile(cred, client_id),
        )
        fin, prof = fin or {}, prof or {}
        nid = next((i for i in ids or [] if _is_nid((i.get("documentType") or {}).get("name", ""))), None)
        nid = nid or (ids[0] if ids else None)
        gender = ((client.get("gender") or {}).get("name") or "").strip().lower()
        bank = None
        if prof.get("bank_name") and prof.get("bank_account_number"):
            bank = BankAccount(
                bank=prof["bank_name"],
                branch=prof.get("bank_branch") or None,
                account_name=prof.get("bank_account_name") or client.get("displayName", ""),
                account_number=prof["bank_account_number"],
            )
        nok = None
        if prof.get("nok_name") and prof.get("nok_phone"):
            nok = NextOfKin(
                name=prof["nok_name"], relationship=prof.get("nok_relationship") or "-", phone=prof["nok_phone"]
            )
        return Borrower(
            id=client_id,
            name=client.get("displayName", ""),
            phone=normalise_phone(client.get("mobileNo") or "") or None,
            national_id=nid.get("documentKey") if nid else None,
            employer=prof.get("employer") or fin.get("income_source"),
            address=prof.get("address"),
            date_of_birth=fdate(client.get("dateOfBirth")),
            gender="female" if gender.startswith("f") else "male" if gender.startswith("m") else None,
            payroll_number=prof.get("payroll_number"),
            bank=bank,
            next_of_kin=nok,
            monthly_income=dec(fin["monthly_income"]) if fin.get("monthly_income") is not None else None,
            existing_monthly_debt=dec(fin.get("existing_monthly_debt")),
            credit_score=int(fin["credit_score"]) if fin.get("credit_score") not in (None, "") else None,
            monthly_business_noi=dec(fin["monthly_business_noi"])
            if fin.get("monthly_business_noi") not in (None, "")
            else None,
            income_verified=fin.get("income_verified"),
        )

    async def _profile(self, cred: str, client_id: int) -> dict | None:
        try:
            return await self._datatable(cred, PROFILE_TABLE, client_id)
        except BackendError as e:
            if e.status == 403:  # the portal user may not read bank and next-of-kin details
                return None
            raise

    async def _code_values(self, cred: str, code_name: str) -> dict[str, int]:
        async def load() -> dict[str, int]:
            codes = await self._get(cred, "/codes")
            code = next((c for c in codes if c.get("name", "").lower() == code_name.lower()), None)
            if not code:
                return {}
            values = await self._get(cred, f"/codes/{code['id']}/codevalues")
            return {v["name"].strip().lower(): int(v["id"]) for v in values}

        return await self._cached(f"code:{code_name}", 600, load)

    async def search_borrowers(self, cred: str, query: str, limit: int = 50) -> list[BorrowerListItem]:
        q = query.strip()
        if not q:
            page = await self._get(cred, f"/clients?limit={limit}&orderBy=displayName&sortOrder=ASC")
            return [
                BorrowerListItem(id=int(c["id"]), name=c.get("displayName", ""), phone=c.get("mobileNo"))
                for c in page.get("pageItems", [])
            ]
        hits = await self._get(cred, f"/search?query={quote(q)}&resource=clients,clientIdentifiers&exactMatch=false")
        out: dict[int, BorrowerListItem] = {}
        for h in hits or []:
            kind = (h.get("entityType") or "").upper()
            cid = int(h["entityId"]) if kind == "CLIENT" else int(h.get("parentId") or 0)
            if not cid or cid in out:
                continue
            name = h.get("entityName") if kind == "CLIENT" else h.get("parentName")
            out[cid] = BorrowerListItem(
                id=cid,
                name=name or "",
                phone=h.get("entityMobileNo") if kind == "CLIENT" else None,
                national_id=h.get("entityName") if kind != "CLIENT" else None,
            )
        return list(out.values())[:limit]

    async def get_borrower(self, cred: str, borrower_id: int) -> Borrower:
        return await self._borrower(cred, borrower_id)

    def _client_body(self, body: BorrowerIn, gender_id: int | None) -> dict:
        out: dict[str, Any] = {
            **DATE_FMT,
            "firstname": body.first_name,
            "lastname": body.last_name,
            "mobileNo": normalise_phone(body.phone),
            "dateOfBirth": body.date_of_birth.isoformat(),
        }
        if gender_id:
            out["genderId"] = gender_id
        return out

    async def _gender_id(self, cred: str, gender: str) -> int | None:
        values = await self._code_values(cred, "Gender")
        return next((v for k, v in values.items() if k.startswith(gender[0])), None)

    async def _nid_type(self, cred: str) -> int:
        types = await self._code_values(cred, "Customer Identifier")
        type_id = next((v for k, v in types.items() if _is_nid(k)), None)
        if type_id is None:
            raise BackendError(
                'Add a "National ID (NID)" value to the Customer Identifier code in Fineract '
                "(Admin > System > Manage codes), then try again.",
                422,
            )
        return type_id

    async def _check_unique(self, cred: str, body: BorrowerIn, except_id: int | None = None) -> None:
        """Refuse a phone number or NID that another borrower already has, naming them, before anything
        is written (Fineract would otherwise create the client and then refuse the identifier)."""
        phone = normalise_phone(body.phone)
        hits = await self._get(cred, f"/search?query={quote(phone)}&resource=clients&exactMatch=false")
        for h in hits or []:
            cid = int(h.get("entityId") or 0)
            if (h.get("entityType") or "").upper() != "CLIENT" or cid == except_id:
                continue
            client = await self._get(cred, f"/clients/{cid}")
            if normalise_phone(client.get("mobileNo") or "") == phone:
                raise BackendError(
                    f"{client.get('displayName', 'Another borrower')} already has phone number {phone}.", 409
                )
        if body.national_id:
            key = _nid_key(body.national_id)
            hits = await self._get(
                cred, f"/search?query={quote(body.national_id)}&resource=clientIdentifiers&exactMatch=false"
            )
            for h in hits or []:
                owner = int(h.get("parentId") or 0)
                if owner and owner != except_id and _nid_key(h.get("entityName") or "") == key:
                    raise BackendError(
                        f"{h.get('parentName', 'Another borrower')} already has NID number {body.national_id}.", 409
                    )

    async def _save_details(self, cred: str, client_id: int, body: BorrowerIn, new: bool) -> None:
        if body.national_id:
            type_id = await self._nid_type(cred)
            existing = [] if new else await self._get(cred, f"/clients/{client_id}/identifiers")
            current = next((i for i in existing if (i.get("documentType") or {}).get("id") == type_id), None)
            ident = {"documentTypeId": type_id, "documentKey": body.national_id, "status": "Active"}
            if current is None:
                await self._post(cred, f"/clients/{client_id}/identifiers", ident)
            elif current.get("documentKey") != body.national_id:
                await self._req(cred, "PUT", f"/clients/{client_id}/identifiers/{current['id']}", ident)
        bank, nok = body.bank, body.next_of_kin
        await self._upsert(
            cred,
            PROFILE_TABLE,
            client_id,
            {
                "address": body.address,
                "employer": body.employer,
                "payroll_number": body.payroll_number,
                "bank_name": bank.bank if bank else None,
                "bank_branch": bank.branch if bank else None,
                "bank_account_name": bank.account_name if bank else None,
                "bank_account_number": bank.account_number if bank else None,
                "nok_name": nok.name if nok else None,
                "nok_relationship": nok.relationship if nok else None,
                "nok_phone": normalise_phone(nok.phone) if nok else None,
            },
            clear_empty=True,  # removing a bank account or next of kin in McLender must remove it here too
        )
        if body.monthly_income is not None:
            await self._upsert(
                cred,
                BORROWER_TABLE,
                client_id,
                {
                    "monthly_income": body.monthly_income,
                    "existing_monthly_debt": body.existing_monthly_debt,
                    "income_source": body.employer,
                },
            )

    async def create_borrower(self, cred: str, body: BorrowerIn, today: date) -> Borrower:
        await self._check_unique(cred, body)
        if body.national_id:
            await self._nid_type(cred)  # fail before creating anything if the NID type isn't set up
        result = await self._post(
            cred,
            "/clients",
            {
                **self._client_body(body, await self._gender_id(cred, body.gender)),
                "officeId": 1,
                "legalFormId": 1,
                "active": True,
                "activationDate": today.isoformat(),
                "submittedOnDate": today.isoformat(),
            },
        )
        client_id = int(result.get("clientId") or result["resourceId"])
        try:
            await self._save_details(cred, client_id, body, new=True)
        except BackendError as e:
            raise BackendError(
                f"The borrower was created (number {client_id}) but some details weren't saved: {e.message} "
                "Open the borrower and save again.",
                e.status,
            ) from e
        self._invalidate()
        return await self._borrower(cred, client_id)

    async def update_borrower(self, cred: str, borrower_id: int, body: BorrowerIn) -> Borrower:
        await self._check_unique(cred, body, except_id=borrower_id)
        await self._req(
            cred, "PUT", f"/clients/{borrower_id}", self._client_body(body, await self._gender_id(cred, body.gender))
        )
        await self._save_details(cred, borrower_id, body, new=False)
        self._invalidate()
        return await self._borrower(cred, borrower_id)

    async def borrower_loan_list(self, cred: str, borrower_id: int, today: date) -> list[LoanSummary]:
        accounts = await self._get(cred, f"/clients/{borrower_id}/accounts")
        ids = [int(a["id"]) for a in (accounts or {}).get("loanAccounts", [])]
        raws = await asyncio.gather(*(self._get(cred, f"/loans/{i}") for i in ids))
        return sorted((self._summary(r, today) for r in raws), key=lambda s: s.id, reverse=True)

    @staticmethod
    def _document(raw: dict) -> BorrowerDocument:
        kind = (raw.get("name") or "").strip().lower()
        found = re.search(r"\d{4}-\d{2}-\d{2}", raw.get("description") or "")
        return BorrowerDocument(
            id=int(raw["id"]),
            kind=cast(DocumentKind, kind if kind in DOCUMENT_LABELS else "other"),
            file_name=raw.get("fileName") or "document",
            content_type=raw.get("type") or "application/octet-stream",
            size=int(raw.get("size") or 0),
            uploaded_on=date.fromisoformat(found.group(0)) if found else None,
        )

    async def list_documents(self, cred: str, borrower_id: int) -> list[BorrowerDocument]:
        raws = await self._get(cred, f"/clients/{borrower_id}/documents")
        return sorted((self._document(r) for r in raws or []), key=lambda d: d.id, reverse=True)

    async def add_document(
        self, cred: str, borrower_id: int, kind: str, file_name: str, content_type: str, data: bytes, today: date
    ) -> BorrowerDocument:
        resp = await self._send(
            cred,
            "POST",
            f"/clients/{borrower_id}/documents",
            data={"name": kind, "description": f"McLender upload {today.isoformat()}"},
            files={"file": (file_name, data, content_type)},
        )
        doc_id = int(resp.json()["resourceId"])
        return BorrowerDocument(
            id=doc_id,
            kind=cast(DocumentKind, kind),
            file_name=file_name,
            content_type=content_type,
            size=len(data),
            uploaded_on=today,
        )

    async def get_document(self, cred: str, borrower_id: int, doc_id: int) -> tuple[BorrowerDocument, bytes]:
        meta = await self._get(cred, f"/clients/{borrower_id}/documents/{doc_id}")
        resp = await self._send(cred, "GET", f"/clients/{borrower_id}/documents/{doc_id}/attachment")
        return self._document(meta), resp.content

    async def create_application(self, cred: str, borrower_id: int, body: ApplicationIn, today: date) -> LoanSummary:
        accounts = await self._get(cred, f"/clients/{borrower_id}/accounts")
        if any(int((a.get("status") or {}).get("id", 0)) == 100 for a in (accounts or {}).get("loanAccounts", [])):
            raise BackendError("This borrower already has an application waiting for a decision.", 409)
        summary = await self._submit_loan(cred, borrower_id, body.amount, body.months, today)
        if body.purpose:
            try:
                await self._post(cred, f"/loans/{summary.id}/notes", {"note": f"Purpose: {body.purpose}"})
            except BackendError as e:  # the application stands even if the note can't be saved
                log.warning("Could not save the purpose note on loan %s: %s", summary.id, e.message)
        return summary


def _note_time(v: Any, zone: tzinfo) -> datetime | None:
    """A note's creation time in local (Port Moresby) time. Fineract stores it in UTC and sends it as
    epoch milliseconds, an ISO date-time, or [y, m, d, h, min, s], depending on version. A date alone
    is taken as that local day."""
    try:
        if isinstance(v, int | float):
            return datetime.fromtimestamp(v / 1000, tz=UTC).astimezone(zone)
        if isinstance(v, list | tuple) and len(v) >= 3:
            if len(v) < 4:
                return datetime(int(v[0]), int(v[1]), int(v[2]), 12, tzinfo=zone)
            y, mo, d, h, mi, sec = ([int(x) for x in v[:6]] + [0, 0, 0])[:6]
            return datetime(y, mo, d, h, mi, sec, tzinfo=UTC).astimezone(zone)
        if isinstance(v, str) and v:
            if len(v) <= 10:
                return datetime.fromisoformat(v).replace(hour=12, tzinfo=zone)
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(zone)
    except (ValueError, TypeError):
        return None
    return None


def _nid_key(nid: str) -> str:
    return "".join(c for c in nid if c.isalnum()).lower()


def _is_nid(name: str) -> bool:
    n = name.lower()
    return "national" in n or "nid" in n
