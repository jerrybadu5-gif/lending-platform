# Configuring Mifos X for the lending company

Work through these in order after the first login. Menu paths are for the Mifos X web app (**Admin** menu, top right). Each step names the brief requirement it covers.

## 1. Organisation basics

| Step | Where | Setting |
|---|---|---|
| Change the default password | Profile → Settings | Do this first. Default is `mifos` / `password`. |
| Head office name | Organization → Manage Offices | Rename "Head Office"; add branches if any. |
| Currency | Organization → Currency Configuration | Add **PGK – Papua New Guinean Kina**; remove unused currencies. |
| Working days & holidays | Organization → Working Days / Holidays | Mon–Fri; add PNG public holidays so due dates move off them. |
| Staff | Organization → Manage Employees | Loan officers (needed to assign clients/loans). |

## 2. Users, roles, maker-checker *(brief: audit trail, approval control)*

1. **Admin → Users → Roles**: create at least `Loan Officer` (create clients/loans, record repayments), `Credit Manager` (approve, reject, disburse), `Accountant` (journal entries, reports), `Auditor` (read-only).
2. **Admin → System → Maker Checker Tasks**: tick *Approve loan*, *Disburse loan*, *Undo transaction*, *Write off*, *Create journal entry*. Turn it on in **Admin → System → Configurations → maker-checker**. The person who creates an action can't approve it.
3. **Admin → System → Audit Trails** shows every action with maker, checker, time and the full request. Nothing financial is deleted; mistakes are reversed with a visible reversing entry.

## 3. Chart of accounts *(brief: double-entry general ledger)*

**Accounting → Chart of Accounts.** A minimal set for a small lender:

| GL code | Name | Type |
|---|---|---|
| 1100 | Cash at bank | Asset |
| 1110 | Cash on hand / mobile money float | Asset |
| 1200 | Loan portfolio (principal outstanding) | Asset |
| 1210 | Interest receivable | Asset |
| 1220 | Fees & penalties receivable | Asset |
| 1290 | Loan loss provision | Asset (contra) |
| 2100 | Borrower overpayments | Liability |
| 3100 | Paid-up capital | Equity |
| 4100 | Interest income | Income |
| 4200 | Fee income | Income |
| 4300 | Penalty income | Income |
| 4400 | Recoveries of written-off loans | Income |
| 5100 | Loan write-offs | Expense |
| 5200 | Provision expense | Expense |

Use **accrual (periodic)** accounting if you report on an accrual basis, otherwise **cash**. Each loan product then maps to these accounts (step 5), and every disbursement, repayment, fee and write-off posts balanced debits and credits automatically. **Accounting → Accounting closure** locks a period so it can't be back-dated.

## 4. Charges *(brief: late penalties)*

**Products → Charges → Create charge**

- **Late payment penalty**: Applies to *Loan*, Time = *Overdue fees*, Calculation = *% of overdue principal + interest* (or Flat), *Penalty* ticked, frequency monthly if it should repeat.
- **Processing fee** (optional): Time = *Disbursement*, Calculation = Flat or % of amount.
- **Admin → System → Configurations**: set `penalty-wait-period` (grace days before the penalty applies).
- **Admin → System → Scheduler Jobs**: make sure *Apply penalty to overdue loans* and *Update loan arrears ageing* are active and running nightly.

## 5. Loan products *(brief: EMI, reducing balance, flat rate)*

**Products → Loan Products → Create.** Make one product per offer, e.g.:

| Setting | Personal loan (reducing) | Salary advance (flat) |
|---|---|---|
| Currency | PGK, 2 decimals | PGK |
| Principal min/default/max | 500 / 5,000 / 50,000 | 200 / 1,000 / 5,000 |
| Repayments | 3–36, every 1 month | 1–6, every 1 fortnight (2 weeks) |
| Nominal interest rate | per year | per year |
| Interest method | **Declining balance** | **Flat** |
| Amortisation | **Equal installments** (= EMI) | Equal installments |
| Interest calculation period | Same as repayment period | Same as repayment period |
| Repayment strategy (allocation) | Penalties, Fees, Interest, Principal | same |
| Arrears tolerance / grace | as policy | as policy |
| Charges | Late payment penalty, processing fee | same |
| Accounting | Accrual (periodic) → map to GL codes above | same |
| Allow partial period interest / pre-closure | On (for early repayment) | On |

