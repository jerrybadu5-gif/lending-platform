// Formatting rules from the McLender design system: K 1,318.74 and dd/MM/yyyy.

/** Kina with thousands separators and two decimals, from a decimal string or number. String math only. */
export function formatKina(amount: string | number | null | undefined, opts: { currency?: boolean } = {}): string {
  if (amount === null || amount === undefined || amount === '') return '—'
  const s = typeof amount === 'number' ? amount.toFixed(2) : amount.trim()
  if (!/^-?\d+(\.\d+)?$/.test(s)) return '—'
  const neg = s.startsWith('-')
  const [whole, frac = ''] = (neg ? s.slice(1) : s).split('.')
  const cents = (frac + '00').slice(0, 2)
  // Round half up on the third decimal using integer string math.
  let units = BigInt(whole + cents)
  if (frac.length > 2 && Number(frac[2]) >= 5) units += 1n
  const str = units.toString().padStart(3, '0')
  const w = str.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const out = `${w}.${str.slice(-2)}`
  return `${neg && units !== 0n ? '-' : ''}${opts.currency === false ? '' : 'K '}${out}`
}

/** ISO yyyy-mm-dd -> dd/MM/yyyy */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

export function formatPercent(ratio: string | number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || ratio === '') return '—'
  return `${(Number(ratio) * 100).toFixed(digits)}%`
}

/** Accepts "1,318.74", "K 1318.74", " 1318.7 " -> "1318.74"; null if not a money amount. */
export function parseKina(input: string): string | null {
  const s = input.replace(/[K,\s]/gi, '')
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null
  const [w, f = ''] = s.split('.')
  return `${String(BigInt(w))}.${(f + '00').slice(0, 2)}`
}

export function weekdayDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return `${d.toLocaleDateString('en-AU', { weekday: 'long' })} ${formatDate(iso)}`
}
