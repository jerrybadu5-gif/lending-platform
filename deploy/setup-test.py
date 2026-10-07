"""
Sets up a fresh Fineract for a McLender test run, in one go:

  1. the McLender data tables (underwriting/bootstrap.py)
  2. PGK as the currency, and the payment types Cash, Bank Transfer, Mobile Money, Payroll Deduction
  3. a "Personal loan" product (PGK, 24% a year, reducing balance, monthly, 3-36 months)
  4. roles Credit Manager, Loan Officer and Borrower Portal, with only the permissions each needs
  5. staff users grace (credit manager) and john (loan officer), and the portal user from deploy/.env
  6. three test borrowers: Mary Kila (active loan, a payment made), Peter Wambi and Joyce Ilave
     (applications waiting for approval)

Run from the repository folder once Fineract is up (see docs/LIVE-TESTING.md):

    python deploy/setup-test.py

Safe to run again: anything that already exists is left alone.
    python deploy/setup-test.py --new-passwords    # give grace and john new passwords
 Uses the Fineract admin login
mifos / password unless FINERACT_USER / FINERACT_PASSWORD are set.

TEST DATA ONLY. Do not run this against the live Breez Lending server.
"""
from __future__ import annotations

import os
import re
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
# Staff also keep the borrower profile (bank account, next of kin) and KYC documents. The portal does not.
# Staff also keep the officer's review of each application (dt_loan_review), remove wrong uploads (with a
# note saying why) and set the borrower's photo from their ID card.
STAFF_TABLES = (bootstrap.PROFILE_TABLE, bootstrap.REVIEW_TABLE)
STAFF_KYC = [f"{op}_{t}" for t in STAFF_TABLES for op in ("READ", "CREATE", "UPDATE")] + [
    "CREATE_DOCUMENT", "READ_DOCUMENT", "DELETE_DOCUMENT", "CREATE_CLIENTIDENTIFIER", "UPDATE_CLIENTIDENTIFIER",
    "CREATE_LOANNOTE", "CREATE_CLIENTNOTE", "CREATE_CLIENTIMAGE", "DELETE_CLIENTIMAGE",
]
ROLES = {
    "Credit Manager": (
        "Approves, rejects and disburses loans (McLender: approver)",
        ["ALL_FUNCTIONS_READ", "CREATE_CLIENT", "ACTIVATE_CLIENT", "UPDATE_CLIENT", "CREATE_LOAN", "UPDATE_LOAN",
         "APPROVE_LOAN", "REJECT_LOAN", "DISBURSE_LOAN", "REPAYMENT_LOAN", *DT_RW, *STAFF_KYC],
    ),
    "Loan Officer": (
        "Takes applications and records repayments; cannot approve",
        ["ALL_FUNCTIONS_READ", "CREATE_CLIENT", "ACTIVATE_CLIENT", "UPDATE_CLIENT", "CREATE_LOAN", "UPDATE_LOAN",
         "REPAYMENT_LOAN", *DT_RW, *STAFF_KYC],
    ),
    "Borrower Portal": (
        "Technical user behind the McLender borrower portal",
        ["READ_CLIENT", "READ_CLIENTIDENTIFIER", "READ_LOAN", "CREATE_LOAN", "READ_LOANPRODUCT", *DT_RW],
    ),
}


SPECIALS = "!@%*-_+=?"  # no #, $ or quotes: they mean something in .env files


def strong(pw: str) -> bool:
    """Fineract's default password policy: 12-50 characters, upper, lower, digit and special
    character, no spaces, and no character repeated twice in a row."""
    return (
        12 <= len(pw) <= 50
        and any(c.isupper() for c in pw)
        and any(c.islower() for c in pw)
        and any(c.isdigit() for c in pw)
        and any(not c.isalnum() for c in pw)
        and " " not in pw
        and not any(a == b for a, b in zip(pw, pw[1:]))
    )


def new_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789" + SPECIALS
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(16))
        if strong(pw):
            return pw


def set_env_value(key: str, value: str) -> None:
    path = ROOT / "deploy" / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    found = any(line.startswith(f"{key}=") for line in lines)
    lines = [f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines]
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if read_env().get(key) != value:  # the API must read exactly what Fineract is given
        sys.exit(f"Could not save {key} in {path}. Set it by hand and run this again.")


def step(msg: str) -> None:
    print(f"\n== {msg}")


def read_env() -> dict[str, str]:
    env = {}
    path = ROOT / "deploy" / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                # Like Docker Compose: " #" starts a comment, but a # inside a value (a password) is kept.
                env[k.strip()] = re.split(r"\s+#", v, maxsplit=1)[0].strip().strip('"').strip("'")
    return env


def items(res):
    return res.get("pageItems", res) if isinstance(res, dict) else res


