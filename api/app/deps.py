"""Shared objects (back end, SMS, one-time codes, rate limits) and small helpers for the routers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request

from .backends.base import LendingBackend
from .config import Settings
from .domain.risk import Policy
from .security import OtpStore, RateLimiter, SessionStore
from .sms import SmsSender
from .store import DbOtpStore, DbRateLimiter, DbSessionStore


@dataclass
class Services:
    settings: Settings
    backend: LendingBackend
    sms: SmsSender
    otp: OtpStore | DbOtpStore
    policy: Policy
    login_limit: RateLimiter | DbRateLimiter
    otp_limit: RateLimiter | DbRateLimiter
    sessions: SessionStore | DbSessionStore
    # At most 2 'come and sign' SMS resends per loan in 10 minutes (cost, and not to pester borrowers).
    resend_limit: RateLimiter | DbRateLimiter = field(default_factory=lambda: RateLimiter(2, 600))

    def today(self) -> date:
        return datetime.now(local_zone(self.settings.timezone)).date()


# Port Moresby is UTC+10 all year (no daylight saving), so a fixed offset is exact if the
# time zone database is missing (Windows without the tzdata package).
_FALLBACK = {"Pacific/Port_Moresby": timezone(timedelta(hours=10), "PGT")}


def local_zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name in _FALLBACK:
            return _FALLBACK[name]
        raise


def services(request: Request) -> Services:
    return request.app.state.services
