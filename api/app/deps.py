"""Shared objects (back end, SMS, one-time codes, rate limits) and small helpers for the routers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Request

from .backends.base import LendingBackend
from .config import Settings
from .domain.risk import Policy
from .security import OtpStore, RateLimiter
from .sms import SmsSender


@dataclass
class Services:
    settings: Settings
    backend: LendingBackend
    sms: SmsSender
    otp: OtpStore
    policy: Policy
    login_limit: RateLimiter
    otp_limit: RateLimiter

    def today(self) -> date:
        return datetime.now(ZoneInfo(self.settings.timezone)).date()


def services(request: Request) -> Services:
    return request.app.state.services
