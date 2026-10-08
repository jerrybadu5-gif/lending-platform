# Testing McLender (sample data)

Start it with `start-demo.ps1` (see the README). Tick each line as you go. Note anything that looks wrong, reads badly or feels slow: the screen, what you did, what you expected.

Sample data is dated from today, so "due today" always has loans in it. Close and restart the API window to reset everything.

## Staff app: http://localhost:5173/staff

**Sign in**
- [ ] A wrong password says "Username or password is wrong."
- [ ] `demo` / `demo` signs in as Grace Pokana, Credit manager.

**Dashboard**
- [ ] Four figures show: gross portfolio, active loans, PAR over 30 days, due today (gold).
- [ ] "Waiting for approval" lists 5 applications, each with Approve, Refer or Decline.
- [ ] "Arrears by age" shows the 1–30 and 31–60 day amounts.

**Review a loan: Peter Wambi (K 15,000, Refer)**
- [ ] Applications opens on "Waiting for your decision": Grace Tom, Peter Wambi and Samuel's business loan, each "Sent for approval".
- [ ] The affordability card shows DTI 44.5% against a 40% limit, and "most we can lend" K 13,113.42.
- [ ] The Decision card starts with "Loan officer recommends approving K 13,000.00" and John's note. The approved amount starts at 13,000.00.
- [ ] The Documents card shows his ID, payslips, bank statement and deduction authority in the page, one tab each.
- [ ] Approve: a message confirms, the status becomes Approved, and "Record disbursement" appears.
- [ ] Record disbursement: the loan becomes Active and shows its next payment.

**Send back and reject**
- [ ] On another submitted application, "Send back" needs a note; the application moves to "With loan officers", showing your note to the officer.
- [ ] "Reject" asks for confirmation, and you can't confirm until a note is written.
- [ ] After rejecting, the status is Rejected and the loan leaves the pending list.

**Repayments**
- [ ] "Due today" lists Mary Kila, Ruth Kaupa and Samuel Kiap.
- [ ] Choosing Mary fills in K 1,318.74. Saving without a reference shows an error.
- [ ] With a reference such as `CM8841203377`, saving shows the receipt and "Sent to 70123344", and Mary drops off the due-today list. The receipt stays on screen and "Print receipt (PDF)" works.
- [ ] "Receipts recorded" lists the receipt under the form. On Mary's loan, "Kept on file" shows the receipt PDF.
- [ ] "In arrears" lists Thomas Aisi (47 days, red), Lucy Gumuno (26) and Andrew Moka (12).
- [ ] Entering more than is owed gives a clear error.

**Borrowers and documents**
- [ ] Borrowers lists 10 people; searching `2011 0488` finds Peter Wambi by his NID number.
- [ ] Searching `WAMBI peter`, `kila mary` or `Joyse` (a typo) finds the right person.
- [ ] On a profile, click a document's file name: it opens in the page with Download and Remove. Removing needs a reason, and the reason shows under "File notes". A document of a borrower with an approved loan can't be removed.
- [ ] Upload a phone photo of an ID card as the ID, open it, and "Read ID card": the face is cropped and the card's details are shown next to what's on file. "Use as profile photo" puts it on the profile; "Update details from the card" opens the edit form filled in, saying what changed.
- [ ] New borrower: an empty save marks what's missing; someone under 18 is refused; a phone already in use is refused.
- [ ] On the new profile, "4 documents needed". Upload any PDF or photo as the ID: it shows under Documents on file and downloads again.
- [ ] Joyce Ilave's application can't be approved: it lists the bank statement and payroll deduction authority as missing.
- [ ] After approving a loan, the pay-out steps appear: the agreement (3 pages, marked DRAFT), "SMS sent to borrower", then upload a signed copy (any PDF), then record the pay-out with a reference. Pay-out isn't possible before the signed copy is uploaded.

**Credit manager is the final say**
- [ ] As `demo`, open an application John hasn't sent up (Ruth Kaupa or Joyce Ilave). The card is "Decision", with no "Send to credit manager". Approve is greyed out until John sends his review; Reject and "Note to loan officer" work.

**Two people in one browser**
- [ ] Click "Sign in as someone else (new tab)", sign in there as `officer`. Each tab keeps its own person after reloading.

**Permissions: sign out and sign in as `officer` / `officer` (John Kerema, Loan officer)**
- [ ] Applications opens on "To review" (Ruth Kaupa and Joyce Ilave). There's no Approve or Reject button anywhere.
- [ ] On Ruth's application, "Send to credit manager" needs a written assessment. After sending, it shows "With the credit manager".
- [ ] Joyce's application can't be sent up, for approval or decline, until her documents are uploaded.
- [ ] On an approved loan, step 4 says a credit manager pays out.

## Borrower portal: http://localhost:5173/portal

Best on a phone-sized window: in Chrome or Edge press F12, then Ctrl+Shift+M.

- [ ] Phone `7012 3344`, then Send code. The 6-digit code appears in the API window (and at http://localhost:8000/api/dev/sms/70123344).
- [ ] A wrong code is refused, and after 5 wrong codes you must ask for a new one.
- [ ] Home shows "Hello, Mary", K 7,912.43 left to pay, 6 of 12 payments made.
- [ ] "How to pay" shows reference BL482 and the three ways to pay.
- [ ] Apply: changing the amount or term updates the monthly payment (K 5,000 over 12 months is K 472.80).
- [ ] A low take-home pay shows the "more than 40% of your pay" warning.
- [ ] Sending the application shows "We have your application", and the new loan appears for staff under Applications.
- [ ] An unknown number such as `7999 9999` gets the same "we have sent a code" message but no code. This is deliberate.

## Things to judge by eye

- [ ] Wording reads naturally for Breez Lending staff and borrowers.
- [ ] Amounts all show as `K 1,234.56`, dates as dd/mm/yyyy.
- [ ] Dark mode (switch Windows to dark) is readable.
- [ ] Nothing breaks at phone width or when the window is narrow.

## Automated checks (optional, for developers)

```powershell
cd api;  .\.venv\Scripts\python.exe -m pytest
cd web;  npm test;  npm run build;  npx playwright install chromium;  npm run e2e
```