def main() -> None:
    new_passwords = "--new-passwords" in sys.argv[1:]  # read now: the data table step resets sys.argv
    env = read_env()
    os.environ.setdefault("FINERACT_URL", f"http://localhost:{env.get('FINERACT_PORT', '8080')}")
    f = Fineract.from_env()
    portal_user = env.get("MCL_FINERACT_PORTAL_USER", "portal")
    portal_pw = env.get("MCL_FINERACT_PORTAL_PASSWORD", "")
    if not portal_pw or portal_pw.startswith("change-me") or not strong(portal_pw):
        # Fineract would refuse it, so make a strong one and save it where the API reads it.
        portal_pw = new_password()
        set_env_value("MCL_FINERACT_PORTAL_PASSWORD", portal_pw)
        print("! MCL_FINERACT_PORTAL_PASSWORD in deploy/.env was too weak for Fineract; it now has a new,")
        print("  strong one. Restart the API afterwards: cd deploy; docker compose up -d mclender-api")
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
            "interestCalculationPeriodType": 1,
            "repaymentStartDateType": 1, "loanScheduleType": "CUMULATIVE",  # first repayment counted from disbursement
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

    def user(username, first, last, role, password=None, is_staff=True):
        if username in users:
            if new_passwords and is_staff:
                password = new_password()
                f.put(f"/users/{users[username]['id']}", {"password": password, "repeatPassword": password})
                print(f"* {username:<8} new password: {password}   <- write this down")
            elif not is_staff:
                # Keep the portal user's password the same as deploy/.env, which the API signs in with.
                f.put(f"/users/{users[username]['id']}", {"password": password, "repeatPassword": password})
                print(f"= {username} (password matched to deploy/.env)")
            else:
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
        password = password or new_password()
        f.post("/users", {**body, "password": password, "repeatPassword": password})
        shown = f"password: {password}   <- write this down" if is_staff else "password: the one in deploy/.env"
        print(f"+ {username:<8} ({role}) {shown}")

    user("grace", "Grace", "Pokana", "Credit Manager")
    user("john", "John", "Kerema", "Loan Officer")
    user(portal_user, "Borrower", "Portal", "Borrower Portal", password=portal_pw, is_staff=False)

    step("Test borrowers")
    start = TODAY - timedelta(days=75)

    def borrower(first, last, phone, income, debt, score):
        """The client's id, created if missing. An existing client is reused, so a run that stopped
        half-way is finished by the next one (see the loan steps below)."""
        hits = f.get(f"/search?query={phone}&resource=clients&exactMatch=false")
        for h in hits or []:
            c = f.get(f"/clients/{h['entityId']}")
            if (c.get("mobileNo") or "").endswith(phone):
                print(f"= {first} {last}")
                return int(c["id"])
        cid = f.post("/clients", {
            **DF, "officeId": 1, "legalFormId": 1, "firstname": first, "lastname": last, "mobileNo": phone,
            "active": True, "activationDate": start.isoformat(), "submittedOnDate": start.isoformat(),
        })["clientId"]
        f.upsert_datatable_row(bootstrap.BORROWER_TABLE, cid, {
            "monthly_income": income, "existing_monthly_debt": debt, "credit_score": score,
            "income_verified": True, "income_source": "Salary",
        })
        f.upsert_datatable_row(bootstrap.PROFILE_TABLE, cid, {
            "address": "Waigani, NCD", "employer": "Test employer", "payroll_number": f"T-{phone[-4:]}",
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

    def first_loan(cid):
        """(loan id, Fineract status id) of the client's test loan, or (None, None)."""
        loans = (f.get(f"/clients/{cid}/accounts") or {}).get("loanAccounts") or []
        if not loans:
            return None, None
        loan = min(loans, key=lambda lo: int(lo["id"]))
        return int(loan["id"]), int((loan.get("status") or {}).get("id") or 0)

    # Mary: applied, approved, paid out and one repayment made. Each step is done only if still missing.
    mary = borrower("Mary", "Kila", "70123344", 4200, 300, 720)
    on = start + timedelta(days=5)
    loan, status = first_loan(mary)
    if loan is None:
        loan, status = apply(mary, 5000, 12, on), 100
        print("  + applied for K 5,000")
    if status == 100:
        f.post(f"/loans/{loan}?command=approve", {**DF, "approvedOnDate": on.isoformat(), "approvedLoanAmount": 5000,
                                                  "expectedDisbursementDate": on.isoformat()})
        status = 200
        print("  + approved")
    if status == 200:
        f.post(f"/loans/{loan}?command=disburse", {**DF, "actualDisbursementDate": on.isoformat()})
        status = 300
        print(f"  + disbursed {on:%d/%m/%Y}")
    if status == 300:
        txns = (f.get(f"/loans/{loan}?associations=transactions") or {}).get("transactions") or []
        if not any((t.get("type") or {}).get("repayment") for t in txns):
            paid = on + timedelta(days=30)
            f.post(f"/loans/{loan}/transactions?command=repayment", {
                **DF, "transactionDate": paid.isoformat(), "transactionAmount": 472.80,
                "paymentTypeId": have["mobile money"], "receiptNumber": "TEST-0001",
            })
            print("  + one payment made")

    for first, last, phone, income, debt, score, amount, months in [
        ("Peter", "Wambi", "71234567", 3500, 900, 610, 15000, 24),
        ("Joyce", "Ilave", "72345678", 1800, 700, 520, 8000, 12),
    ]:
        cid = borrower(first, last, phone, income, debt, score)
        if first_loan(cid)[0] is None:
            apply(cid, amount, months, TODAY - timedelta(days=1))
            print(f"  + applied for K {amount:,} over {months} months")

    print("\nDone. Passwords are shown only when a user is created (or with --new-passwords).")


if __name__ == "__main__":
    try:
        main()
    except FineractError as e:
        sys.exit(f"\nFineract refused a step: {e}\nCopy this message to Claude. Running the script again is safe.")
