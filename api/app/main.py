"""McLender API entry point: `uvicorn app.main:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .backends.base import BackendError, LendingBackend
from .config import Settings, get_settings
from .deps import Services
from .routers import borrowers, documents, payout, portal, staff
from .security import OtpStore, RateLimiter, SessionStore
from .sms import make_sms
from .underwriting import load_policy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def make_backend(settings: Settings, today) -> LendingBackend:
    if settings.backend == "fineract":
        from .backends.fineract import FineractBackend

        return FineractBackend(settings)
    from .backends.demo import DemoBackend

    return DemoBackend(today)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    weak = settings.session_secret.startswith(("dev-only", "change-me")) or len(settings.session_secret) < 32
    if settings.backend == "fineract" and weak:
        raise RuntimeError("Set MCL_SESSION_SECRET to a long random value (32+ characters) for the Fineract back end.")
    if settings.backend == "fineract" and not settings.cookie_secure:
        logging.getLogger("mclender").warning(
            "MCL_COOKIE_SECURE is off: sign-in cookies will also travel over plain HTTP. Turn it on behind HTTPS."
        )
    if settings.backend == "fineract" and settings.sms_provider == "console":
        logging.getLogger("mclender").warning(
            "No SMS provider: borrowers will not receive sign-in codes or receipts. %s",
            "Codes are written to this log (MCL_SMS_LOG_CONTENT=true): local testing only."
            if settings.sms_log_content
            else "For local testing only, set MCL_SMS_LOG_CONTENT=true to read codes from this log.",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = Services(
            settings=settings,
            backend=None,  # type: ignore[arg-type]  # set just below, once today's date is known
            sms=make_sms(settings.sms_provider, reveal=settings.backend == "demo" or settings.sms_log_content),
            otp=OtpStore(settings.otp_ttl_seconds, settings.otp_max_attempts),
            policy=load_policy(settings.policy_file),
            login_limit=RateLimiter(10, 300),
            otp_limit=RateLimiter(5, 900),
            sessions=SessionStore(settings.session_hours),
        )
        svc.backend = make_backend(settings, svc.today())
        app.state.services = svc
        yield
        await svc.backend.aclose()

    app = FastAPI(
        title="McLender API",
        version="0.1.0",
        lifespan=lifespan,
        description=f"Back end for the McLender staff app and the {settings.company_name} borrower portal.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-MCL-User", "X-MCL-Tab"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(BackendError)
    async def backend_error(_: Request, exc: BackendError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e["loc"] if p != "body")
            fields.append({"field": loc, "message": e["msg"]})
        return JSONResponse({"detail": "Some fields need fixing.", "fields": fields}, status_code=422)

    @app.get("/api/health", tags=["system"])
    async def health():
        return {"status": "ok", "backend": settings.backend}

    if settings.dev_sms_inbox and settings.backend == "demo":

        @app.get("/api/dev/sms/{phone}", tags=["development"])
        async def dev_sms(phone: str, request: Request):
            sent = [m for m in request.app.state.services.sms.sent if m[0] == phone]
            return {"to": phone, "text": sent[-1][1] if sent else None}

    app.include_router(staff.router)
    app.include_router(borrowers.router)
    app.include_router(documents.router)
    app.include_router(payout.router)
    app.include_router(portal.router)
    return app


app = create_app()
