"""
Assess loan applications in Mifos X / Fineract and record the result on the loan.

    python assess.py --loan 42          # one loan
    python assess.py --pending          # every loan "Submitted and pending approval"
    python assess.py --pending --dry-run

Reads borrower data from the client's "dt_borrower_financials" data table and the
loan's own repayment schedule, then writes "dt_loan_assessment" and a loan note.
Connection settings come from FINERACT_URL / FINERACT_USER / FINERACT_PASSWORD /
FINERACT_TENANT. Policy thresholds come from policy.json next to this file.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from bootstrap import ASSESSMENT_TABLE, BORROWER_TABLE
from fineract import Fineract, FineractError
from risk import DECLINING_BALANCE, FLAT, Applicant, Assessment, LoanTerms, Policy, assess

PENDING_APPROVAL = 100
# Fineract repaymentFrequencyType ids -> periods per year for repaymentEvery=1
PERIODS_PER_YEAR = {0: Decimal(365), 1: Decimal(52), 2: Decimal(12), 3: Decimal(1)}


def load_policy() -> Policy:
    p = Path(__file__).with_name("policy.json")
    return Policy.from_dict(json.loads(p.read_text())) if p.exists() else Policy()


def dec(v) -> Decimal | None:
    return None if v is None or v == "" else Decimal(str(v))


def loan_terms(loan: dict) -> LoanTerms:
    every = int(loan.get("repaymentEvery") or 1)
    ppy = PERIODS_PER_YEAR[loan["repaymentFrequencyType"]["id"]] / every
    periods = [p for p in loan.get("repaymentSchedule", {}).get("periods", []) if p.get("period")]
    scheduled = None
    if periods:  # use Fineract's own schedule: exact for every product configuration
        total = sum(Decimal(str(p.get("totalDueForPeriod", 0))) for p in periods)
        scheduled = (total / len(periods)).quantize(Decimal("0.01"))
    return LoanTerms(
        principal=dec(loan.get("proposedPrincipal") or loan.get("principal")),
        annual_rate=dec(loan.get("annualInterestRate") or 0) / 100,
        installments=int(loan["numberOfRepayments"]),
        periods_per_year=ppy,
        interest_type=FLAT if loan.get("interestType", {}).get("id") == 1 else DECLINING_BALANCE,
        scheduled_installment=scheduled,
    )


def applicant(row: dict | None) -> Applicant:
    row = row or {}
    score = row.get("credit_score")
    return Applicant(
        monthly_income=dec(row.get("monthly_income")),
        existing_monthly_debt=dec(row.get("existing_monthly_debt")) or Decimal(0),
        credit_score=int(score) if score not in (None, "") else None,
        monthly_business_noi=dec(row.get("monthly_business_noi")),
    )


def record(f: Fineract, loan_id: int, a: Assessment, policy: Policy) -> None:
    f.upsert_datatable_row(ASSESSMENT_TABLE, loan_id, {
        "recommendation": a.recommendation,
        "risk_score": str(a.risk_score),
        "monthly_payment": str(a.monthly_payment),
        "dti": str(a.dti) if a.dti is not None else None,
        "dscr": str(a.dscr) if a.dscr is not None else None,
        "max_recommended_principal": str(a.max_recommended_principal),
        "policy_version": policy.version,
        "assessed_on": date.today().isoformat(),
        "notes": " | ".join(a.notes),
    })
    f.post(f"/loans/{loan_id}/notes",
           {"note": f"Underwriting ({policy.version}): {a.recommendation}, score {a.risk_score}. "
                    + " ".join(a.notes)})


def run(f: Fineract, loan_id: int, policy: Policy, dry_run: bool) -> None:
    loan = f.get(f"/loans/{loan_id}?associations=repaymentSchedule")
    terms = loan_terms(loan)
    app = applicant(f.datatable_row(BORROWER_TABLE, loan["clientId"]))
    a = assess(app, terms, policy)
    dti = f"{a.dti:.1%}" if a.dti is not None else "n/a"
    print(f"Loan {loan_id} ({loan.get('clientName')}): {a.recommendation:7} score {a.risk_score:>5} "
          f"DTI {dti:>6}  payment/mo {a.monthly_payment:,.2f}  cap {a.max_recommended_principal:,.2f}")
    for n in a.notes:
        print(f"    - {n}")
    if not dry_run:
        record(f, loan_id, a, policy)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--loan", type=int, help="loan id")
    g.add_argument("--pending", action="store_true", help="all loans pending approval")
    ap.add_argument("--dry-run", action="store_true", help="print results without writing to Fineract")
    args = ap.parse_args()

    f, policy = Fineract.from_env(), load_policy()
    ids = [args.loan] if args.loan else [l["id"] for l in f.loans(status_id=PENDING_APPROVAL)]
    if not ids:
        print("No loans pending approval.")
    for loan_id in ids:
        try:
            run(f, loan_id, policy, args.dry_run)
        except (FineractError, KeyError, ValueError) as e:
            print(f"Loan {loan_id}: skipped ({e})")


if __name__ == "__main__":
    main()
