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
    session_hours: int = 10
    cookie_secure: bool = False
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # SMS: "console" logs messages (development). Digicel and Vodafone adapters are chosen at shipping time.
    sms_provider: Literal["console"] = "console"
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5

    # Development only: GET /api/dev/sms/{phone} returns the last SMS sent (demo back end only).
    dev_sms_inbox: bool = False

    policy_file: str = ""  # path to underwriting policy.json; empty = built-in defaults


@lru_cache
def get_settings() -> Settings:
    return Settings()
