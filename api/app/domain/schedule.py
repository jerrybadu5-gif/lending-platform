"""Repayment schedules (Decimal only). Used by the demo back end and for quotes.

With a real Fineract back end the schedule always comes from Fineract itself; this module
only has to agree with it for previews.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .risk import DECLINING_BALANCE, FLAT, installment, money


def add_months(d: date, months: int, anchor_day: int | None = None) -> date:
    """Same day-of-month `months` later, clamped to month end, never drifting (31 Jan -> 28 Feb -> 31 Mar)."""
    day = anchor_day or d.day
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


@dataclass
class Row:
    number: int
    due_date: date
    principal: Decimal
    interest: Decimal
    total: Decimal
    balance_after: Decimal


def monthly_schedule(
    principal: Decimal, annual_rate_pct: Decimal, months: int, first_due: date, method: str = DECLINING_BALANCE
) -> list[Row]:
    rate = annual_rate_pct / 100
    rows: list[Row] = []
    balance = principal
    if method == FLAT:
        interest_each = money(principal * rate / 12)
        principal_each = money(principal / months)
        for n in range(1, months + 1):
            p = balance if n == months else principal_each
            balance -= p
            rows.append(Row(n, add_months(first_due, n - 1), p, interest_each, p + interest_each, balance))
        return rows
    pay = installment(principal, rate, months)
    for n in range(1, months + 1):
        i = money(balance * rate / 12)
        p = balance if n == months else pay - i
        balance -= p
        rows.append(Row(n, add_months(first_due, n - 1), p, i, p + i, balance))
    return rows
