import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk import FLAT, Applicant, LoanTerms, Policy, assess, installment, max_principal  # noqa: E402
from assess import loan_terms  # noqa: E402


def test_emi_matches_standard_formula():
    # 15,000 at 10% p.a. over 12 months -> 1,318.74 (standard EMI tables / Excel PMT)
    assert installment(D("15000"), D("0.10"), 12) == D("1318.74")


def test_zero_rate():
    assert installment(D("1200"), D("0"), 12) == D("100.00")


def test_flat_rate():
    # 10,000 at 12% flat for 12 months: interest 1,200 -> 11,200 / 12
    assert installment(D("10000"), D("0.12"), 12, interest_type=FLAT) == D("933.33")


def test_weekly_frequency():
    weekly = installment(D("5200"), D("0.26"), 52, periods_per_year=D(52))
    r = 0.26 / 52  # independent float check, to the cent
    expected = 5200 * r * (1 + r) ** 52 / ((1 + r) ** 52 - 1)
    assert abs(weekly - D(str(round(expected, 2)))) <= D("0.01")


def test_max_principal_is_inverse_of_installment():
    for itype in ("DECLINING_BALANCE", FLAT):
        pay = installment(D("20000"), D("0.18"), 24, interest_type=itype)
        cap = max_principal(pay, D("0.18"), 24, interest_type=itype)
        assert abs(cap - D("20000")) < D("1.00")
        assert installment(cap, D("0.18"), 24, interest_type=itype) <= pay


def test_brief_example_is_approved():
    # The worked example from the architecture brief
    a = assess(Applicant(D("5000"), D("400"), 680), LoanTerms(D("15000"), D("0.10"), 12))
    assert a.recommendation == "APPROVE"
    assert a.monthly_payment == D("1318.74")
    assert a.dti == D("0.3437")
    assert a.max_recommended_principal >= D("15000")


def test_high_dti_declines():
    a = assess(Applicant(D("2000"), D("500"), 720), LoanTerms(D("15000"), D("0.10"), 12))
    assert a.recommendation == "DECLINE"


def test_borderline_dti_refers():
    # DTI ~42% -> within the 5pp refer band
    a = assess(Applicant(D("4000"), D("360"), 700), LoanTerms(D("15000"), D("0.10"), 12))
    assert a.recommendation == "REFER"


def test_low_credit_declines_borderline_refers():
    terms = LoanTerms(D("5000"), D("0.10"), 12)
    assert assess(Applicant(D("5000"), D("0"), 550), terms).recommendation == "DECLINE"
    assert assess(Applicant(D("5000"), D("0"), 590), terms).recommendation == "REFER"


def test_missing_data_never_approves():
    terms = LoanTerms(D("5000"), D("0.10"), 12)
    assert assess(Applicant(None), terms).recommendation == "REFER"
    assert assess(Applicant(D("9000"), D("0"), None), terms).recommendation == "REFER"


def test_low_dscr_refers():
    a = assess(Applicant(D("8000"), D("0"), 750, monthly_business_noi=D("1000")),
               LoanTerms(D("15000"), D("0.10"), 12))
    assert a.dscr == D("0.76") and a.recommendation == "REFER"


def test_score_bounds_and_monotonic():
    terms = LoanTerms(D("5000"), D("0.10"), 12)
    good = assess(Applicant(D("10000"), D("0"), 800), terms).risk_score
    worse = assess(Applicant(D("10000"), D("0"), 650), terms).risk_score
    assert D(0) <= worse < good <= D(100)


def test_policy_from_json_dict():
    p = Policy.from_dict({"max_dti": "0.35", "min_credit_score": 650, "unknown": 1})
    assert p.max_dti == D("0.35") and p.min_credit_score == 650


def test_loan_terms_from_fineract_payload():
    loan = {
        "proposedPrincipal": 15000.0, "annualInterestRate": 10.0, "numberOfRepayments": 12,
        "repaymentEvery": 1, "repaymentFrequencyType": {"id": 2}, "interestType": {"id": 0},
        "repaymentSchedule": {"periods": [{"principalDisbursed": 15000}] +
                              [{"period": i, "totalDueForPeriod": 1318.74} for i in range(1, 12)] +
                              [{"period": 12, "totalDueForPeriod": 1318.77}]},
    }
    t = loan_terms(loan)
    assert t.principal == D("15000.0") and t.annual_rate == D("0.1") and t.periods_per_year == 12
    assert t.scheduled_installment == D("1318.74")
