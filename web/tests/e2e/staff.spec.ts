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
  await expect(page.getByLabel('Approved amount (PGK)')).toHaveValue('13,100.00')
  await page.getByLabel('Note for the file').fill('Reduced to fit DTI')
  await page.getByRole('button', { name: /^Approve K 13,100.00$/ }).click()
  await expect(page.getByRole('status')).toContainText('approved for K 13,100.00')
  await page.getByRole('button', { name: 'Record disbursement' }).click()
  await expect(page.getByRole('link', { name: 'Record repayment' })).toBeVisible()
})

test('reject needs a reason', async ({ page }) => {
  await page.getByRole('navigation').getByRole('link', { name: /Applications/ }).click()
  await page.getByRole('cell', { name: /Joyce Ilave/ }).click()
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
})
