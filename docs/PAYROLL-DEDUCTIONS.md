# Payroll deduction files

Many Breez Lending borrowers repay through their employer's payroll. Each pay period (fortnightly for the PNG public
service) the employer deducts the instalment from the borrower's pay and sends Breez Lending one payment plus a list
of who it was for. McLender will import that list and post each line as a repayment.

This page describes the file McLender expects. **It is a draft**: compare it with real files from the employers
(Department of Finance / Alesco for the public service, and each private employer) before the import is built,
and note any differences at the end of this page.

## The file

A CSV (or an Excel sheet saved as CSV), one row per deduction. Extra lines above the column headings (employer name,
pay period) and a total line at the end are allowed and ignored.

| Column | Required | Example | Used for |
|---|---|---|---|
| Pay Period | yes | `21` | the batch name, and spotting the same period imported twice |
| Pay Date | yes | `09/10/2026` (dd/mm/yyyy) | the repayment date in Fineract |
| Employee No | one of these three | `T-3344` | matching: the borrower's payroll number in McLender |
| NID Number | | `2015 6612 0034` | matching when there is no employee number |
| Loan Reference | | `LN-000536` | matching when the borrower has more than one loan |
| Surname, Given Names | yes | `KILA`, `Mary` | a check that the match is the right person |
| Deduction Code | no | `BRZ01` | lines with another lender's code are skipped |
| Amount (PGK) | yes | `472.80` | the repayment amount |

## What happens to each line (planned)

1. **Matched**: one active loan found by employee number (or NID, or loan reference) and the name agrees. Posted as a
   "Payroll Deduction" repayment, reference `PAY-<employer>-<period>-<employee no>`, receipt and SMS as usual.
2. **Short or over**: matched, but the amount differs from the instalment due. Posted as received; listed so staff can
   follow up a short payment or decide what to do with the extra.
3. **Needs checking**: no employee number match, but a name match only, or the name disagrees. Not posted until
   staff pick the loan.
4. **Not ours**: nobody matches. Not posted; listed to send back to the employer.
5. **Duplicate**: the same employee and amount twice in one file, or a period already imported. Not posted twice.

Nothing is posted until staff have seen the preview and confirmed. The batch (file, who imported it, what was posted
and what wasn't) is kept as a record, and the total posted must equal the money received from the employer.

## The sample file

[`samples/payroll-deductions-sample.csv`](samples/payroll-deductions-sample.csv) is made up. It uses the three test
borrowers that `deploy/setup-test.py` creates (payroll numbers `T-3344`, `T-4567`, `T-5678`) and covers every case:

| Line | Expected result |
|---|---|
| Mary Kila, T-3344, K 472.80 | Matched: her monthly instalment |
| Peter Wambi, T-4567, K 793.07 | Matched, once his K 15,000 / 24-month loan is approved and paid out (it's only an application after setup) |
| Joyce Ilave, T-5678, K 700.00 | Short by K 56.48 once her K 8,000 / 12-month loan is paid out (instalment K 756.48) |
| Mary Kila, no employee number, K 50.00 | Needs checking: name only |
| Grace Tom, T-9001 | Not ours: no such borrower in the live test |
| Peter Wambi, T-4567 again | Duplicate |
| TOTAL | Ignored (but checked against the sum of the lines: K 3,428.94) |

## To decide

- The test loan product repays **monthly**, but the public service is paid **fortnightly**. Payroll loans should
  probably repay fortnightly too (a fortnightly loan product in Fineract), so each deduction matches one instalment.
- Whether a short payment is followed up by the loan officer, the employer, or both.
- What to do with an overpayment: keep it against the next instalment (Fineract's default) or refund it.

## Differences found in real files

_Add here what real employer files look like: column names, date format, header lines, how amounts are written._
