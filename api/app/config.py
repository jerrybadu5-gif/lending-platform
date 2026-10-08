"""Settings, read from environment variables prefixed MCL_ (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCL_", env_file=".env", extra="ignore")

    # "demo" runs on built-in sample data (no Fineract needed); "fineract" talks to a real server.
    backend: Literal["demo", "fineract"] = "demo"
    company_name: str = "Breez Lending"
    # Printed on loan agreements, statements and receipts.
    company_address: str = "Port Moresby, National Capital District, Papua New Guinea"
    company_phone: str = ""
    company_email: str = ""
    timezone: str = "Pacific/Port_Moresby"

    fineract_url: str = "http://localhost:8080"
    fineract_tenant: str = "default"
    fineract_verify_tls: bool = True
    # Technical Fineract user the borrower portal acts as (read own loans, submit applications).
    fineract_portal_user: str = ""
    fineract_portal_password: str = ""
    # Fineract loan product used for portal applications, and payment type names by method.
    portal_product_id: int = 1
    payment_types: dict[str, str] = Field(
        default_factory=lambda: {
            "cash": "Cash",
            "bank": "Bank Transfer",
            "mobile": "Mobile Money",
            "payroll": "Payroll Deduction",
        }
    )

    # Sessions. Set a long random secret in production (python -c "import secrets;print(secrets.token_urlsafe(48))").
    session_secret: str = "dev-only-change-me"
    # McLender's own database (sessions, sign-in codes, rate limits; later settings and the audit log), e.g.
    # postgresql+psycopg://mclender:<password>@postgresql:5432/mclender. Empty: kept in memory (lost on restart).
    database_url: str = ""
    session_hours: int = 10
    cookie_secure: bool = False
    # Write SMS text (including sign-in codes) to the log. Sample data always does; with Fineract only
    # for local testing until a real SMS provider is set up.
    sms_log_content: bool = False
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # SMS: "console" logs messages (development). Digicel and Vodafone adapters are chosen at shipping time.
    sms_provider: Literal["console"] = "console"
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5

    # Development only: GET /api/dev/sms/{phone} returns the last SMS sent (demo back end only).
    dev_sms_inbox: bool = False

    policy_file: str = ""  # path to underwriting policy.json; empty = built-in defaults

    # KYC: documents needed (by kind, minimum number of files) before a loan can be approved.
    # A borrower's three payslips may be one scanned file, so one payslip file counts.
    kyc_required: dict[str, int] = Field(
        default_factory=lambda: {"id": 1, "payslip": 1, "bank_statement": 1, "deduction_authority": 1}
    )
    # Loan officer reviews and submits; only then can a credit manager approve, reject or send it back.
    review_required: bool = True
    # A credit manager who sent an application up themselves can't also approve it, unless this is true
    # (a branch with a single credit manager and no loan officer).
    allow_self_approval: bool = False
    kyc_required_for_approval: bool = True
    # A loan is paid out only once the borrower's signed agreement is uploaded to it.
    signed_agreement_required: bool = True
    max_upload_mb: int = 5  # Fineract's own document limit is 5 MB

    # The loan agreement is a draft template until a PNG lawyer has reviewed the wording. While this is
    # false, every page says so.
    agreement_reviewed: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
