"""
One-time setup: creates the data tables McLender uses (borrower financials, borrower
profile, loan assessment), the code values it needs (Gender, National ID), and,
optionally, blocks loan approval until an assessment exists.

    python bootstrap.py                 # create data tables
    python bootstrap.py --gate          # ...and require an assessment before APPROVE

Safe to re-run: existing tables/checks are skipped.
"""
from __future__ import annotations

import argparse

from fineract import Fineract, FineractError

BORROWER_TABLE = "dt_borrower_financials"
PROFILE_TABLE = "dt_borrower_profile"
ASSESSMENT_TABLE = "dt_loan_assessment"
LOAN_APPROVE_STATUS = 200  # Fineract StatusEnum.APPROVE for entity m_loan

TABLES = [
    {
        "datatableName": BORROWER_TABLE,
        "apptableName": "m_client",
        "entitySubType": "PERSON",  # required by Fineract 1.10+ for client tables
        "multiRow": False,
        "columns": [
            {"name": "monthly_income", "type": "decimal", "mandatory": True},
            {"name": "existing_monthly_debt", "type": "decimal", "mandatory": True},
            {"name": "credit_score", "type": "number", "mandatory": False},
            {"name": "monthly_business_noi", "type": "decimal", "mandatory": False},
            {"name": "income_verified", "type": "boolean", "mandatory": False},
            {"name": "income_source", "type": "string", "length": 100, "mandatory": False},
        ],
    },
    {
        # Address, employer, bank account and next of kin. Kept apart from the financials so the
        # borrower portal's technical user can be denied access to bank details.
        "datatableName": PROFILE_TABLE,
        "apptableName": "m_client",
        "entitySubType": "PERSON",
        "multiRow": False,
        "columns": [
            {"name": "address", "type": "string", "length": 200, "mandatory": False},
            {"name": "employer", "type": "string", "length": 100, "mandatory": False},
            {"name": "payroll_number", "type": "string", "length": 30, "mandatory": False},
            {"name": "bank_name", "type": "string", "length": 60, "mandatory": False},
            {"name": "bank_branch", "type": "string", "length": 60, "mandatory": False},
            {"name": "bank_account_name", "type": "string", "length": 100, "mandatory": False},
            {"name": "bank_account_number", "type": "string", "length": 30, "mandatory": False},
            {"name": "nok_name", "type": "string", "length": 100, "mandatory": False},
            {"name": "nok_relationship", "type": "string", "length": 40, "mandatory": False},
            {"name": "nok_phone", "type": "string", "length": 20, "mandatory": False},
        ],
    },
    {
        "datatableName": ASSESSMENT_TABLE,
        "apptableName": "m_loan",
        "multiRow": False,
        "columns": [
            {"name": "recommendation", "type": "string", "length": 10, "mandatory": True},
            {"name": "risk_score", "type": "decimal", "mandatory": True},
            {"name": "monthly_payment", "type": "decimal", "mandatory": True},
            {"name": "dti", "type": "decimal", "mandatory": False},
            {"name": "dscr", "type": "decimal", "mandatory": False},
            {"name": "max_recommended_principal", "type": "decimal", "mandatory": True},
            {"name": "policy_version", "type": "string", "length": 20, "mandatory": True},
            {"name": "assessed_on", "type": "date", "mandatory": True},
            {"name": "notes", "type": "text", "mandatory": False},
        ],
    },
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", action="store_true",
                    help=f"require a {ASSESSMENT_TABLE} entry before a loan can be approved")
    args = ap.parse_args()
    f = Fineract.from_env()

    existing = {t["registeredTableName"] for t in f.get("/datatables")}
    for spec in TABLES:
        name = spec["datatableName"]
        if name in existing:
            print(f"= {name} already exists")
            continue
        f.post("/datatables", spec)
        print(f"+ created {name} on {spec['apptableName']}")

    ensure_code_values(f, "Gender", ["Female", "Male"])
    ensure_code_values(f, "Customer Identifier", ["National ID (NID)"])

    if args.gate:
        checks = f.get("/entityDatatableChecks?limit=500")
        items = checks.get("pageItems", checks) if isinstance(checks, dict) else checks
        if any(c.get("datatableName") == ASSESSMENT_TABLE and c.get("status", {}).get("id") == LOAN_APPROVE_STATUS
               for c in items):
            print("= approval gate already exists")
        else:
            try:
                f.post("/entityDatatableChecks",
                       {"entity": "m_loan", "status": LOAN_APPROVE_STATUS, "datatableName": ASSESSMENT_TABLE})
                print("+ loans now need an assessment before approval")
            except FineractError as e:
                print(f"! could not create approval gate: {e}")


def ensure_code_values(f: Fineract, code_name: str, wanted: list[str]) -> None:
    """Add any missing values to one of Fineract's built-in codes (dropdown lists)."""
    code = next((c for c in f.get("/codes") if c.get("name", "").lower() == code_name.lower()), None)
    if code is None:
        print(f"! Fineract has no code called {code_name!r}; add it in Admin > System > Manage codes")
        return
    have = {v["name"].strip().lower() for v in f.get(f"/codes/{code['id']}/codevalues")}
    for pos, name in enumerate(wanted, 1):
        if name.lower() in have:
            print(f"= {code_name}: {name}")
        else:
            f.post(f"/codes/{code['id']}/codevalues", {"name": name, "position": pos, "isActive": True})
            print(f"+ {code_name}: {name}")


if __name__ == "__main__":
    main()
