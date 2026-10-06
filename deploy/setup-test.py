"""
Sets up a fresh Fineract for a McLender test run, in one go:

  1. the two McLender data tables (underwriting/bootstrap.py)
  2. PGK as the currency, and the payment types Cash, Bank Transfer, Mobile Money, Payroll Deduction
  3. a "Personal loan" product (PGK, 24% a year, reducing balance, monthly, 3-36 months)
  4. roles Credit Manager, Loan Officer and Borrower Portal, with only the permissions each needs
  5. staff users grace (credit manager) and john (loan officer), and the portal user from deploy/.env
  6. three test borrowers: Mary Kila (active loan, a payment made), Peter Wambi and Joyce Ilave
     (applications waiting for approval)

Run from the repository folder once Fineract is up (see docs/LIVE-TESTING.md):

    python deploy/setup-test.py

Safe to run again: anything that already exists is left alone. Uses the Fineract admin login
mifos / password unless FINERACT_USER / FINERACT_PASSWORD are set.

TEST DATA ONLY. Do not run this against the live Breez Lending server.
"""
from __future__ import annotations

import os
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "underwriting"))

import bootstrap  # noqa: E402
from fineract import Fineract, FineractError  # noqa: E402

TODAY = date.today()
DF = {"locale": "en", "dateFormat": "yyyy-MM-dd"}
PRODUCT_NAME = "Personal loan"
PAYMENT_TYPES = [("Cash", True), ("Bank Transfer", False), ("Mobile Money", False), ("Payroll Deduction", False)]

DT = [bootstrap.BORROWER_TABLE, bootstrap.ASSESSMENT_TABLE]
DT_RW = [f"{op}_{t}" for t in DT for op in ("READ", "CREATE", "UPDATE")]
ROLES = {
    "Credit Manager": (
        "Approves, rejects and disburses loans (McLender: approver)",
        ["ALL_FUNCTIONS_READ", "CREATE_CLIENT", "ACTIVATE_CLIENT", "UPDATE_CLIENT", "CREATE_LOAN", "UPDATE_LOAN",
         "APPROVE_LOAN", "REJECT_LOAN", "DISBURSE_LOAN", "REPAYMENT_LOAN", *DT_RW],
    ),
    "Loan Officer": (
        "Takes applications and records repayments; cannot approve",
        ["ALL_FUNCTIONS_READ", "CREATE_CLIENT", "ACTIVATE_CLIENT", "UPDATE_CLIENT", "CREATE_LOAN", "UPDATE_LOAN",
         "REPAYMENT_LOAN", *DT_RW],
    ),
    "Borrower Portal": (
        "Technical user behind the McLender borrower portal",
        ["READ_CLIENT", "READ_CLIENTIDENTIFIER", "READ_LOAN", "CREATE_LOAN", "READ_LOANPRODUCT", *DT_RW],
    ),
}


def step(msg: str) -> None:
    print(f"\n== {msg}")


def read_env() -> dict[str, str]:
    env = {}
    path = ROOT / "deploy" / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.split("#", 1)[0].strip().strip('"').strip("'")
    return env


def items(res):
    return res.get("pageItems", res) if isinstance(res, dict) else res


