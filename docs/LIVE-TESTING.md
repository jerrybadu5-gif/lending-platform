# Live testing: McLender with a real Fineract (Docker Desktop, Windows)

This runs the whole system on one PC: PostgreSQL, Apache Fineract, the Mifos X admin app and McLender.
It uses **test data only**. Allow 30–45 minutes the first time; most of it is downloading and Fineract's
first start.

You need Docker Desktop running (whale icon in the taskbar steady, not animating) and about 8 GB of
memory free. All commands are for PowerShell in VS Code (**Terminal > New Terminal**), starting in the
`lending-platform` folder.

## 1. Settings file

```powershell
Copy-Item deploy\.env.example deploy\.env
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Open `deploy\.env` in VS Code and change these lines (any long passwords you like; it's a test):

| Line | Set to |
|---|---|
| `POSTGRES_PASSWORD` | a password |
| `FINERACT_DB_PASS` | a different password |
| `MCL_SESSION_SECRET` | the long random text the `python` line printed |
| `MCL_FINERACT_PORTAL_PASSWORD` | another password (8+ characters) |
| `MCL_SMS_LOG_CONTENT` | `true` (test PC only: puts sign-in codes in the log, as there's no SMS provider yet) |

Save the file. It's ignored by git, so the passwords never go to GitHub.

## 2. Start the database and Fineract

```powershell
cd deploy
docker compose up -d postgresql fineract-server
```

The first time this downloads about 1 GB. Then Fineract sets up its database, which takes 3–10 minutes.
Check whether it's ready (repeat every minute or so):

```powershell
curl.exe -s http://localhost:8080/fineract-provider/actuator/health
```

It's ready when this shows `{"status":"UP"...}`. To watch it start: `docker compose logs -f fineract-server`
(Ctrl+C stops watching, not Fineract).

## 3. Load the test setup

```powershell
cd ..
api\.venv\Scripts\python.exe deploy\setup-test.py
```

This creates the data tables, PGK, payment types, a Personal loan product, the roles, the users `grace`
(credit manager), `john` (loan officer) and `portal`, and three test borrowers. **Write down the logins
it prints at the end; they're shown once.** If it stops with "Fineract refused a step", copy the message to
Claude. It's safe to run again after a fix.

If it says to set `MCL_PORTAL_PRODUCT_ID`, change that line in `deploy\.env`.

## 4. Start McLender and the Mifos X admin app

```powershell
cd deploy
docker compose up -d --build
docker compose ps
```

The first build takes a few minutes. All five services should show `running` (or `healthy`).

| Open | Sign in |
|---|---|
| McLender staff app: http://localhost:8088/staff | `grace` or `john`, with the passwords from step 3 |
| McLender portal: http://localhost:8088/portal | phone `7012 3344` (Mary Kila) |
| Mifos X admin: http://localhost:8081 | `mifos` / `password` (Fineract's built-in admin) |

Portal sign-in code (the newest line is the one to use):

```powershell
docker compose logs mclender-api | Select-String "sign-in code"
```

## 5. What to check

Tick each one. If something is wrong, note the screen, what you did and what you expected.

**Staff app as `grace`**
- [ ] Sign-in shows Grace's name and the Credit manager role.
- [ ] Dashboard: 1 active loan (Mary), 2 waiting for approval (Peter, Joyce). Mary is about 10 days overdue,
      so she shows under arrears.
- [ ] Open Peter Wambi's application: "Run the affordability check again" gives a recommendation and the figures.
- [ ] Applications as Grace shows Peter under "With loan officers": John has to review it first.

**As `john` (Loan officer), in a second browser or a private window**
- [ ] Open Peter's application. "Send to credit manager" is greyed out, with "Documents still needed". Follow the
      link to his profile and upload the four documents (any PDF or phone photo will do for a test). The badge
      turns to "Documents complete".
- [ ] Upload a phone photo of an ID card as his ID (yours is fine for a test), open it and "Read ID card". Check the
      photo crop and the details read; "Use as profile photo" shows it on the profile, and in Mifos X on the client.
- [ ] Back on the application, recommend approval for a smaller amount, write what you checked, and send it.
      It shows "With the credit manager"; there's no Approve button for John.

**Back as `grace`**
- [ ] Peter is under "Waiting for your decision", with John's recommendation and the documents shown in the page.
- [ ] Try "Send back" with a note: John sees it under "To review" with your note. Send it up again as John.
- [ ] Approve Peter. The pay-out steps appear:
  - [ ] Step 1: "Loan agreement (PDF)" opens with the amount, his details and the DRAFT note.
  - [ ] Step 2: shows "SMS not delivered (no SMS provider set up yet)" and is not ticked, because texts only
        go to the log until Digicel/Vodafone is connected (`docker compose logs mclender-api | Select-String "approved"`).
        "Log a phone call" with a note ticks step 2 and adds the call to History.
  - [ ] Step 4 says to upload the signed agreement first; there is no pay-out button yet.
  - [ ] Step 3: upload any PDF as the signed agreement. It shows as a link; Signed is ticked on the progress bar.
  - [ ] Step 4: the account number is filled in from his profile. Enter a reference and record the disbursement.
        He becomes Active with a schedule, and the log shows the "paid out" SMS.
  - [ ] In Mifos X: the loan's Notes show the SMS, phone call and signed-agreement entries; Documents has the
        signed copy; the disbursement transaction shows Bank Transfer and your reference.
- [ ] As John, send Joyce up recommending decline; as Grace, reject her with a note. She leaves the list.
- [ ] Repayments: record K 472.80 for Mary by Mobile Money with a reference. The receipt stays on screen and
      "Print receipt (PDF)" opens it; it's also listed under "Receipts recorded". In Mifos X, Mary's loan >
      Documents has the receipt PDF.

**Borrowers as `grace`**
- [ ] Borrowers > New borrower: saving an empty form marks what's missing; a date of birth under 18 is refused.
- [ ] Sign up a new borrower with an NID number and a bank account. The profile shows "4 documents needed".
- [ ] Signing up another borrower with the same phone or NID number is refused, naming who has it.
- [ ] Upload a document, then open it from "Documents on file": it shows in the page, and Download gives the same
      file. Upload a wrong one and remove it with a reason: the reason shows under "File notes" and in Mifos X
      (client Notes).
- [ ] Take a loan application on the profile. It opens with the affordability check done.
- [ ] Search finds the borrower by name in any case and order (`MOREA kila`), phone and NID number.

**Compare in Mifos X** (http://localhost:8081)
- [ ] Clients > Peter Wambi: the loan is Active with the approved amount and the same schedule.
- [ ] Clients > Joyce Ilave: the loan is Rejected, with your note.
- [ ] Clients > Mary Kila > loan > Transactions: your repayment, Mobile Money, your reference.
- [ ] Clients > your new borrower: identifier "National ID (NID)", the uploaded documents under Documents,
      and the profile under the dt_borrower_profile tab.
- [ ] Uploaded documents survive a restart: `docker compose up -d --force-recreate fineract-server`, wait for UP,
      then download one again in McLender.
- [ ] The McLender dashboard figures match what Mifos X shows (active loans, outstanding, overdue).


**Portal**
- [ ] Phone `7012 3344`, code from the log: Mary's loan shows what's left, the next payment and her payments.
- [ ] "Download statement (PDF)" and "Repayment schedule (PDF)" open her own documents.
- [ ] Apply for K 3,000 over 12 months. It appears for `john` under "To review" (and for `grace` under "With loan officers"), and in Mifos X under Mary.
- [ ] Phone `7999 9999` (unknown) gets the same "we have sent a code" message, and no code in the log.

## Stopping, restarting, starting over

```powershell
docker compose stop          # stop everything; data kept
docker compose start         # start again (Fineract takes a minute)
docker compose down -v       # DELETE all test data and start from step 2
```

## If something goes wrong

| Problem | Try |
|---|---|
| `port is already allocated` | Another program uses that port. Change `FINERACT_PORT`, `WEB_APP_PORT` or `MCLENDER_PORT` in `.env` |
| Health check never says UP | `docker compose logs fineract-server --tail 50`; often memory: give Docker more in Docker Desktop > Settings > Resources |
| McLender says it can't reach Fineract | `docker compose logs mclender-api --tail 50` |
| Sign-in to the portal says nothing was found | Re-run step 3, then check Mary's mobile number in Mifos X is 70123344 |

Copy any error to Claude as text, with the command you ran.
