import { describe, expect, it } from 'vitest'
import { validate } from '../../src/staff/BorrowerForm'

const ok = {
  first_name: 'Kila', last_name: 'Morea', phone: '7555 1212', date_of_birth: '1990-04-12', gender: 'female' as const,
  address: 'Lot 9, Tokarara', national_id: '2018 4410 9921', employer: '', payroll_number: '', monthly_income: '3,800.00',
  existing_monthly_debt: '0.00', bank: '', branch: '', account_name: '', account_number: '', nok_name: '', nok_relationship: '',
  nok_phone: '',
}

describe('borrower form checks', () => {
  it('accepts a complete form', () => {
    expect(validate(ok)).toEqual({})
  })
  it('needs an adult with a PNG mobile number', () => {
    const year = new Date().getFullYear() - 17
    const e = validate({ ...ok, phone: '123', date_of_birth: `${year}-01-01` })
    expect(e.phone).toMatch(/8-digit/)
    expect(e.date_of_birth).toMatch(/18/)
    expect(validate({ ...ok, phone: '+675 7555 1212' }).phone).toBeUndefined()
  })
  it('asks for the whole bank account once any part is entered', () => {
    const e = validate({ ...ok, bank: 'BSP' })
    expect(e.account_number).toBeDefined()
    expect(e.account_name).toBeDefined()
    expect(validate({ ...ok, bank: 'BSP', account_name: 'Kila Morea', account_number: '1001 2233' })).toEqual({})
  })
  it('asks for the whole next of kin once any part is entered', () => {
    expect(validate({ ...ok, nok_name: 'Ben' }).nok_phone).toBeDefined()
  })
})
