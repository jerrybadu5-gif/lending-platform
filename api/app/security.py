"""Sessions, one-time codes and a simple rate limiter.

Sessions live on the server. The browser only gets a random session id in an HttpOnly,
SameSite=Strict cookie (signed, so a tampered id is rejected before any lookup); the
staff member's Fineract credential never leaves the server. Sessions, one-time codes and
rate limits here are kept in memory, for the demo and tests; with MCL_DATABASE_URL set, app/store.py keeps
them in McLender's database instead, so a restart signs nobody out.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer

from .config import Settings

STAFF_COOKIE = "mcl_staff"
PORTAL_COOKIE = "mcl_portal"
# Each tab must present both its username and a session-bound secret.
STAFF_USER_HEADER = "X-MCL-User"
STAFF_TAB_HEADER = "X-MCL-Tab"


def _canonical_user(username: str) -> str:
    return username.strip().lower()


def staff_cookie_for(username: str) -> str:
    canonical = _canonical_user(username)
    slug = re.sub(r"[^a-z0-9]", "", canonical)[:32] or "user"
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"{STAFF_COOKIE}_{slug}_{digest}"


@dataclass
class StaffSession:
    username: str
    display_name: str
    roles: list[str]
    cred: str
    tab_credential: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)


@dataclass
class PortalSession:
    borrower_id: int
    first_name: str


class SessionStore:
    """Server-side sessions keyed by a random id, each with an absolute expiry."""

    def __init__(self, hours: int):
        self.ttl = hours * 3600
        self._items: dict[str, tuple[float, Any]] = {}

    def create(self, data: Any) -> str:
        self._sweep()
        sid = secrets.token_urlsafe(32)
        self._items[sid] = (time.monotonic() + self.ttl, data)
        return sid

    def get(self, sid: str) -> Any | None:
        item = self._items.get(sid)
        if not item:
            return None
        if time.monotonic() > item[0]:
            del self._items[sid]
            return None
        return item[1]

    def delete(self, sid: str) -> None:
        self._items.pop(sid, None)

    def _sweep(self) -> None:
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._items.items() if now > exp]:
            del self._items[k]


def _signer(settings: Settings, cookie: str) -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret, salt=cookie)


def _services(request: Request) -> Any:
    return request.app.state.services


def _set_cookie(response: Response, svc: Any, cookie: str, sid: str) -> None:
    response.set_cookie(
        cookie,
        _signer(svc.settings, cookie).dumps(sid),
        max_age=svc.settings.session_hours * 3600,
        httponly=True,
        secure=svc.settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def start_session(response: Response, svc: Any, cookie: str, data: StaffSession | PortalSession) -> None:
    sid = svc.sessions.create(data)
    _set_cookie(response, svc, cookie, sid)
    if isinstance(data, StaffSession):
        _set_cookie(response, svc, staff_cookie_for(data.username), sid)


def _session_id(request: Request, settings: Settings, cookie: str) -> str | None:
    token = request.cookies.get(cookie)
    if not token:
        return None
    try:
        return str(_signer(settings, cookie).loads(token))
    except BadSignature:
        return None


def _staff_cookie(request: Request) -> str:
    """The cookie selected by this tab; lookup still requires its credential."""
    user = request.headers.get(STAFF_USER_HEADER, "").strip()
    return staff_cookie_for(user) if user else STAFF_COOKIE


def end_session(request: Request, response: Response, svc: Any, cookie: str) -> None:
    if cookie == STAFF_COOKIE:
        mine = _staff_cookie(request)
        sid = _session_id(request, svc.settings, mine)
        data = _lookup(request, svc, mine, StaffSession)
        if data is None:
            raise HTTPException(401, "Please sign in.")
        if sid:
            svc.sessions.delete(sid)
        response.delete_cookie(mine, path="/")
        if isinstance(data, StaffSession):
            response.delete_cookie(staff_cookie_for(data.username), path="/")
        if _session_id(request, svc.settings, STAFF_COOKIE) in (sid, None):
            response.delete_cookie(STAFF_COOKIE, path="/")
        return
    sid = _session_id(request, svc.settings, cookie)
    if sid:
        svc.sessions.delete(sid)
    response.delete_cookie(cookie, path="/")


def _lookup(request: Request, svc: Any, cookie: str, kind: type) -> Any | None:
    sid = _session_id(request, svc.settings, cookie)
    data = svc.sessions.get(sid) if sid else None
    if not isinstance(data, kind):
        return None
    if isinstance(data, StaffSession):
        user = request.headers.get(STAFF_USER_HEADER, "")
        credential = request.headers.get(STAFF_TAB_HEADER, "")
        if (
            not user
            or not credential
            or _canonical_user(user) != _canonical_user(data.username)
            or not hmac.compare_digest(credential.encode(), data.tab_credential.encode())
        ):
            return None
    return data


def staff_session(request: Request, svc: Any = Depends(_services)) -> StaffSession:
    data = _lookup(request, svc, _staff_cookie(request), StaffSession)
    if data is None:
        raise HTTPException(401, "Please sign in.")
    return data


def portal_session(request: Request, svc: Any = Depends(_services)) -> PortalSession:
    data = _lookup(request, svc, PORTAL_COOKIE, PortalSession)
    if data is None:
        raise HTTPException(401, "Please sign in with your phone number.")
    return data


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

    def reset(self, key: str) -> None:
        """Forget a key's hits (after a successful sign-in, so only failed attempts add up)."""
        self._hits.pop(key, None)
