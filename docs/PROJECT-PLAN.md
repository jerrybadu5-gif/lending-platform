# McLender project plan

**The key document for completing McLender.** Agreed with Jerry Badu on 8 October 2026. The editable version with drawings is the Claude doc at https://claude.ai/code/artifact/293c9b87-59ec-44ad-8b66-9de19b3f37ae; this copy in the repository is updated whenever the plan changes, through the same branch and pull request steps as the code.

McLender goes live at Breez Lending with a pilot from 19 April 2027 and go-live on 17 May 2027, after six build phases of two to six weeks each. Every feature is tested live by Jerry before it reaches GitHub `main`, and each phase ends with a tagged release.

## Where we are

- **Built (prototype, v0.1 to v0.2):** borrower sign-up and KYC documents, ID card reading, loan applications with an affordability check, loan officer review and credit manager decision, pay-out steps with the signed agreement, repayments with receipts, PDFs (agreement, schedule, statement, receipt), borrower portal, forgiving search, staff in separate tabs. Merged as PRs 11 to 14; PR 15 (live-test fixes) is open.
- **Runs on:** Apache Fineract (the loan engine and ledger) and Mifos X (its admin screens), with McLender's own API and web app in front, all in Docker on Jerry's PC for testing.

## What "complete" means for the pilot

- Breez Lending only, one office first, built for several branches.
- Hosted on an office server at Breez.
- Must have before the pilot: collections and reminders, payroll deductions, reports and exports, accounting, an administrator area (users, roles, branches, approval limits, products, settings, branding, audit log), borrower portal, and existing loans moved in.
- Connected to SMS, email, bank and mobile-money statements, and the PNG credit bureau, as far as contracts allow by then.

## Scope

Sixteen modules make the complete system; thirteen are still to build or finish, and all but the last one are needed for the pilot.

| Module | What it covers | Status | Phase |
| --- | --- | --- | --- |
| Borrowers and KYC | Sign-up, documents, ID card reading, search, photo | Done | – |
| Applications and decisions | Affordability check, officer review, manager decision | Done (PR 15 open) | 0 |
| Pay-out | Agreement, borrower contact, signed copy, disbursement | Done | – |
| Repayments and receipts | Record, receipt PDF filed on the loan, SMS | Done | – |
| Borrower portal | Phone sign-in, balance, statements, apply | Done; needs real SMS | 5 |
| Administration | Users, roles, branches, approval limits, products, settings, branding (colours, logo), password reset, two-step sign-in | To build | 1 |
| Audit log | Who did what and when, searchable, export for auditors | To build | 1 |
| Collections | Daily call list, follow-up log, promises to pay, reminders, penalties and waivers, arrears dashboard | To build | 2 |
| Payroll deductions | Import employer files, match, post in bulk, exceptions | To build; needs a real file | 3 |
| Bank and mobile money | Import BSP, Kina Bank, CellMoni, MiCash statements and match repayments | To build | 3 |
| Accounting | Chart of accounts, journal entries for every loan event, month-end, trial balance | To set up in Fineract | 4 |
| Reports and exports | Portfolio, arrears by age, disbursements, collections, income, staff activity; Excel and PDF; Bank of PNG returns | To build | 4 |
| SMS and email | Digicel or Vodafone SMS; email for agreements, statements, receipts | To connect | 5 |
| Credit bureau | Credit check at application | To connect | 5 |
| Production and migration | Office server, backups, remote access, monitoring, existing loans moved in, training | To do | 6 |
| Product for other lenders | Several companies on one system, own branding, support | After the pilot | – |

## Phases and timeline

The pilot starts on 19 April 2027 after six build phases; go-live follows a four-week parallel run. SMS, email and the credit bureau (P5) run alongside P3 and P4, because they depend on contracts with outside companies, not on code.

| Phase | Dates (planned) | Release |
| --- | --- | --- |
| P0 · Stabilise | 12 Oct – 23 Oct 2026 | v0.2 |
| P1 · Administration and audit | 26 Oct – 4 Dec 2026 | v0.3 |
| P2 · Collections and reminders | 7 Dec 2026 – 15 Jan 2027 | v0.4 |
| P3 · Payroll and statements | 18 Jan – 12 Feb 2027 | v0.5 |
| P5 · SMS, email, credit bureau | 18 Jan – 19 Mar 2027 (alongside P3, P4) | in v0.5 / v0.6 |
| P4 · Accounting and reports | 15 Feb – 19 Mar 2027 | v0.6 |
| P6 · Server, migration, training | 22 Mar – 16 Apr 2027 | v0.9 (release candidate) |
| P7 · Pilot, parallel run | 19 Apr – 14 May 2027 | – |
| Go-live | 17 May 2027 | v1.0 |

**P0 · Stabilise (2 weeks).** Merge PR 15, retest live, tag v0.2. Move sessions and rate limits from memory into the database, so a restart doesn't sign everyone out. Exit: all live-test items pass.

