import { expect, test, type Page } from '@playwright/test'

const PDF = { name: 'scan.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% e2e\n%%EOF\n') }

async function signInAs(page: Page, user: string) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByLabel('Username').fill(user)
  await page.getByLabel('Password').fill(user)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Portfolio today' })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await page.goto('/staff/login')
  await page.getByLabel('Username').fill('demo')
  await page.getByLabel('Password').fill('demo')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Portfolio today' })).toBeVisible()
})

test('sign up a borrower, upload KYC documents, take an application and approve it', async ({ page }) => {
  await page.getByRole('navigation').getByRole('link', { name: 'Borrowers' }).click()
  await page.getByRole('link', { name: 'New borrower' }).click()

  // Saving an empty form shows what to fix.
  await page.getByRole('button', { name: 'Save borrower' }).click()
  await expect(page.getByText('Enter the first name.')).toBeVisible()

  await page.getByLabel('First name').fill('Kila')
  await page.getByLabel('Last name').fill('Morea')
  await page.getByLabel('Date of birth').fill('1990-04-12')
  await page.getByRole('button', { name: 'Female' }).click()
  await page.getByLabel('NID number').fill('2018 4410 9921')
  await page.getByLabel('Mobile number').fill('7555 1212')
  await page.getByLabel('Home address').fill('Section 5, Lot 9, Tokarara, NCD')
  await page.getByLabel('Employer').fill('Department of Education')
  await page.getByLabel('Take-home pay each month (PGK)').fill('3,800.00')
  await page.getByLabel('Bank', { exact: true }).selectOption('BSP')
  await page.getByLabel('Name on the account').fill('Kila Morea')
  await page.getByLabel('Account number').fill('1001 2233 4455')
  await page.getByRole('button', { name: 'Save borrower' }).click()

  await expect(page.getByRole('heading', { name: 'Kila Morea' })).toBeVisible()
  await expect(page.getByText('4 documents needed')).toBeVisible()
  await page.getByTestId('upload-id').setInputFiles(PDF)
  await expect(page.getByText('3 documents needed')).toBeVisible()
  await expect(page.getByRole('button', { name: 'scan.pdf' })).toBeVisible()

  await page.getByLabel('Amount (PGK)').fill('3000')
  await page.getByRole('button', { name: 'Save application' }).click()
  await expect(page.getByRole('heading', { name: 'Kila Morea' })).toBeVisible()
  // The credit manager decides, but approval waits for the loan officer's review. No "send to credit manager" for her.
  await expect(page.getByRole('heading', { name: 'Decision' })).toBeVisible()
  await expect(page.getByText(/The loan officer hasn't sent his review yet/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send to credit manager' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^Approve/ })).toBeDisabled()

  // The loan officer can't send it up until every document is on file.
  const loanUrl = page.url()
  await signInAs(page, 'officer')
  await page.goto(loanUrl)
  await expect(page.getByText('Documents still needed', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send to credit manager' })).toBeDisabled()
  await page.getByRole('button', { name: 'Decline' }).click()
  await expect(page.getByRole('button', { name: 'Send to credit manager' })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()

  await page.getByRole('link', { name: "Upload them on the borrower's profile" }).click()
  for (const kind of ['payslip', 'bank_statement', 'deduction_authority']) {
    await page.getByTestId(`upload-${kind}`).setInputFiles(PDF)
  }
  await expect(page.getByText('Documents complete')).toBeVisible()
  await page.goto(loanUrl)
  await page.getByLabel('Your assessment').fill('All four documents checked against the originals.')
  await page.getByRole('button', { name: 'Send to credit manager' }).click()
  await expect(page.getByRole('heading', { name: 'With the credit manager' })).toBeVisible()
  await signInAs(page, 'demo')
  await page.goto(loanUrl)
  await expect(page.getByRole('button', { name: /^Approve/ })).toBeEnabled()
  await page.getByRole('button', { name: /^Approve/ }).click()
  await expect(page.getByRole('status')).toContainText('approved')

  const agreement = page.getByRole('link', { name: 'Loan agreement (PDF)' })
  await expect(agreement).toBeVisible()
  const href = (await agreement.getAttribute('href'))!
  const response = page.waitForResponse((res) => res.url().endsWith(href))
  await agreement.click()
  expect((await response).headers()['content-type']).toBe('application/pdf')
})

test('find a borrower by NID number', async ({ page }) => {
  await page.goto('/staff/borrowers')
  await page.getByLabel('Find a borrower').fill('2011 0488')
  await expect(page.getByRole('cell', { name: 'Peter Wambi' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Mary Kila' })).toHaveCount(0)
})


test('open a document, then remove a wrong upload with a reason', async ({ page }) => {
  await page.goto('/staff/borrowers/10')  // Joyce Ilave: no loan approved yet
  await page.getByTestId('upload-other').setInputFiles({ ...PDF, name: 'wrong-person.pdf' })
  await page.getByRole('button', { name: 'wrong-person.pdf' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('link', { name: 'Download' })).toBeVisible()
  await expect(dialog.locator('iframe')).toBeVisible()
  await dialog.getByRole('button', { name: 'Remove…' }).click()
  await dialog.getByRole('button', { name: 'Remove document' }).click()
  await expect(dialog.getByText('Say why it is being removed, for the record.')).toBeVisible()
  await dialog.getByLabel('Why remove it?').fill('Another borrower’s payslip')
  await dialog.getByRole('button', { name: 'Remove document' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'wrong-person.pdf' })).toHaveCount(0)
  await expect(page.getByText(/Removed Other document: wrong-person.pdf. Reason: Another borrower’s payslip/)).toBeVisible()
})

test('search ignores case and word order', async ({ page }) => {
  await page.goto('/staff/borrowers')
  await page.getByLabel('Find a borrower').fill('WAMBI peter')
  await expect(page.getByRole('cell', { name: 'Peter Wambi' })).toBeVisible()
})
