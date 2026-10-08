"""McLender's own small database: sessions, one-time codes and rate limits, so a restart of the API
doesn't sign everyone out or forget a lock-out.

Fineract stays the record of borrowers, loans and money. This database only holds McLender's
working state (and, in later phases, its settings and audit log). With no MCL_DATABASE_URL the
same things are kept in memory, as before: fine for the demo and tests, lost on a restart.

What is stored, and how it is protected:
- a session row is keyed by the SHA-256 of the session id, never the id itself, so a copy of the
  database can't be used to sign in; its contents (who, roles, the staff member's Fineract
  credential) are encrypted with a key derived from MCL_SESSION_SECRET;
- a one-time code row holds only a hash of the phone number and code;
- a rate-limit row holds a key (an address and username, or a phone hash) and a time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)

log = logging.getLogger("mclender.store")

metadata = MetaData()

sessions_table = Table(
    "mcl_session",
    metadata,
    Column("id_hash", String(64), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("payload", LargeBinary, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

otp_table = Table(
    "mcl_otp",
    metadata,
    Column("phone_hash", String(64), primary_key=True),
    Column("digest", String(64), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

rate_hits_table = Table(
    "mcl_rate_hit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("key", String(200), nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Index("ix_mcl_rate_hit_key_at", "key", "at"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def usable_url(url: str | None) -> bool:
    """A database URL McLender should use: set, and with a password when it names a server."""
    if not url:
        return False
    if url.startswith("sqlite"):
        return True
    # postgresql+psycopg://user:password@host/db, with the password still empty when it isn't set up
    creds = url.split("://", 1)[-1].split("@", 1)[0]
    password = creds.split(":", 1)[1] if ":" in creds else ""
    # deploy/mclender-db.sh skips a password still set to the example's change-me, so skip it here too
    return "@" in url and bool(password) and not password.startswith("change-me")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        # one connection shared by all threads: an in-memory SQLite database lives in its connection
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def migrate(engine: Engine) -> None:
    """Bring the database up to date (Alembic migrations in api/migrations), creating it on first run."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config()
    cfg.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


# ---------------------------------------------------------------- sessions
class Cipher:
    """Encrypts session contents with a key derived from the session secret."""

    def __init__(self, secret: str):
        key = hashlib.sha256(f"mclender-session-store:{secret}".encode()).digest()
        self._f = Fernet(base64.urlsafe_b64encode(key))

    def seal(self, data: dict) -> bytes:
        return self._f.encrypt(json.dumps(data).encode())

    def open(self, token: bytes) -> dict | None:
        try:
            return dict(json.loads(self._f.decrypt(token)))
        except (InvalidToken, ValueError):
            return None  # written with another secret, or damaged: treat as signed out


class DbSessionStore:
    """Server-side sessions in the database (same interface as security.SessionStore)."""

    def __init__(self, engine: Engine, hours: int, secret: str, kinds: dict[str, type]):
        self.engine, self.ttl = engine, timedelta(hours=hours)
        self.cipher = Cipher(secret)
        self.kinds = kinds  # "staff" -> StaffSession, "portal" -> PortalSession
        self._names = {v: k for k, v in kinds.items()}

    def create(self, data: Any) -> str:
        import secrets

        sid = secrets.token_urlsafe(32)
        now = _now()
        kind = self._names[type(data)]
        with self.engine.begin() as conn:
            conn.execute(delete(sessions_table).where(sessions_table.c.expires_at < now))
            conn.execute(
                insert(sessions_table).values(
                    id_hash=_sha(sid),
                    kind=kind,
                    payload=self.cipher.seal(asdict(data)),
                    expires_at=now + self.ttl,
                    created_at=now,
                )
            )
        return sid

    def get(self, sid: str) -> Any | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(sessions_table.c.kind, sessions_table.c.payload, sessions_table.c.expires_at).where(
                    sessions_table.c.id_hash == _sha(sid)
                )
            ).first()
        if row is None:
            return None
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires < _now():
            self.delete(sid)
            return None
        data = self.cipher.open(row.payload)
        cls = self.kinds.get(row.kind)
        if data is None or cls is None:
            return None
        try:
            return cls(**data)
        except TypeError:  # an old session shape after an upgrade: sign in again
            return None

    def delete(self, sid: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(sessions_table).where(sessions_table.c.id_hash == _sha(sid)))


# ---------------------------------------------------------------- one-time codes
class DbOtpStore:
    """Sign-in codes in the database (same interface as security.OtpStore)."""

    def __init__(self, engine: Engine, ttl: int, max_attempts: int):
        self.engine, self.ttl, self.max_attempts = engine, ttl, max_attempts

    @staticmethod
    def _digest(phone: str, code: str) -> str:
        return _sha(f"{phone}:{code}")

    def issue(self, phone: str) -> str:
        import secrets

        code = f"{secrets.randbelow(10**6):06d}"
        key, now = _sha(f"otp:{phone}"), _now()
        with self.engine.begin() as conn:
            conn.execute(delete(otp_table).where(otp_table.c.expires_at < now))
            conn.execute(delete(otp_table).where(otp_table.c.phone_hash == key))
            conn.execute(
                insert(otp_table).values(
                    phone_hash=key,
                    digest=self._digest(phone, code),
                    attempts=0,
                    expires_at=now + timedelta(seconds=self.ttl),
                )
            )
        return code

    def verify(self, phone: str, code: str) -> bool:
        import hmac

        key = _sha(f"otp:{phone}")
        with self.engine.begin() as conn:
            row = conn.execute(select(otp_table).where(otp_table.c.phone_hash == key)).first()
            if row is None:
                return False
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expires < _now() or row.attempts >= self.max_attempts:
                conn.execute(delete(otp_table).where(otp_table.c.phone_hash == key))
                return False
            if hmac.compare_digest(row.digest, self._digest(phone, code)):
                conn.execute(delete(otp_table).where(otp_table.c.phone_hash == key))
                return True
            conn.execute(
                update(otp_table).where(otp_table.c.phone_hash == key).values(attempts=otp_table.c.attempts + 1)
            )
            return False


# ---------------------------------------------------------------- rate limits
class DbRateLimiter:
    """At most `limit` hits per key in `window` seconds, kept in the database (same interface as
    security.RateLimiter)."""

    def __init__(self, engine: Engine, limit: int, window: float, name: str):
        self.engine, self.limit, self.window, self.name = engine, limit, window, name

    def _key(self, key: str) -> str:
        return f"{self.name}:{key}"[:200]

    def check(self, key: str) -> None:
        from fastapi import HTTPException

        k, now = self._key(key), _now()
        since = now - timedelta(seconds=self.window)
        with self.engine.begin() as conn:
            conn.execute(delete(rate_hits_table).where(rate_hits_table.c.key == k, rate_hits_table.c.at < since))
            hits = conn.execute(
                select(func.count()).select_from(rate_hits_table).where(rate_hits_table.c.key == k)
            ).scalar_one()
            if hits >= self.limit:
                raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
            conn.execute(insert(rate_hits_table).values(key=k, at=now))

    def reset(self, key: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(rate_hits_table).where(rate_hits_table.c.key == self._key(key)))
