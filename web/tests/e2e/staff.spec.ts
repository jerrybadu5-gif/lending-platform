import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/staff')
  await expect(page).toHaveURL(/\/staff\/login/)
  await page.getByLabel('Username').fill('demo')
  await page.getByLabel('Password').fill('demo')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Portfolio today' })).toBeVisible()
})

test('dashboard shows figures and waiting applications', async ({ page }) => {
  await expect(page.getByText('Due today', { exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: /Peter Wambi/ })).toBeVisible()
})

test('review, approve and disburse a referred loan', async ({ page }) => {
  await page.getByRole('cell', { name: /Peter Wambi/ }).click()
  await expect(page.getByRole('heading', { name: 'Peter Wambi' })).toBeVisible()
  await expect(page.getByRole('img', { name: /Debt-to-income 44.5%/ })).toBeVisible()
  // The loan officer's review comes first, with the borrower's documents shown in the page.
  await expect(page.getByText('Loan officer recommends approving K 13,000.00')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Documents to review' }).getByRole('tab')).toHaveCount(4)
  await expect(page.getByLabel('Approved amount (PGK)')).toHaveValue('13,000.00')
  await page.getByLabel('Note for the file').fill('Agree with the officer: reduced to fit DTI')
  await page.getByRole('button', { name: /^Approve K 13,000.00$/ }).click()
  await expect(page.getByRole('status')).toContainText('approved for K 13,000.00')
  // Pay-out steps: the SMS went automatically; pay-out waits for the signed agreement.
  await expect(page.getByText(/SMS sent to borrower/).first()).toBeVisible()
  await expect(page.getByText("Upload the borrower's signed loan agreement.")).toBeVisible()
  await page.getByRole('button', { name: 'Log a phone call' }).click()
  await page.getByLabel('What was agreed?').fill('Coming Friday to sign')
  await page.getByRole('button', { name: 'Save call' }).click()
  await expect(page.getByText(/Phoned borrower: Coming Friday to sign/).first()).toBeVisible()
  await page.getByTestId('upload-signed-agreement').setInputFiles({ name: 'signed.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 signed') })
  await expect(page.getByRole('button', { name: 'signed.pdf' })).toBeVisible()
  await expect(page.getByLabel('Paid into account number')).toHaveValue('2003 1188 0091')
  await page.getByRole('button', { name: 'Mobile money' }).click()
  await expect(page.getByLabel('Mobile money number')).toHaveValue('71234567')
  await page.getByRole('button', { name: 'Bank transfer' }).click()
  await expect(page.getByLabel('Paid into account number')).toHaveValue('2003 1188 0091')
  await page.getByLabel('Bank transfer reference').fill('TT-0012345')
  await page.getByRole('button', { name: 'Record disbursement' }).click()
  await expect(page.getByRole('link', { name: 'Record repayment' })).toBeVisible()
})

test('reject needs a reason', async ({ page }) => {
  await page.getByRole('navigation').getByRole('link', { name: /Applications/ }).click()
  await expect(page.getByRole('tab', { name: /Waiting for your decision/ })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('cell', { name: 'LN-000541' }).click()
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Reject application' })).toBeDisabled()
  await page.getByRole('button', { name: 'Keep reviewing' }).click()
  await page.getByLabel('Note for the file').fill('Income too low for any term')
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await page.getByRole('button', { name: 'Reject application' }).click()
  await expect(page.getByRole('status')).toContainText('rejected')
})

test('record a mobile money repayment', async ({ page }) => {
  await page.getByRole('navigation').getByRole('link', { name: 'Repayments' }).click()
  await page.getByRole('button', { name: 'Mary Kila' }).click()
  await expect(page.getByLabel('Amount received (PGK)')).toHaveValue('1,318.74')
  await page.getByRole('button', { name: /Record repayment/ }).click()
  await expect(page.getByText('Enter the reference so the payment can be traced.')).toBeVisible()
  await page.getByLabel('Mobile money transaction ID').fill('CM8841203377')
  await page.getByRole('button', { name: /Record repayment/ }).click()
  await expect(page.getByText('Repayment recorded')).toBeVisible()
  await expect(page.getByText(/Sent to 70123344/)).toBeVisible()
  // The receipt stays on screen after Mary drops off the "due today" list, and is listed below.
  await expect(page.getByRole('region', { name: 'Loans' }).getByRole('button', { name: 'Mary Kila' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Print receipt (PDF)' })).toBeVisible()
  const listed = page.getByRole('region', { name: 'Receipts recorded' })
  await expect(listed.getByText('Mary Kila')).toBeVisible()
  const href = (await listed.getByRole('link', { name: 'Print receipt' }).getAttribute('href'))!
  const response = page.waitForResponse((res) => res.url().endsWith(href))
  await listed.getByRole('link', { name: 'Print receipt' }).click()
  expect((await response).headers()['content-type']).toBe('application/pdf')
})


test('loan officer reviews and sends up; cannot approve', async ({ page }) => {
  await page.getByRole('button', { name: /Sign out/ }).click()
  await page.getByLabel('Username').fill('officer')
  await page.getByLabel('Password').fill('officer')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('navigation').getByRole('link', { name: /Applications/ }).click()
  await expect(page.getByRole('tab', { name: /To review/ })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('cell', { name: 'LN-000538' }).click()
  await expect(page.getByRole('button', { name: /^Approve/ })).toHaveCount(0)
  await page.getByRole('button', { name: 'Send to credit manager' }).click()
  await expect(page.getByText('Write what you checked and why (at least a sentence).')).toBeVisible()
  await page.getByLabel('Your assessment').fill('ID and payslips checked; employer confirmed by phone.')
  await page.getByRole('button', { name: 'Send to credit manager' }).click()
  await expect(page.getByRole('heading', { name: 'With the credit manager' })).toBeVisible()
  await expect(page.getByText(/Loan officer recommends approving/)).toBeVisible()
})


test('credit manager and loan officer signed in side by side in one browser', async ({ page, context }) => {
  // This tab is Grace (credit manager). A second tab signs in as John and stays John.
  const john = await context.newPage()
  await john.goto('/staff/login')
  await john.getByLabel('Username').fill('officer')
  await john.getByLabel('Password').fill('officer')
  await john.getByRole('button', { name: 'Sign in' }).click()
  await expect(john.getByText('John Kerema').first()).toBeVisible()

  await page.reload()
  await expect(page.getByText('Grace Pokana').first()).toBeVisible()
  await john.reload()
  await expect(john.getByText('John Kerema').first()).toBeVisible()

  // Grace asks John for more on an application he hasn't sent up yet; it lands in his list with her note.
  await page.goto('/staff/loans/542')
  await page.getByRole('button', { name: 'Note to loan officer' }).click()
  await page.getByLabel('What needs doing').fill('Please get her bank statement first')
  await page.getByRole('button', { name: 'Send to loan officer' }).click()
  await expect(page.getByRole('status')).toContainText('Sent to the loan officer')
  await john.goto('/staff/loans/542')
  await expect(john.getByRole('note').getByText('Please get her bank statement first')).toBeVisible()
})
