import { describe, expect, it } from 'vitest'
import { formatDate, formatKina, formatPercent, parseKina } from '../../src/lib/format'

describe('formatKina', () => {
  it('writes kina with separators and two decimals', () => {
    expect(formatKina('1318.74')).toBe('K 1,318.74')
    expect(formatKina('1284500')).toBe('K 1,284,500.00')
    expect(formatKina('0.5')).toBe('K 0.50')
    expect(formatKina(-250)).toBe('-K 250.00') // minus sign, never brackets
    expect(formatKina('13113.42', { currency: false })).toBe('13,113.42')
  })
  it('rounds half up without floating point', () => {
    expect(formatKina('1.005')).toBe('K 1.01')
    expect(formatKina('999.995')).toBe('K 1,000.00')
  })
  it('shows a dash for missing or bad values', () => {
    expect(formatKina(null)).toBe('—')
    expect(formatKina('abc')).toBe('—')
  })
})

describe('parseKina', () => {
  it('accepts what people type', () => {
    expect(parseKina('1,318.74')).toBe('1318.74')
    expect(parseKina('K 13000')).toBe('13000.00')
    expect(parseKina(' 5.5 ')).toBe('5.50')
  })
  it('rejects nonsense and more than two decimals', () => {
    expect(parseKina('12.345')).toBeNull()
    expect(parseKina('-5')).toBeNull()
    expect(parseKina('')).toBeNull()
  })
})

it('dates and percents', () => {
  expect(formatDate('2026-10-06')).toBe('06/10/2026')
  expect(formatPercent('0.4446')).toBe('44.5%')
})
