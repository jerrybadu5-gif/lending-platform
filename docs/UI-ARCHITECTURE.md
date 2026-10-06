# McLender UI: architecture

**Status:** Accepted, built (see docs/MCLENDER.md for what exists now) · **Date:** 06/10/2026 · **Design:** McLender design system + app prototype (Claude artifacts)

## What we are building

One React app with two areas on top of the existing Fineract back end:

| Area | Users | Main jobs | Form |
|---|---|---|---|
| **Staff app** `/staff` | Loan officers, credit managers, accountants | Dashboard, client intake and KYC, loan applications with the affordability check, approve or reject, record repayments, collections list, reports | Desktop-first, works on a tablet |
| **Borrower portal** `/portal` | Borrowers | See what they owe and when, how to pay, payment history, apply for a loan | Mobile-first installable PWA, works on slow connections |

The Mifos X web app stays installed for admin tasks we don't rebuild, such as products, chart of accounts, roles and system configuration.

## Components

```
 Browser (staff PC / borrower phone)
   └─ mclender-web  React 18 + TypeScript + Vite, Tailwind with McLender tokens, TanStack Query, PWA service worker
        │ HTTPS, session cookie (never Fineract credentials in the browser)
        ▼
 mclender-api  FastAPI (Python 3.12), the back-end-for-front-end
   ├─ /staff/*   proxies Fineract with the staff member's own Fineract login (their roles and maker-checker still apply)
   ├─ /portal/*  borrower login by phone number + SMS one-time code; only ever reads that borrower's own loans
   ├─ underwriting  reuses underwriting/risk.py; runs on submit and writes dt_loan_assessment
   ├─ payments   adapter interface: bank-statement matching first, then mobile money (CellMoni, MiCash) and bank gateways
   └─ sms        adapter interface for receipts, reminders, one-time codes (provider chosen later)
        │
        ▼
 Fineract 1.15 (existing deploy/)  ──  PostgreSQL 16
 mclender-api's own tables (portal users, OTPs, sessions, payment imports) in a separate "mclender" database
```

Why a back end in the middle rather than the browser calling Fineract directly:

- Borrowers must never get Fineract credentials. Fineract's own self-service API is an option, but it would put every borrower on Fineract's user table and needs its own hardening.
- One place handles the affordability check, SMS, payment matching and rate limits.
- It keeps the Fineract URL off the internet: only `mclender-api` and the web app are public.

## Front-end structure

```
web/
├── src/design/        tokens.css + Tailwind theme generated from the design system's tokens.json
├── src/components/    Button, StatusPill, Money, StatTile, Field, DataTable, LoanStepper, AssessmentCard
│                      (TypeScript ports of the design system bundle, same props as its index.d.ts)
├── src/staff/         routes: dashboard, applications/:id, repayments, clients, reports
├── src/portal/        routes: home, apply, schedule, help (+ manifest.webmanifest, service worker)
├── src/api/           typed client for mclender-api, generated from its OpenAPI schema
└── tests/             Vitest unit tests + Playwright smoke tests for both areas
```

## Fineract state → UI words

| Fineract `status.code` | UI label (StatusPill) | LoanStepper step |
|---|---|---|
| `loanStatusType.submitted.and.pending.approval` | Pending approval | Submitted / Assessed (if an assessment exists) |
| `loanStatusType.approved` | Approved | Approved |
| `loanStatusType.active` | Active, or In arrears when `inArrears` | Disbursed / Repaying |
| `loanStatusType.closed.obligations.met` | Closed | Closed |
| `loanStatusType.rejected` / `withdrawn.by.client` | Rejected | (pill only) |
| `loanStatusType.closed.written.off` | Written off | (pill only) |

## Delivery plan (after design approval)

1. **Scaffold** `web/` and `api/`, CI, compose services `mclender-web` and `mclender-api` behind Caddy.
2. **Staff:** log in, then dashboard, then the application review with approve/reject, then repayments.
3. **Portal:** OTP login, then home, how to pay and history, then apply.
4. **Hardening:** rate limits, audit logging, Playwright smoke tests, backup of the `mclender` database.

## Decisions needed from Jerry

- An SMS provider for one-time codes and receipts, and whether mobile money comes in phase 1 or later.
- The company's real name and logo to replace "McLender".
- Hosting for the public portal: the office server behind a fixed IP, or a PNG/Australian VPS.
