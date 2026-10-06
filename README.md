# McLender

Open-source loan management for **Breez Lending**, Port Moresby, Papua New Guinea.

McLender is a staff app and a borrower portal on top of [Apache Fineract](https://fineract.apache.org/), the open-source core banking platform. Fineract keeps the ledger, the loan accounts and the audit trail. McLender adds the screens staff and borrowers use every day, plus an affordability check.

| | What it does |
|---|---|
| **Staff app** `/staff` | Dashboard (portfolio, PAR30, arrears by age, due today), loan applications with the affordability check, approve or reject with a reason, record disbursement, collections list, record repayments by cash, bank transfer, mobile money or payroll, with an SMS receipt |
| **Borrower portal** `/portal` | Sign in with phone number and SMS code, see what is left to pay and when, how to pay with a payment reference, payment history, loan quote and application. Installable on a phone (PWA) |
| **Affordability check** | Debt-to-income, debt service cover, credit score and a 0–100 risk score, giving APPROVE, REFER or DECLINE. It recommends only; a credit manager decides |

Why Fineract instead of building a ledger from scratch: [docs/DECISION.md](docs/DECISION.md). How the pieces fit: [docs/MCLENDER.md](docs/MCLENDER.md).

```
lending-platform/
├── api/            McLender API (Python, FastAPI): sits between the web app and Fineract
├── web/            McLender web app (React + TypeScript): staff app and borrower portal
├── deploy/         Docker Compose: PostgreSQL, Fineract, Mifos X admin, McLender API and web, backups
├── underwriting/   Data table setup for Fineract (bootstrap.py) and the stand-alone assessment script
├── design/         McLender design system files (tokens, components)
└── docs/           Decision record, architecture, Fineract configuration guide
```

## Try it in 2 minutes (sample data, no Fineract needed)

You need Python 3.12+ and Node 22+.

**On Windows:** open PowerShell in this folder and run `powershell -ExecutionPolicy Bypass -File .\start-demo.ps1`. It installs what's needed, starts McLender and opens the browser. Then follow the checklist in [docs/TESTING.md](docs/TESTING.md).

**By hand (any system):**

```bash
# 1. API with sample data
cd api
pip install -e ".[dev]"
MCL_DEV_SMS_INBOX=true uvicorn app.main:app --port 8000      # Windows PowerShell: $env:MCL_DEV_SMS_INBOX="true"; uvicorn ...

# 2. Web app (second terminal)
cd web
npm install
npm run dev
```

- Staff app: http://localhost:5173/staff, sign in as `demo` / `demo` (credit manager) or `officer` / `officer` (loan officer).
- Borrower portal: http://localhost:5173/portal, phone `7012 3344` (Mary Kila). The SMS code is printed in the API terminal, and also shown at http://localhost:8000/api/dev/sms/70123344.
- API documentation: http://localhost:8000/docs

Sample data resets every time the API restarts.

## Run it for real (with Fineract)

1. Follow [deploy/](deploy/) and [docs/CONFIGURATION.md](docs/CONFIGURATION.md) to start Fineract and set up the products, chart of accounts and payment types (`Cash`, `Bank Transfer`, `Mobile Money`, `Payroll Deduction`).
2. Run `python underwriting/bootstrap.py --gate` once to create the data tables McLender uses.
3. In Mifos X, create a user `portal` with a role that can only read clients and loans, create loans, and read and write data tables.
4. In `deploy/.env`, set `MCL_BACKEND=fineract`, `MCL_SESSION_SECRET`, `MCL_FINERACT_PORTAL_USER` and `MCL_FINERACT_PORTAL_PASSWORD`, then run `docker compose up -d --build`.
5. Open http://localhost:8088/staff and sign in with a Fineract username and password.

## Checks

| | Command | Status |
|---|---|---|
| API | `cd api && ruff check app tests && mypy app && pytest` | 51 tests pass |
| Web | `cd web && npm run lint && npm run typecheck && npm test && npm run build` | 9 unit tests pass |
| End to end | `cd web && npm run build && npm run e2e` | 5 browser tests pass (staff on desktop, portal on a phone) |
| CI | `.github/workflows/ci.yml` runs all of the above, plus dependency audits and Docker builds, on every pull request | |

## Not decided yet (at shipping time)

- **SMS:** Digicel PNG and Vodafone PNG. McLender sends every SMS through one small interface (`api/app/sms.py`), so both adapters go in there. Until then, messages are written to the log.
- **Server:** office server or hosted VPS. With a domain name in `MCLENDER_SITE_ADDRESS`, Caddy gets an HTTPS certificate automatically.

## Licence

MIT, copyright Jerry Badu. Apache Fineract is Apache 2.0; the Mifos X web app is MPL 2.0.
