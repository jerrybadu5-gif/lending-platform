"""PDF documents: loan agreement, repayment schedule, loan statement and payment receipt.

Built with ReportLab (pure Python, no system libraries), A4, Helvetica. Amounts as "K 1,234.56",
dates as dd/mm/yyyy. Every page carries the company name and a footer with the page number.

The loan agreement wording is a DRAFT for a Papua New Guinea lawyer to review. Until
MCL_AGREEMENT_REVIEWED=true, every page of it says so.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .domain.models import Installment, LoanDetail, Payment, PayWay

BRAND = colors.HexColor("#0b5d57")
BRAND_DEEP = colors.HexColor("#0f2a28")
INK_MUTED = colors.HexColor("#4f5d5a")
LINE = colors.HexColor("#d5dbd8")
SOFT = colors.HexColor("#eef5f3")
WARN = colors.HexColor("#8a1c1c")

DRAFT_NOTE = "DRAFT TEMPLATE - wording not yet reviewed by a lawyer. Do not give to borrowers."

STATE_WORDS = {
    "PENDING": "Waiting for approval",
    "APPROVED": "Approved, not yet paid out",
    "ACTIVE": "Active",
    "ARREARS": "Active, payment overdue",
    "ARREARS_LATE": "Active, more than 30 days overdue",
    "CLOSED": "Paid off",
    "WRITTEN_OFF": "Written off",
    "REJECTED": "Not approved",
    "WITHDRAWN": "Withdrawn",
}


@dataclass(frozen=True)
class Company:
    name: str
    address: str
    phone: str = ""
    email: str = ""


def kina(v: Decimal | int | float | None) -> str:
    if v is None:
        return "-"
    return f"K {Decimal(v):,.2f}"


def dmy(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "-"


# ------------------------------------------------------------------ styles
_base = getSampleStyleSheet()
S = {
    "title": ParagraphStyle(
        "title",
        _base["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=BRAND_DEEP,
        alignment=0,
        spaceAfter=2 * mm,
    ),
    "h2": ParagraphStyle(
        "h2",
        _base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=BRAND_DEEP,
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    ),
    "body": ParagraphStyle("body", _base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13),
    "small": ParagraphStyle(
        "small", _base["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=INK_MUTED
    ),
    "clause": ParagraphStyle(
        "clause",
        _base["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        leftIndent=7 * mm,
        firstLineIndent=-7 * mm,
        spaceAfter=2 * mm,
    ),
    "big": ParagraphStyle(
        "big", _base["BodyText"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=BRAND
    ),
    "right": ParagraphStyle(
        "right", _base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, alignment=TA_RIGHT
    ),
    "warn": ParagraphStyle(
        "warn",
        _base["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=WARN,
        borderColor=WARN,
        borderWidth=0.8,
        borderPadding=6,
        spaceBefore=2 * mm,
        spaceAfter=4 * mm,
    ),
}


def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(text: str, style: str = "body") -> Paragraph:  # noqa: N802 - reads like the ReportLab flowable
    return Paragraph(text, S[style])


def _grid(
    rows: Sequence[Sequence[Any]],
    widths: Sequence[float],
    header: bool = True,
    right_cols: Sequence[int] = (),
    total_row: bool = False,
) -> Table:
    t = Table([list(r) for r in rows], colWidths=list(widths), repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DEEP),
        ]
    for c in right_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if total_row:
        style += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5), ("LINEABOVE", (0, -1), (-1, -1), 0.8, BRAND)]
    t.setStyle(TableStyle(style))
    return t


def _pairs(rows: Sequence[tuple[str, Any]], width: float = 170 * mm) -> Table:
    """Label / value list, two to a row."""
    cells = [
        [P(f"<font color='#4f5d5a'>{_esc(k)}</font>", "body"), P(_esc(v) if v not in (None, "") else "-")]
        for k, v in rows
    ]
    t = Table(cells, colWidths=[width * 0.38, width * 0.62])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return t


def _build(story: list, company: Company, title: str, today: date, draft: bool = False) -> bytes:
    buf = io.BytesIO()

    def frame(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(BRAND)
        canvas.rect(0, h - 6 * mm, w, 6 * mm, stroke=0, fill=1)
        canvas.setFillColor(BRAND_DEEP)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(18 * mm, h - 17 * mm, company.name)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK_MUTED)
        contact = " | ".join(x for x in (company.phone, company.email) if x)
        canvas.drawRightString(w - 18 * mm, h - 14 * mm, company.address[:95])
        if contact:
            canvas.drawRightString(w - 18 * mm, h - 18 * mm, contact)
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, h - 22 * mm, w - 18 * mm, h - 22 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, 10 * mm, f"{title} - printed {dmy(today)} by McLender")
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Page {doc.page}")
        if draft:
            canvas.setFillColor(WARN)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawCentredString(w / 2, 15 * mm, DRAFT_NOTE)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=28 * mm,
        bottomMargin=22 * mm,
        title=title,
        author=company.name,
        creator="McLender",
    )
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


def _schedule_table(schedule: Sequence[Installment], show_paid: bool) -> Table:
    head = (
        ["No.", "Due date", "Principal", "Interest", "Fees", "Payment"]
        + (["Paid"] if show_paid else [])
        + ["Balance after"]
    )
    rows: list[list[Any]] = [head]
    for i in schedule:
        row = [str(i.number), dmy(i.due_date), kina(i.principal), kina(i.interest), kina(i.fees), kina(i.total)]
        if show_paid:
            row.append(kina(i.paid))
        rows.append(row + [kina(i.balance_after)])
    tot = (
        [
            "",
            "Total",
            kina(sum((i.principal for i in schedule), Decimal(0))),
            kina(sum((i.interest for i in schedule), Decimal(0))),
            kina(sum((i.fees for i in schedule), Decimal(0))),
            kina(sum((i.total for i in schedule), Decimal(0))),
        ]
        + ([kina(sum((i.paid for i in schedule), Decimal(0)))] if show_paid else [])
        + [""]
    )
    rows.append(tot)
    widths = [10 * mm, 22 * mm, 23 * mm, 21 * mm, 16 * mm, 23 * mm] + ([21 * mm] if show_paid else []) + [24 * mm]
    right = list(range(2, len(head)))
    return _grid(rows, widths, right_cols=right, total_row=True)


def _loan_facts(loan: LoanDetail) -> list[tuple[str, Any]]:
    method = "flat rate" if loan.interest_method == "FLAT" else "reducing balance"
    first = loan.schedule[0] if loan.schedule else None
    return [
        ("Loan number", loan.ref),
        ("Borrower", loan.borrower.name),
        ("Product", loan.product),
        ("Amount", kina(loan.principal)),
        ("Interest rate", f"{loan.annual_rate:.2f}% a year, {method}"),
        ("Repayments", f"{len(loan.schedule) or loan.term_months} x {kina(first.total) if first else '-'}"),
        ("Payment reference", loan.payment_reference),
        ("Status", STATE_WORDS.get(loan.state, loan.state)),
    ]


# ---------------------------------------------------------------- documents
def repayment_schedule(loan: LoanDetail, company: Company, today: date) -> bytes:
    story: list = [
        P("Repayment schedule", "title"),
        _pairs(_loan_facts(loan)),
        P("Payments", "h2"),
        _schedule_table(loan.schedule, show_paid=loan.state not in ("PENDING", "APPROVED")),
        Spacer(1, 4 * mm),
        P(
            f"Always quote your payment reference <b>{_esc(loan.payment_reference)}</b> so we can match your "
            "payment. Dates that fall on a weekend or public holiday are due the next working day.",
            "small",
        ),
    ]
    return _build(story, company, f"Repayment schedule {loan.ref}", today)


def statement(loan: LoanDetail, company: Company, today: date, ways: Sequence[PayWay]) -> bytes:
    paid = sum((p.amount for p in loan.payments), Decimal(0))
    story: list = [
        P(f"Loan statement as at {dmy(today)}", "title"),
        _pairs(
            [
                ("Loan number", loan.ref),
                ("Borrower", loan.borrower.name),
                ("Amount borrowed", kina(loan.principal)),
                ("Total paid to date", kina(paid)),
                ("Left to pay", kina(loan.outstanding)),
                (
                    "Overdue now",
                    kina(loan.overdue_amount) + (f" ({loan.days_overdue} days)" if loan.days_overdue else ""),
                ),
                (
                    "Next payment",
                    f"{kina(loan.next_due_amount)} on {dmy(loan.next_due_date)}" if loan.next_due_date else "-",
                ),
                ("Status", STATE_WORDS.get(loan.state, loan.state)),
            ]
        ),
        P("Payments received", "h2"),
    ]
    if loan.payments:
        rows: list[list[Any]] = [["Date", "Method", "Reference", "Amount"]]
        rows += [
            [dmy(p.paid_on), p.method, p.reference or "-", kina(p.amount)]
            for p in sorted(loan.payments, key=lambda p: p.paid_on)
        ]
        rows.append(["", "", "Total", kina(paid)])
        story.append(_grid(rows, [28 * mm, 50 * mm, 55 * mm, 37 * mm], right_cols=[3], total_row=True))
    else:
        story.append(P("No payments yet."))
    story += [P("How to pay", "h2")]
    story += [P(f"<b>{_esc(w.name)}</b>: {_esc(w.how)}") for w in ways]
    story += [Spacer(1, 4 * mm), P("If anything on this statement looks wrong, contact us within 30 days.", "small")]
    return _build(story, company, f"Statement {loan.ref}", today)


def receipt(loan: LoanDetail, payment: Payment, company: Company, today: date) -> bytes:
    number = f"RC-{payment.id}" if payment.id else "-"
    story: list = [
        P("Payment receipt", "title"),
        P(kina(payment.amount), "big"),
        Spacer(1, 3 * mm),
        _pairs(
            [
                ("Receipt number", number),
                ("Date received", dmy(payment.paid_on)),
                ("Received from", loan.borrower.name),
                ("For loan", loan.ref),
                ("Paid by", payment.method),
                ("Payment reference", payment.reference or "-"),
                ("Left to pay on this loan (today)", kina(loan.outstanding)),
            ]
        ),
        Spacer(1, 6 * mm),
        P("Thank you. Keep this receipt as proof of payment.", "small"),
    ]
    return _build(story, company, f"Receipt {number}", today)


def loan_agreement(
    loan: LoanDetail, company: Company, today: date, ways: Sequence[PayWay], reviewed: bool = False
) -> bytes:
    b = loan.borrower
    first = loan.schedule[0] if loan.schedule else None
    last = loan.schedule[-1] if loan.schedule else None
    total = sum((i.total for i in loan.schedule), Decimal(0))
    fees = sum((i.fees for i in loan.schedule), Decimal(0))
    method = "flat rate (on the original amount)" if loan.interest_method == "FLAT" else "reducing balance"
    bank = (
        f"{b.bank.bank}{', ' + b.bank.branch if b.bank.branch else ''}, account {b.bank.account_number} "
        f"({b.bank.account_name})"
        if b.bank
        else "To be confirmed before payout"
    )

    story: list = [P("Loan agreement", "title"), P(f"Agreement number {loan.ref}, dated {dmy(today)}", "small")]
    if not reviewed:
        story.append(
            P(
                DRAFT_NOTE + " The terms in section 3 are placeholders written in plain English for "
                "Breez Lending's lawyer to check against Papua New Guinea law (including any money-lending "
                "and Bank of PNG requirements) before this agreement is used.",
                "warn",
            )
        )

    story += [
        P("1. Who this agreement is between", "h2"),
        _pairs(
            [
                ("Lender", f"{company.name}, {company.address}"),
                ("Borrower", b.name),
                ("Date of birth", dmy(b.date_of_birth)),
                ("NID or ID number", b.national_id),
                ("Address", b.address),
                ("Phone", b.phone),
                ("Employer", b.employer),
                ("Payroll number", b.payroll_number),
            ]
        ),
        P("2. The loan", "h2"),
        _pairs(
            [
                ("Amount lent", kina(loan.principal)),
                ("Paid into", bank),
                ("Interest", f"{loan.annual_rate:.2f}% a year, {method}"),
                ("Number of repayments", f"{len(loan.schedule) or loan.term_months}"),
                ("Each repayment", kina(first.total) if first else "-"),
                ("First repayment due", dmy(first.due_date) if first else "As in Schedule 1"),
                ("Last repayment due", dmy(last.due_date) if last else "As in Schedule 1"),
                ("Total interest", kina(loan.total_interest)),
                ("Fees", kina(fees)),
                ("Total to repay", kina(total)),
                ("Payment reference", loan.payment_reference),
            ]
        ),
        P(
            "Dates in Schedule 1 are based on the loan being paid out on the date shown in our records. If it is "
            "paid out on a different day, we will give you an updated schedule.",
            "small",
        ),
        P("3. Terms", "h2"),
    ]
    clauses = [
        (
            "3.1 Repayments.",
            "You agree to pay each repayment in Schedule 1 in full on or before its due date, "
            f"quoting the payment reference {_esc(loan.payment_reference)}.",
        ),
        (
            "3.2 Payroll deduction.",
            "If you have signed a payroll deduction authority, your employer will "
            "deduct each repayment from your pay and send it to us. If a deduction is "
            "not made, you must still pay the repayment yourself by the due date.",
        ),
        (
            "3.3 Paying early.",
            "You may repay all or part of the loan early at any time. [Lawyer to confirm "
            "how interest is reduced on early repayment.]",
        ),
        (
            "3.4 Late payments.",
            "If a repayment is late we will contact you by SMS or phone. [Lawyer to "
            "confirm any late fee, its amount and limits.]",
        ),
        (
            "3.5 Default.",
            "If a repayment is more than [30] days overdue, or information you gave us is false, "
            "we may give you written notice asking you to pay the overdue amount. If it is not "
            "paid within [14] days of the notice, the whole balance may become due. [Lawyer to "
            "confirm notice periods and steps.]",
        ),
        (
            "3.6 Your information.",
            "You confirm the information you gave us is true and complete. You will tell "
            "us within 14 days if you change your job, address or phone number.",
        ),
        (
            "3.7 Privacy.",
            "We keep your personal information secure and use it to assess and manage this loan. "
            "We may share it with your employer (for deductions) and credit reporting bodies, as "
            "the law allows. [Lawyer to confirm consent wording.]",
        ),
        (
            "3.8 Questions and complaints.",
            "Contact us first. If we cannot resolve it, [lawyer to name the external dispute body, if any].",
        ),
        ("3.9 Law.", "This agreement is governed by the laws of Papua New Guinea."),
    ]
    story += [P(f"<b>{h}</b> {t}", "clause") for h, t in clauses]
    story += [P("How to pay", "h2")] + [P(f"<b>{_esc(w.name)}</b>: {_esc(w.how)}") for w in ways]

    sign = Table(
        [
            ["Borrower", "", "For " + company.name, ""],
            ["Signature", "", "Signature", ""],
            ["Name", b.name, "Name and position", ""],
            ["Date", "", "Date", ""],
            ["Witness signature", "", "", ""],
            ["Witness name", "", "", ""],
        ],
        colWidths=[30 * mm, 55 * mm, 32 * mm, 53 * mm],
        rowHeights=[7 * mm, 14 * mm, 8 * mm, 8 * mm, 14 * mm, 8 * mm],
    )
    sign.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("TEXTCOLOR", (0, 1), (0, -1), INK_MUTED),
                ("TEXTCOLOR", (2, 1), (2, -1), INK_MUTED),
                ("LINEBELOW", (1, 1), (1, -1), 0.5, colors.black),
                ("LINEBELOW", (3, 1), (3, 3), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )
    story += [
        P("4. Signatures", "h2"),
        P(
            "By signing, you confirm you have read this agreement and Schedule 1, had the chance to ask "
            "questions, and received a copy.",
            "body",
        ),
        Spacer(1, 2 * mm),
        KeepTogether([sign]),
        PageBreak(),
        P("Schedule 1: Repayment schedule", "title"),
        _schedule_table(loan.schedule, show_paid=False),
    ]
    return _build(story, company, f"Loan agreement {loan.ref}", today, draft=not reviewed)