## 6. Custom fields, KYC and documents *(brief: KYC & docs, intake form)*

- **Admin → System → Manage Codes**: fill `Customer Identifier` with *National ID*, *Passport*, *Driver's licence*, *NASFUND/Nambawan Super no.*; fill `Gender`, `ClientClassification` etc.
- Client identifiers and document uploads are on every client and loan screen (**Identities**, **Documents** tabs). Upload signed loan agreements as loan documents.
- Run `underwriting/bootstrap.py` (see README). It creates:
  - **Borrower financials** on clients: monthly income, existing monthly debt, credit score, business net operating income, income verified, income source.
  - **Loan assessment** on loans: recommendation, risk score, DTI, DSCR, max recommended principal, policy version, date, notes.
  - **Borrower profile** on clients: address, employer, payroll number, bank account, next of kin.
  - **Loan review** on loans (`dt_loan_review`): the loan officer's recommendation, amount and note, who sent it for
    approval and when, and the credit manager's note if sent back. McLender's approve and reject need it.
  - With `--gate`: loans can't be approved until an assessment exists.
- **Upgrading McLender**: run `underwriting/bootstrap.py` again after each upgrade (it only adds what's missing), and
  give the staff roles READ, CREATE and UPDATE on any new data table (Admin → Users → Roles → the role → Edit,
  "datatable" group). `deploy/setup-test.py` does both on a test server. Until `dt_loan_review` exists, McLender
  refuses to send applications for approval or decide them, with a message saying so.
- **McLender's own database** (from v0.2): set `MCLENDER_DB_PASSWORD` in `deploy/.env` (letters and digits;
  `deploy/setup-test.py` sets one on a test PC), then `docker compose up -d`. The `mclender-db-init` step creates
  the `mclender` database and user, and the API builds its tables on start-up. Sign-ins then survive restarts.
  `deploy/backup.ps1` backs it up with the Fineract databases.

## 7. Loan workflow *(brief: state machine)*

Brief states → Fineract states:

| Brief | Fineract | Action / who |
|---|---|---|
| DRAFT | (form not yet saved) | Loan officer |
| SUBMITTED | Submitted and pending approval | Loan officer saves the application |
| UNDER_REVIEW | Pending approval + assessment recorded | `assess.py` writes the assessment and a note |
| APPROVED / REJECTED | Approved / Rejected (or Withdrawn by applicant) | Credit manager, checked by maker-checker |
| DISBURSED | Active | Disburse (to cash, bank or savings) |
| CLOSED | Closed (obligations met) / Overpaid | Automatic on final repayment |
| DEFAULTED | Overdue → Written off | Arrears ageing, then write-off by credit manager |

Repayments, prepayments and partial payments are recorded on the loan (**Make Repayment**, **Prepay Loan**, **Foreclosure**). Use **Reschedule** or **Re-amortise** to recalculate after a large part-payment.

## 8. Reports *(brief: exportable ledger reports, compliance)*

**Reports** menu. Useful ones to check from day one:

- *Portfolio at Risk*, *Aging Detail*, *Active Loans – Summary/Details*, *Expected Payments*, *Obligation Met Loans*.
- Accounting: *Trial Balance*, *General Ledger*, *Balance Sheet*, *Income Statement*.
- Every report exports to CSV / Excel / PDF. Ad-hoc SQL reports can be added under **Admin → System → Manage Reports** for Bank of PNG returns.

## 9. Before going live

- [ ] All default passwords changed; `.env` passwords strong and stored safely.
- [ ] HTTPS in front of the web app and API (reverse proxy such as Caddy or IIS ARR with a certificate).
- [ ] `backup.ps1` scheduled nightly and a restore tested once.
- [ ] Image versions pinned in `.env`.
- [ ] Opening balances entered (existing loans imported via **Admin → Organization → Bulk Import** templates).
- [ ] One month parallel run reconciled against the current books.