**P1 · Administration and audit (6 weeks).** An admin role and screens for users, roles and permissions, branches (staff see their own branch), approval limits per role, loan products, fees and penalties, KYC document list, SMS wording, company details, colours and logo; password reset and two-step sign-in; a searchable audit log. Exit: an admin sets up a new branch and staff without Mifos X. Release v0.3.

**P2 · Collections and reminders (6 weeks, includes the Christmas break).** Daily call list, follow-up log, promises to pay, reminders before and after the due date, penalties with manager waivers, arrears dashboard by officer and branch. Exit: a week of real arrears worked through it. Release v0.4.

**P3 · Payroll and statements (4 weeks).** Import employer deduction files and bank or mobile-money statements; match, preview, post in bulk, list exceptions. Exit: a real employer file posts correctly. Release v0.5.

**P4 · Accounting and reports (5 weeks).** Chart of accounts and accrual accounting in Fineract, journal entries for every loan event, month-end close, trial balance; portfolio, arrears, disbursement, collection, income and staff reports in Excel and PDF; Bank of PNG returns once the format is confirmed. Exit: Breez's accountant signs off one month of figures. Release v0.6.

**P5 · SMS, email, credit bureau (alongside P3 and P4).** Adapters for the chosen SMS provider, an email service and the credit bureau. Exit: real messages reach a test phone and inbox.

**P6 · Server, migration, training (4 weeks).** Office server with UPS, nightly backups copied off site, a tested restore, secure remote access for branches and the portal, monitoring; existing loans imported and checked; staff guide and training. Exit: a full restore works and migrated balances match the old records. Release candidate v0.9.

**P7 · Pilot (4 weeks).** McLender and the current process run side by side; differences are fixed weekly. Exit: one month-end whose figures match the current records, and no serious issue left open. Go-live and v1.0 on 17 May 2027.

## From a change to GitHub and the live system

Every change follows the same loop: Claude builds and tests it, Jerry tests it live on his PC, and only then does it go to GitHub, where the automated checks and CodeRabbit must pass before it is merged into `main`.

```
Claude builds + tests -> commit on a branch on Jerry's PC -> Jerry tests live --(fails)--> Claude fixes
                                                                  |
                                                                (passes)
                                                                  v
Phase done: tag release, deploy <- Jerry squash-merges <- CI + CodeRabbit OK? <- Jerry pushes, opens PR
                                                              |
                                                     (no) Claude fixes, commit again
```

**The steps, for each feature or fix:**

1. **Branch.** Claude starts a branch from the latest `main`: `feat/…` for a feature, `fix/…` for a correction, `docs/…` for documents only.
2. **Build and check.** Claude writes the code and its tests, runs every automated check (API tests, browser tests, lint, type checks), and has an independent review pass look for bugs and security gaps.
3. **Commit on Jerry's PC.** Claude copies the change to `Documents\Developer\lending-platform`, commits it on that branch, and sends what changed, how to rebuild, and a short test checklist. Nothing is pushed yet.
4. **Live test.** Jerry rebuilds (`docker compose up -d --build`) and works through the checklist as the real users would (officer, manager, borrower). Anything wrong goes back to step 2 on the same branch.
5. **Push and pull request.** When it passes, Jerry pushes the branch and opens a pull request into `main`. Claude gives the title and description to paste.
6. **Checks and review.** GitHub runs the automated checks; CodeRabbit reviews. Any failure or comment goes to Claude, who fixes it, commits on Jerry's PC, and gives a reply for each comment. Jerry pushes again.
7. **Merge.** When the checks are green and the comments are answered, Jerry clicks Squash and merge, then switches his PC to `main` and pulls.
8. **Release.** At the end of each phase, Jerry tags a release on GitHub (v0.3, v0.4 and so on) with notes Claude writes. A release is the only thing that goes on the office server.

**Three places the system runs:**

| Place | Where | What it's for | Data |
| --- | --- | --- | --- |
| Development | Claude's workspace | Building and automated tests | Built-in sample data |
| Test | Jerry's PC, Docker Desktop | Live testing each change before GitHub | Test borrowers from setup-test |
| Production | Breez office server (from P6) | Real use: pilot, then go-live | Real borrowers; backed up nightly |

**Deploying a release to the office server (from P6):** back up first (databases and documents), install the tagged release, run the setup and upgrade steps, then a five-minute check (sign in, open a loan, print a receipt). If anything fails, restore the backup and the previous release; no change is ever made directly on the server.

**Urgent fixes after go-live:** the same loop, made faster: a `fix/…` branch, tested live the same day, merged, and released as a patch (for example v1.0.1).

## Who does what

Claude builds, tests and documents; Jerry decides, tests live, pushes, merges and releases. Nothing goes to GitHub or the office server without Jerry's action.

| Step | Claude | Jerry |
| --- | --- | --- |
| Plan a feature | Proposes the design, screens and data; asks the questions that change it | Answers; agrees the scope |
| Build | Code, tests, independent review, docs and checklist | – |
| Commit | Commits on a branch on Jerry's PC | – |
| Live test | Fixes what Jerry reports, same branch | Rebuilds and works through the checklist |
| GitHub | Writes the PR text and replies to review comments; fixes CI failures | Pushes, opens the PR, merges |
| Release | Writes release notes and upgrade steps | Tags the release |
| Office server (from P6) | Writes the install, backup, restore and upgrade scripts | Runs them, or has Breez IT run them |
| Breez decisions | Lists what's needed and when | Gets answers from Breez (management, accountant, lawyer) |

