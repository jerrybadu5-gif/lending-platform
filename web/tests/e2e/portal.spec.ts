import { expect, test } from '@playwright/test'
import { readCode } from './sms'


test('borrower signs in with an SMS code and sees the loan', async ({ page }) => {
  await page.goto('/portal')
  await expect(page).toHaveURL(/\/portal\/login/)
  await page.getByLabel('Your mobile number').fill('7255 0198')
  await page.getByRole('button', { name: 'Send code' }).click()
  await expect(page.getByRole('status')).toContainText('6-digit code')
  await page.getByLabel('6-digit code').fill(await readCode('72550198'))
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('Hello, Samuel')).toBeVisible()
  await expect(page.getByText('Left to pay, including interest')).toBeVisible()
  await expect(page.getByText('2 of 24 payments made', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'How to pay' }).click()
  await expect(page.getByText('BL455', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Apply' }).click()
  await page.getByRole('button', { name: 'K 2,000' }).click()
  await page.getByRole('button', { name: '6 mo' }).click()
  await expect(page.getByText('K 357.05')).toBeVisible()
  await page.getByLabel('Take-home pay each month (PGK)').fill('5,000')
  await page.getByRole('button', { name: 'Send application' }).click()
  await expect(page.getByText('We have your application')).toBeVisible()
})