def main() -> None:
    env = read_env()
    os.environ.setdefault("FINERACT_URL", f"http://localhost:{env.get('FINERACT_PORT', '8080')}")
    f = Fineract.from_env()
    try:
        f.get("/offices")
    except FineractError as e:
        sys.exit(f"Can't sign in to Fineract ({e}). Is it up? See docs/LIVE-TESTING.md step 2.")
    except OSError as e:
        sys.exit(f"Can't reach Fineract at {f.base} ({e}). Is it up? See docs/LIVE-TESTING.md step 2.")

    step("Data tables")
    sys.argv = [sys.argv[0]]
    bootstrap.main()

    step("Currency and payment types")
    f.put("/currencies", {"currencies": ["PGK"]})
    print("= PGK is the currency")
    have = {t["name"].lower(): t["id"] for t in f.get("/paymenttypes")}
    for pos, (name, cash) in enumerate(PAYMENT_TYPES, 1):
        if name.lower() in have:
            print(f"= {name}")
        else:
            r = f.post("/paymenttypes", {"name": name, "description": name, "isCashPayment": cash, "position": pos})
            have[name.lower()] = r["resourceId"]
            print(f"+ {name}")

    step("Loan product")
    product = next((p for p in f.get("/loanproducts") if p["name"] == PRODUCT_NAME), None)
    if product:
        pid = product["id"]
        print(f"= {PRODUCT_NAME} (id {pid})")
    else:
        pid = f.post("/loanproducts", {
            **DF,
            "name": PRODUCT_NAME, "shortName": "PL01", "description": "Salaried borrowers, monthly repayments",
            "currencyCode": "PGK", "digitsAfterDecimal": 2, "inMultiplesOf": 0,
            "principal": 5000, "minPrincipal": 500, "maxPrincipal": 50000,
            "numberOfRepayments": 12, "minNumberOfRepayments": 3, "maxNumberOfRepayments": 36,
            "repaymentEvery": 1, "repaymentFrequencyType": 2,
            "interestRatePerPeriod": 24, "minInterestRatePerPeriod": 10, "maxInterestRatePerPeriod": 36,
            "interestRateFrequencyType": 3, "interestType": 0, "amortizationType": 1,
            "interestCalculationPeriodType": 1, "allowPartialPeriodInterestCalcualtion": False,
            "transactionProcessingStrategyCode": "mifos-standard-strategy",
            "daysInMonthType": 1, "daysInYearType": 1, "isInterestRecalculationEnabled": False,
            "isLinkedToFloatingInterestRates": False, "isEqualAmortization": False,
            "accountingRule": 1,  # none for this test; the real chart of accounts is docs/CONFIGURATION.md section 3
        })["resourceId"]
        print(f"+ {PRODUCT_NAME} (id {pid})")
    if str(pid) != env.get("MCL_PORTAL_PRODUCT_ID", "1"):
        print(f"! Set MCL_PORTAL_PRODUCT_ID={pid} in deploy/.env before starting McLender")

    step("Roles")
    known = {p["code"] for p in f.get("/permissions")}
    roles = {r["name"]: r["id"] for r in f.get("/roles")}
    for name, (desc, perms) in ROLES.items():
        if name not in roles:
            roles[name] = f.post("/roles", {"name": name, "description": desc})["resourceId"]
            print(f"+ {name}")
        else:
            print(f"= {name}")
        missing = [p for p in perms if p not in known]
        if missing:
            print(f"  ! this Fineract has no permission {', '.join(missing)}: skipped")
        f.put(f"/roles/{roles[name]}/permissions", {"permissions": {p: True for p in perms if p in known}})

    step("Staff and users")
    users = {u["username"]: u for u in f.get("/users")}
    staff = {s["displayName"]: s["id"] for s in items(f.get("/staff?status=all"))}
    logins = []

    def user(username, first, last, role, password=None, is_staff=True):
        if username in users:
            print(f"= {username}")
            return
        body = {
            "username": username, "firstname": first, "lastname": last, "email": f"{username}@example.com",
            "officeId": 1, "roles": [roles[role]], "sendPasswordToEmail": False, "passwordNeverExpires": True,
        }
        if is_staff:
            display = f"{last}, {first}"
            if display not in staff:
                staff[display] = f.post("/staff", {
                    **DF, "officeId": 1, "firstname": first, "lastname": last, "isLoanOfficer": True,
                    "isActive": True, "joiningDate": (TODAY - timedelta(days=365)).isoformat(),
                })["resourceId"]
            body["staffId"] = staff[display]
        password = password or "Mcl-" + secrets.token_urlsafe(9)
        f.post("/users", {**body, "password": password, "repeatPassword": password})
        logins.append((username, "(the password in deploy/.env)" if is_staff is False else password, role))
        print(f"+ {username} ({role})")

    user("grace", "Grace", "Pokana", "Credit Manager")
    user("john", "John", "Kerema", "Loan Officer")
    portal_pw = env.get("MCL_FINERACT_PORTAL_PASSWORD", "")
    if not portal_pw or portal_pw.startswith("change-me"):
        sys.exit("Set MCL_FINERACT_PORTAL_PASSWORD in deploy/.env first (see docs/LIVE-TESTING.md step 1).")
    user(env.get("MCL_FINERACT_PORTAL_USER", "portal"), "Borrower", "Portal", "Borrower Portal",
         password=portal_pw, is_staff=False)

    step("Test borrowers")
    start = TODAY - timedelta(days=75)

    def borrower(first, last, phone, income, debt, score):
        hits = f.get(f"/search?query={phone}&resource=clients&exactMatch=false")
        for h in hits or []:
            c = f.get(f"/clients/{h['entityId']}")
            if (c.get("mobileNo") or "").endswith(phone):
                print(f"= {first} {last}")
                return None
        cid = f.post("/clients", {
            **DF, "officeId": 1, "legalFormId": 1, "firstname": first, "lastname": last, "mobileNo": phone,
            "active": True, "activationDate": start.isoformat(), "submittedOnDate": start.isoformat(),
        })["clientId"]
        f.upsert_datatable_row(bootstrap.BORROWER_TABLE, cid, {
            "monthly_income": income, "existing_monthly_debt": debt, "credit_score": score,
            "income_verified": True, "income_source": "Salary",
        })
        print(f"+ {first} {last}, phone {phone}")
        return cid

    def apply(cid, amount, months, on):
        return f.post("/loans", {
            **DF, "loanType": "individual", "clientId": cid, "productId": pid, "principal": amount,
            "loanTermFrequency": months, "loanTermFrequencyType": 2, "numberOfRepayments": months,
            "repaymentEvery": 1, "repaymentFrequencyType": 2, "interestRatePerPeriod": 24,
            "amortizationType": 1, "interestType": 0, "interestCalculationPeriodType": 1,
            "transactionProcessingStrategyCode": "mifos-standard-strategy",
            "expectedDisbursementDate": on.isoformat(), "submittedOnDate": on.isoformat(),
        })["loanId"]

    mary = borrower("Mary", "Kila", "70123344", 4200, 300, 720)
    if mary:
        on = start + timedelta(days=5)
        loan = apply(mary, 5000, 12, on)
        f.post(f"/loans/{loan}?command=approve", {**DF, "approvedOnDate": on.isoformat(), "approvedLoanAmount": 5000,
                                                  "expectedDisbursementDate": on.isoformat()})
        f.post(f"/loans/{loan}?command=disburse", {**DF, "actualDisbursementDate": on.isoformat()})
        paid = on + timedelta(days=30)
        f.post(f"/loans/{loan}/transactions?command=repayment", {
            **DF, "transactionDate": paid.isoformat(), "transactionAmount": 472.80,
            "paymentTypeId": have["mobile money"], "receiptNumber": "TEST-0001",
        })
        print(f"  + K 5,000 loan disbursed {on:%d/%m/%Y}, one payment made")
    peter = borrower("Peter", "Wambi", "71234567", 3500, 900, 610)
    if peter:
        apply(peter, 15000, 24, TODAY - timedelta(days=1))
        print("  + applied for K 15,000 over 24 months")
    joyce = borrower("Joyce", "Ilave", "72345678", 1800, 700, 520)
    if joyce:
        apply(joyce, 8000, 12, TODAY - timedelta(days=1))
        print("  + applied for K 8,000 over 12 months")

    print("\nDone.")
    if logins:
        print("\nNew Fineract logins (shown once; write them down):")
        for u, p, r in logins:
            print(f"  {u:<8} {p:<20} {r}")


if __name__ == "__main__":
    try:
        main()
    except FineractError as e:
        sys.exit(f"\nFineract refused a step: {e}\nCopy this message to Claude. Running the script again is safe.")
