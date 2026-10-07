"""Minimal Apache Fineract REST client (standard library only)."""
from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Optional


class FineractError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {self._readable(body)}")
        self.status = status
        self.body = body

    @staticmethod
    def _readable(body: str) -> str:
        """Fineract's validation errors as one line each, instead of a long JSON blob."""
        try:
            data = json.loads(body)
            errors = data.get("errors") or []
            if not isinstance(errors, list):
                return body[:1000]
            lines = [f"{e.get('parameterName') or '-'}: {e.get('defaultUserMessage') or e.get('developerMessage')}"
                     for e in errors]
            return "\n  ".join([data.get("defaultUserMessage", "")] + lines) if lines else body[:1000]
        except (ValueError, AttributeError, TypeError):
            return body[:1000]


class Fineract:
    def __init__(self, base_url: str, username: str, password: str,
                 tenant: str = "default", verify_tls: bool = True, timeout: int = 60):
        self.base = base_url.rstrip("/") + "/fineract-provider/api/v1"
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Fineract-Platform-TenantId": tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.ctx = None if verify_tls else ssl._create_unverified_context()
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Fineract":
        return cls(
            os.environ.get("FINERACT_URL", "http://localhost:8080"),
            os.environ.get("FINERACT_USER", "mifos"),
            os.environ.get("FINERACT_PASSWORD", "password"),
            os.environ.get("FINERACT_TENANT", "default"),
            os.environ.get("FINERACT_VERIFY_TLS", "true").lower() != "false",
        )

    def request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise FineractError(e.code, e.read().decode(errors="replace")) from None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: dict) -> Any:
        return self.request("POST", path, body)

    def put(self, path: str, body: dict) -> Any:
        return self.request("PUT", path, body)

    # --- helpers -------------------------------------------------------
    def datatable_row(self, table: str, entity_id: int) -> Optional[dict]:
        rows = self.get(f"/datatables/{table}/{entity_id}?genericResultSet=false")
        return rows[0] if rows else None

    def upsert_datatable_row(self, table: str, entity_id: int, values: dict) -> None:
        body = {"locale": "en", "dateFormat": "yyyy-MM-dd",
                **{k: v for k, v in values.items() if v is not None}}
        if self.datatable_row(table, entity_id):
            self.put(f"/datatables/{table}/{entity_id}", body)
        else:
            self.post(f"/datatables/{table}/{entity_id}", body)

    def loans(self, status_id: Optional[int] = None, page: int = 200):
        offset = 0
        while True:
            res = self.get(f"/loans?offset={offset}&limit={page}")
            items = res.get("pageItems", [])
            for loan in items:
                if status_id is None or loan.get("status", {}).get("id") == status_id:
                    yield loan
            offset += page
            if offset >= res.get("totalFilteredRecords", 0) or not items:
                break
