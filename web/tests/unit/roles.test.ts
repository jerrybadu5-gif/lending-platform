import { describe, expect, it } from 'vitest'
import type { LoanSummary } from '../../src/api/client'
import { isApproverRole } from '../../src/lib/me'
import { stageLabel } from '../../src/staff/Applications'
import { withCard } from '../../src/staff/BorrowerForm'

describe('roles', () => {
  it('knows who decides loans', () => {
    expect(isApproverRole(['Credit Manager'])).toBe(true)
    expect(isApproverRole(['Loan officer'])).toBe(false)
    expect(isApproverRole(['Loan officer', 'Super user'])).toBe(true)
    expect(isApproverRole([])).toBe(false)
  })

  it('labels where a pending application is', () => {
    const base = { state: 'PENDING' } as LoanSummary
    expect(stageLabel({ ...base, review_stage: 'SUBMITTED' })?.text).toBe('Sent for approval')
    expect(stageLabel({ ...base, review_stage: 'RETURNED' })?.tone).toBe('warning')
    expect(stageLabel({ ...base, state: 'APPROVED', review_stage: 'SUBMITTED' })).toBeNull()
  })
})

describe('details from the ID card', () => {
  const form = {
    first_name: 'Peter', last_name: 'Wambi', phone: '71234567', date_of_birth: '1986-03-14', gender: 'male' as const,
    address: 'Lae', national_id: '', employer: '', payroll_number: '', monthly_income: '', existing_monthly_debt: '0.00',
    bank: '', branch: '', account_name: '', account_number: '', nok_name: '', nok_relationship: '', nok_phone: '',
  }

  it('fills only what the card had and says what changed', () => {
    const { form: next, changed } = withCard(form, {
      first_name: 'Peter John', last_name: 'Wambi', national_id: '2011 0488 7712', date_of_birth: null, gender: null,
    })
    expect(next.first_name).toBe('Peter John')
    expect(next.national_id).toBe('2011 0488 7712')
    expect(next.date_of_birth).toBe('1986-03-14')
    expect(changed).toEqual(['first_name', 'national_id'])
  })

  it('leaves the form alone without a card', () => {
    expect(withCard(form, undefined)).toEqual({ form, changed: [] })
  })
})
