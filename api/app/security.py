"""Sessions (signed, time-limited cookies), one-time codes and a simple rate limiter.

The staff cookie carries the staff member's Fineract credential, signed so it can't be
forged. It is HttpOnly and SameSite=Strict, so page scripts can't read it and other
sites can't send it. One-time codes are kept hashed in memory: run a single API worker,
or move them to the database before scaling out.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings

STAFF_COOKIE = "mcl_staff"
PORTAL_COOKIE = "mcl_portal"


def _serializer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=salt)


def set_session(response: Response, settings: Settings, cookie: str, data: dict) -> None:
    token = _serializer(settings, cookie).dumps(data)
    response.set_cookie(
        cookie,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session(response: Response, cookie: str) -> None:
    response.delete_cookie(cookie, path="/")


def read_session(request: Request, settings: Settings, cookie: str) -> dict | None:
    token = request.cookies.get(cookie)
    if not token:
        return None
    try:
        return _serializer(settings, cookie).loads(token, max_age=settings.session_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None


@dataclass
class StaffSession:
    username: str
    display_name: str
    roles: list[str]
    cred: str


def _settings(request: Request) -> Settings:
    return request.app.state.services.settings


def staff_session(request: Request, settings: Settings = Depends(_settings)) -> StaffSession:
    data = read_session(request, settings, STAFF_COOKIE)
    if not data:
        raise HTTPException(401, "Please sign in.")
    return StaffSession(**data)


def portal_session(request: Request, settings: Settings = Depends(_settings)) -> int:
    data = read_session(request, settings, PORTAL_COOKIE)
    if not data:
        raise HTTPException(401, "Please sign in with your phone number.")
    return int(data["borrower_id"])


# ---------------------------------------------------------------- one-time codes
@dataclass
class _Challenge:
    digest: str
    expires: float
    attempts: int = 0


class OtpStore:
    def __init__(self, ttl: int, max_attempts: int):
        self.ttl, self.max_attempts = ttl, max_attempts
        self._items: dict[str, _Challenge] = {}

    @staticmethod
    def _digest(phone: str, code: str) -> str:
        return hashlib.sha256(f"{phone}:{code}".encode()).hexdigest()

    def issue(self, phone: str) -> str:
        code = f"{secrets.randbelow(10**6):06d}"
        self._items[phone] = _Challenge(self._digest(phone, code), time.monotonic() + self.ttl)
        return code

    def verify(self, phone: str, code: str) -> bool:
        ch = self._items.get(phone)
        if not ch or time.monotonic() > ch.expires or ch.attempts >= self.max_attempts:
            self._items.pop(phone, None)
            return False
        ch.attempts += 1
        if hmac.compare_digest(ch.digest, self._digest(phone, code)):
            del self._items[phone]
            return True
        return False


class RateLimiter:
    """At most `limit` hits per key in `window` seconds (in memory)."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
        q.append(now)
