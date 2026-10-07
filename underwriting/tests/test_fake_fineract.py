"""End-to-end run of assess.py against an in-process fake Fineract API."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import assess  # noqa: E402
from fineract import Fineract  # noqa: E402
from risk import Policy  # noqa: E402

API = "/fineract-provider/api/v1"
LOAN = {
    "id": 7, "clientId": 3, "clientName": "Test Borrower", "status": {"id": 100},
    "proposedPrincipal": 15000.0, "annualInterestRate": 10.0, "numberOfRepayments": 12,
    "repaymentEvery": 1, "repaymentFrequencyType": {"id": 2}, "interestType": {"id": 0},
    "repaymentSchedule": {"periods": [{"period": i, "totalDueForPeriod": 1318.74} for i in range(1, 13)]},
}


def make_handler(calls, store):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            assert self.headers["Fineract-Platform-TenantId"] == "default"
            p = self.path.replace(API, "")
            if p.startswith("/loans/7"):
                return self._send(LOAN)
            if p.startswith("/loans?"):
                return self._send({"totalFilteredRecords": 1, "pageItems": [LOAN]})
            if p.startswith("/datatables/dt_borrower_financials/3"):
                return self._send([{"monthly_income": 5000, "existing_monthly_debt": 400, "credit_score": 680}])
            if p.startswith("/datatables/dt_loan_assessment/7"):
                return self._send(store.get("assessment", []))
            self._send({}, 404)

        def _body(self):
            return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

        def do_POST(self):
            p, b = self.path.replace(API, ""), self._body()
            calls.append(("POST", p, b))
            if p == "/datatables/dt_loan_assessment/7":
                store["assessment"] = [b]
            self._send({"resourceId": 1})

        def do_PUT(self):
            calls.append(("PUT", self.path.replace(API, ""), self._body()))
            self._send({"resourceId": 1})
    return H


def test_assess_pending_writes_assessment_then_updates():
    calls, store = [], {}
    srv = HTTPServer(("127.0.0.1", 0), make_handler(calls, store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        f = Fineract(f"http://127.0.0.1:{srv.server_port}", "mifos", "password")
        for _ in range(2):  # second run must update, not insert
            for loan in f.loans(status_id=100):
                assess.run(f, loan["id"], Policy(), dry_run=False)
    finally:
        srv.shutdown()

    methods = [(m, p) for m, p, _ in calls]
    assert methods == [("POST", "/datatables/dt_loan_assessment/7"), ("POST", "/loans/7/notes"),
                       ("PUT", "/datatables/dt_loan_assessment/7"), ("POST", "/loans/7/notes")]
    row = calls[0][2]
    assert row["recommendation"] == "APPROVE" and row["dti"] == "0.3437" and row["locale"] == "en"
    assert "dscr" not in row  # None values are not sent


def test_odd_error_bodies_keep_a_readable_message():
    from fineract import FineractError

    assert "HTTP 400" in str(FineractError(400, '{"errors": 1}'))
    assert "bad" in str(FineractError(400, '{"defaultUserMessage": "bad", "errors": [{"parameterName": "x"}]}'))
