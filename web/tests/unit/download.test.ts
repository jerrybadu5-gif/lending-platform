import { describe, expect, it } from 'vitest'
import { fileNameFrom } from '../../src/components/DownloadLink'

describe('download file names', () => {
  it('prefers the UTF-8 name', () => {
    expect(fileNameFrom(`attachment; filename="payslip_Oct.pdf"; filename*=UTF-8''payslip%E2%80%93Oct.pdf`)).toBe('payslip–Oct.pdf')
  })
  it('falls back to the plain name', () => {
    expect(fileNameFrom('attachment; filename="LN-000482-statement.pdf"')).toBe('LN-000482-statement.pdf')
  })
  it('handles a missing header', () => {
    expect(fileNameFrom(null)).toBeNull()
  })
})
