# Decision: Adopt Mifos X / Apache Fineract instead of building the LMS from scratch

**Date:** 2026-10-06 · **Status:** Recommended · **Owner:** Jerry

## Verdict

An existing platform is sufficient. **Mifos X (Apache Fineract 1.15.0 back end + Mifos X web app)** covers roughly 90% of the architecture brief out of the box, on the same PostgreSQL database the brief specifies. The one real gap is the automated affordability / risk-scoring step, which is small and is supplied here as an add-on (`underwriting/`) that talks to Fineract through its REST API, instead of a parallel custom stack.

Building the brief from scratch would mean re-creating, and then auditing, a double-entry ledger, a loan state machine, re-amortisation, penalties, maker-checker and regulatory reports: 9+ weeks of work that Fineract already ships, tested by microfinance institutions in production for over a decade.

## Fit-gap against the brief

| Brief requirement | Mifos X / Fineract | Notes |
|---|---|---|
| PostgreSQL ACID store | ✅ Native | PostgreSQL is a supported database (MariaDB too). |
| Double-entry general ledger, immutable postings | ✅ Native | Chart of accounts, cash or accrual accounting per product, journal entries auto-posted, reversals instead of deletes. |
| Audit trail | ✅ Native | Every command is logged with maker, checker, timestamp and JSON payload (Admin → Audit). |
| EMI, reducing balance, flat interest | ✅ Native | `interestType` = Declining Balance or Flat; amortisation = Equal Installments (EMI) or Equal Principal. |
| Late penalties | ✅ Native | Overdue installment charges (flat or % of overdue), applied by the scheduled job. |
| Loan states DRAFT→…→CLOSED/DEFAULTED | ✅ Native | Submitted & pending approval → Approved → Active (disbursed) → Closed (obligations met), plus Rejected, Withdrawn, Written-off, Overpaid, Rescheduled. "Draft" is the unsaved application in the UI. |
| Partial / early repayment, re-amortisation | ✅ Native | Configurable allocation order, pre-closure, loan rescheduling, "re-amortise" and "re-age" transactions. |
| KYC & document attachments | ✅ Native | Client identifiers (national ID etc.), document uploads on clients and loans, client photos/signatures. |
| Custom intake fields (income, existing debt, credit score) | ✅ Native | Data tables (custom fields) attached to clients / loans, shown in the UI. |
| Approval gating | ✅ Native | Maker-checker per action; "Entity data table checks" can block approval until an assessment exists. |
| Regulatory / ledger reports, export | ✅ Native | 100+ built-in reports (PAR, aging, trial balance, balance sheet, income statement), CSV/PDF/Excel export, BIRT/Pentaho. |
| REST / OpenAPI | ✅ Native | Swagger at `/fineract-provider/swagger-ui/index.html`. |
| Automated DTI / affordability / risk score | ⚠️ Gap | Fineract stores the data but does not score it. Filled by `underwriting/` (≈300 lines of Python). |
| Credit bureau pull | ⚠️ Partial | Credit-bureau integration framework exists (Thitsaworks/Myanmar only). For PNG, enter the bureau score manually into the data table, or extend `underwriting/` later. |
| E-signature records | ⚠️ Partial | Store signed PDFs as loan documents; no built-in e-sign workflow. |
| React 18 front end | ➖ Different | The web app is Angular. Use it as-is; build a React borrower portal later against the same API if needed. |

## Why Mifos X over Frappe Lending

| | Mifos X / Fineract | Frappe Lending |
|---|---|---|
| Purpose | Built for microfinance / small lenders | Lending module on top of ERPNext |
| Licence | Apache 2.0 (Fineract), MPL 2.0 (web app) | GPL 3.0 |
| Footprint | Fineract + DB + web app | Full ERPNext + Frappe + MariaDB + Redis |
| Database | **PostgreSQL** (matches brief) or MariaDB | MariaDB primarily |
| Fit | Portfolio accounting, PAR, maker-checker, data tables ready | Strong if you also want full ERP (HR, inventory, payroll); several features are India-specific (co-lending, GST) |

Choose Frappe Lending instead only if the company also wants ERPNext as its main accounting/HR system.

## Issues found in the brief's sample code (another reason not to build from it)

- EMI and max-loan maths use `float`, which leaks rounding error into money. The add-on uses `Decimal` only.
- `generate_amortization_schedule` returns an **empty schedule for flat-rate loans**.
- Due dates are clamped to day 28 and never return to day 29–31: a loan starting 31 Jan drifts to the 28th forever.
- The SQL schema has no ledger / journal tables despite "double-entry", no audit table, and `is_paid` cannot represent partial payments.
- Risk score subtracts `(dti-0.30)*100` points, so a DTI of 1.3 alone zeroes the score while credit has a small effect. The add-on weights both and documents the formula.

## Phase plan (revised)

1. **Week 1:** Deploy (`deploy/`), set office, currency PGK, timezone Pacific/Port_Moresby, chart of accounts, users and roles.
2. **Week 2:** Configure loan products, penalties, maker-checker, and run `underwriting/bootstrap` to create the data tables and approval gate.
3. **Week 3:** Pilot with real loans in parallel with the current process; check reports against the existing books.
4. **Week 4+:** Production hardening (TLS, backups, monitoring), then optional items: borrower portal, SMS reminders, mobile money integration.
