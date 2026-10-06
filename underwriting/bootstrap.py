"""
One-time setup: creates the custom fields the underwriting step needs and,
optionally, blocks loan approval until an assessment exists.

    python bootstrap.py                 # create data tables
    python bootstrap.py --gate          # ...and require an assessment before APPROVE

Safe to re-run: existing tables/checks are skipped.
"""
from __future__ import annotations

import argparse

from fineract import Fineract, FineractError

BORROWER_TABLE = "dt_borrower_financials"
ASSESSMENT_TABLE = "dt_loan_assessment"
LOAN_APPROVE_STATUS = 200  # Fineract StatusEnum.APPROVE for entity m_loan

TABLES = [
    {
        "datatableName": BORROWER_TABLE,
        "apptableName": "m_client",
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


if __name__ == "__main__":
    main()
