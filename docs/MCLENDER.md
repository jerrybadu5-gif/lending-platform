# McLender: how it works

**System:** McLender · **Company:** Breez Lending · **Updated:** 07/10/2026

## Pieces

```
 Staff PC / borrower phone
   └─ McLender web (React + TypeScript, served by Caddy)     /staff, /portal (PWA)
        │  HTTPS, signed HttpOnly session cookie; no Fineract password ever reaches the browser
        ▼
 McLender API (FastAPI)                                        /api/staff/*, /api/portal/*
   ├─ staff calls run as the signed-in staff member in Fineract (their roles and maker-checker apply)
   ├─ portal calls run as a limited "portal" Fineract user and only ever read the signed-in borrower's loans
   ├─ affordability check (app/domain/risk.py), stored in Fineract data table dt_loan_assessment
   ├─ borrowers: Fineract clients + NID identifier + data tables dt_borrower_financials, dt_borrower_profile
   ├─ KYC files: Fineract client documents (type checked from the file's first bytes, 5 MB limit)
   └─ PDFs (app/pdf.py, ReportLab): loan agreement, repayment schedule, statement, receipt
   └─ SMS interface (console for now; Digicel PNG and Vodafone PNG adapters at shipping time)
        │
        ▼
 Apache Fineract 1.15 ── PostgreSQL 16          Mifos X web app for admin (products, accounts, users)
```

The API has two back ends behind one interface (`api/app/backends/base.py`):

- **demo:** sample Breez Lending data dated relative to today, used for development, training and tests. It resets when the API restarts.
- **fineract:** the real Fineract REST API.

## Screens

| Screen | Path | Notes |
|---|---|---|
| Staff sign-in | `/staff/login` | Fineract username and password |
| Dashboard | `/staff` | Gross portfolio, active loans, PAR30, due today, waiting approvals, arrears by age |
| Applications | `/staff/applications` | Pending (with the check result), approved and not disbursed, rejected |
| Loan review | `/staff/loans/:id` | Borrower facts, schedule, affordability card, approve (amount defaults to policy capacity), reject (reason required, confirmed, SMS sent), record disbursement, history |
| Borrowers | `/staff/borrowers` | Search by name, phone, NID or employer |
| New / edit borrower | `/staff/borrowers/new`, `/staff/borrowers/:id/edit` | Personal details, NID, contact, employer and payroll number, income, bank account for payout, next of kin. Must be 18+; phone and NID must be unique |
| Borrower profile | `/staff/borrowers/:id` | Details, KYC checklist with uploads (ID, payslips, bank statement, payroll deduction authority), documents on file, loans, new loan application (checked at once) |
| Repayments | `/staff/repayments` | Due today, in arrears, all open; record a repayment by method with a reference; receipt plus SMS |
| Pay-out steps | Loan review, once approved | 1 print the agreement; 2 tell the borrower to come and sign (SMS sent automatically on approval; send again or log a phone call, each saved as a loan note); 3 upload the signed agreement to the loan; 4 record the pay-out (bank transfer, mobile money or cash, account and reference), which needs step 3. The borrower gets an SMS when the money is paid out |
| Printed documents | Loan review, repayment receipt | Loan agreement (once approved; marked DRAFT until `MCL_AGREEMENT_REVIEWED=true`), repayment schedule, statement, receipts, all PDF |
| Borrower sign-in | `/portal/login` | Phone, then a 6-digit SMS code valid for 5 minutes, 5 tries |
| Borrower home | `/portal` | Left to pay, progress, next or overdue payment, ways to pay with reference, recent payments, statement and schedule PDFs |
| Apply | `/portal/apply` | Amount and term chips, live quote, income and debts, sends an application that is checked at once |

## Security

- Sessions live on the server. The HttpOnly, SameSite=Strict cookie holds only a random session id, signed with `MCL_SESSION_SECRET`; the staff member's Fineract key never leaves the server. Sessions expire after `MCL_SESSION_HOURS`, and signing out ends them.
- Staff sign-in is limited to 10 tries per 5 minutes per user and address. SMS codes are limited to 5 requests per 15 minutes per number and per address. The code request answers the same way for unknown numbers, so it can't be used to find out who borrows from Breez Lending.
- Approve, reject and disburse need a credit manager role in McLender, and Fineract's own permissions and maker-checker still apply.
- KYC uploads: the file type is read from the file's first bytes (PDF, JPEG, PNG only), never from its name; names are cleaned; 5 MB limit, the same as Fineract's (`MCL_MAX_UPLOAD_MB`). Downloads are always sent as attachments, never shown inline. The KYC check runs at approval and again at disbursement. The portal's Fineract user has no access to bank or next-of-kin details (`dt_borrower_profile`) or to documents.
- Loans can't be paid out until the signed agreement is uploaded to the loan (`MCL_SIGNED_AGREEMENT_REQUIRED`); only credit managers record pay-outs.
- Loans can't be approved until the borrower's KYC documents are on file (`MCL_KYC_REQUIRED`, `MCL_KYC_REQUIRED_FOR_APPROVAL`).
- Money is `Decimal` in Python and a decimal string in JSON and in the browser. No floating-point maths touches amounts.
- Caddy sends a strict Content-Security-Policy and other security headers. The API sends `Cache-Control: no-store`. The service worker caches the app shell only, never API answers.
- Run **one API worker**: SMS codes and rate limits live in memory. Move them to the database before running more than one.

## Checking against Fineract

The Fineract back end is tested against recorded Fineract response shapes (`api/tests/test_fineract_backend.py`) and is being checked against a live Fineract with [LIVE-TESTING.md](LIVE-TESTING.md).

## Decisions still open

| Decision | When | Where it plugs in |
|---|---|---|
| SMS: Digicel PNG and Vodafone PNG | Shipping | `api/app/sms.py` (one class per provider; route by number prefix) |
| Server: office or hosted | Shipping | `deploy/.env` `MCLENDER_SITE_ADDRESS`, `MCL_COOKIE_SECURE` |
| Mobile money collection (CellMoni, MiCash) | After launch | New payment adapter; repayments already record the method and reference |
| Real logo and brand assets | Any time | `design/mclender-ds`, `web/public/icon.svg` |