Progress is reported at the end of each feature: what changed, how to test it, what is not yet verified. The project roadmap in Claude Projects is kept up to date after each merge.

## Decisions and inputs needed

Thirteen answers from Breez decide whether the dates hold; the first two are needed before Phase 1 starts on 26 October.

| Needed by | Decision or input | Why | From |
| --- | --- | --- | --- |
| 26 Oct 2026 | Branches, staff, roles and approval limits (who can approve up to how much) | Phase 1 builds the admin area around them | Breez management |
| 26 Oct 2026 | Logo and brand colours | Phase 1 branding settings | Breez |
| 1 Dec 2026 | SMS provider and sender name (Digicel or Vodafone bulk SMS) | Contracts take weeks; reminders and portal sign-in need real SMS | Breez |
| 1 Dec 2026 | Credit bureau access agreement | Needed before the bureau check can be connected | Breez |
| 4 Jan 2027 | Email service for the company domain | Agreements, statements and receipts by email | Breez IT |
| 4 Jan 2027 | A real employer deduction file; fortnightly loan product; short and over payment rules | Phase 3 matches and posts payroll deductions | Breez, employers |
| 15 Jan 2027 | Chart of accounts, cash or accrual, loan loss provisioning | Phase 4 accounting set-up | Breez accountant |
| 15 Jan 2027 | Bank of PNG reporting and licensing requirements | Which returns the reports must produce | Breez management |
| 1 Feb 2027 | Existing loans: where they are kept (Excel, another system) and a copy | Migration is planned and tested in Phase 6 | Breez |
| 1 Feb 2027 | How branches and borrowers reach the office server (secure tunnel, VPN or fixed internet address) | The portal and branches need it; affects internet plan | Jerry with Breez IT |
| 1 Mar 2027 | Office server, UPS and backup drive bought; who looks after it | Phase 6 installs on it | Breez |
| 1 Mar 2027 | Loan agreement wording reviewed by a PNG lawyer | The agreement stays marked DRAFT until then | Breez lawyer |
| 1 Mar 2027 | Borrower consent and privacy wording; how long records are kept | Needed before real borrower data goes in | Breez lawyer |

## Risks

The biggest risk to the date is outside answers arriving late, not the code; the biggest risk to the business is running real money on an office machine without tested backups.

| Risk | Effect | How we handle it |
| --- | --- | --- |
| Breez answers or contracts (SMS, bureau, accountant, lawyer) come late | Phases 3 to 5 slip; pilot moves | Ask early (dates above); build adapters that work with test data, connect the real service when ready |
| Office server fails, is stolen, or loses power | Lending stops; data could be lost | UPS, nightly encrypted backups copied off site, a restore tested before the pilot and every quarter |
| Office internet goes down | Branches and the portal can't reach the system | Choose a reliable plan with a backup link; branches keep working on paper and enter it later |
| Each live test takes longer than expected | The plan stretches (testing every feature was chosen) | Small features, a clear checklist each time, test sessions booked weekly |
| Old loan records are incomplete or wrong | Wrong balances after migration | Trial migrations in P6, every balance checked against the old records, differences signed off before the pilot |
| Bank of PNG or legal requirements change the scope | Extra reports or wording late | Confirm requirements by 15 January; keep reports configurable |
| A security gap exposes borrower data | Harm to borrowers; legal and reputational damage | Roles checked on the server, audit log, two-step sign-in for staff, HTTPS, an independent security review in P6 |
| Fineract upgrades change how things work | Features break after an upgrade | Pin the Fineract version; upgrade only on the test PC first, as its own change through the same loop |

## When something counts as done

A feature is done when Jerry has tested it live and it is merged into `main`; the system is ready for the pilot when every item in the second list is ticked.

**A feature or fix is done when:**

- [ ] Its automated tests pass, along with all the existing ones (API, browser, lint, type checks)
- [ ] An independent review found no unfixed bug or security gap
- [ ] Jerry has tested it live on his PC with its checklist
- [ ] The GitHub checks are green and every CodeRabbit comment is fixed or answered
- [ ] The user guide and test checklists are updated
- [ ] It is merged into `main`, and anything not verified is written down

**Ready for the pilot when:**

- [ ] Phases 0 to 6 are released (v0.9)
- [ ] Office server installed; a full restore from backup has worked
- [ ] Existing loans migrated and every balance matches the old records
- [ ] Accountant has signed off one month of accounting figures
- [ ] Real SMS reach borrowers; email sends; credit bureau check works (or a written decision to go without it at first)
- [ ] Loan agreement wording approved by a lawyer
- [ ] Security review done; staff use two-step sign-in
- [ ] Staff trained, with a printed quick guide for each role

## Changes to this plan

| Date | Change |
| --- | --- |
| 8 Oct 2026 | First version, agreed with Jerry |
