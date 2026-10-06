import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Button, Field, Skeleton, StatusPill } from '../components'
import { formatKina, parseKina } from '../lib/format'
import { PortalShell } from './PortalShell'

const AMOUNTS = [1000, 2000, 5000, 8000, 10000, 15000]
const TERMS = [3, 6, 12, 24]

export default function PortalApply() {
  const [amount, setAmount] = useState(5000)
  const [months, setMonths] = useState(12)
  const [income, setIncome] = useState('')
  const [debt, setDebt] = useState('0.00')
  const [touched, setTouched] = useState(false)
  const quote = useQuery({ queryKey: ['portal', 'quote', amount, months], queryFn: () => api.portal.quote(String(amount), months) })
  const send = useMutation({
    mutationFn: () => api.portal.apply({ amount: String(amount), months, monthly_income: parseKina(income) ?? '', existing_monthly_debt: parseKina(debt) ?? '' }),
  })
  const incomeError = parseKina(income) === null || Number(parseKina(income)) <= 0 ? 'Enter your take-home pay, like 3,200.00' : undefined
  const debtError = parseKina(debt) === null ? 'Enter 0 if you have no other loans.' : undefined
  const stretch = quote.data && !incomeError && Number(quote.data.monthly_payment) + Number(parseKina(debt) ?? 0) > Number(parseKina(income)) * 0.4

  if (send.error instanceof ApiError && send.error.status === 401) return <Navigate to="/portal/login" replace />

  if (send.data) {
    return (
      <PortalShell>
        <section className="ml-card flex flex-col gap-3" role="status" style={{ padding: '24px 16px' }}>
          <StatusPill status="PENDING" label="Application received" />
          <h1 className="font-display text-[24px] leading-[30px] font-semibold m-0">We have your application</h1>
          <p className="m-0">{send.data.message} Have your ID and your last 3 payslips ready.</p>
          <dl className="m-0 grid gap-x-4 gap-y-2 text-[13px]" style={{ gridTemplateColumns: 'auto minmax(0,1fr)' }}>
            <dt className="text-ink-muted">Amount</dt><dd className="m-0 font-semibold">{formatKina(send.data.amount)}</dd>
            <dt className="text-ink-muted">Term</dt><dd className="m-0">{send.data.months} months, about {formatKina(send.data.monthly_payment)} a month</dd>
            <dt className="text-ink-muted">Reference</dt><dd className="m-0 ml-ref">{send.data.ref}</dd>
          </dl>
          <Link to="/portal" className="ml-btn justify-center no-underline">Back to home</Link>
        </section>
      </PortalShell>
    )
  }

  return (
    <PortalShell>
      <header className="flex items-center gap-3">
        <Link to="/portal" aria-label="Back to home" className="inline-grid place-items-center w-11 h-11 rounded-md text-ink">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
        </Link>
        <h1 className="ml-h2">Apply for a personal loan</h1>
      </header>

      <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }}>
        <span className="ml-label" id="amount-label">How much do you need?</span>
        <div className="grid grid-cols-3 gap-2" role="group" aria-labelledby="amount-label">
          {AMOUNTS.map((a) => <button key={a} type="button" className="ml-chip" aria-pressed={a === amount} onClick={() => setAmount(a)}>K {a.toLocaleString('en-AU')}</button>)}
        </div>
        <span className="ml-label mt-1" id="term-label">Pay it back over</span>
        <div className="grid grid-cols-4 gap-2" role="group" aria-labelledby="term-label">
          {TERMS.map((m) => <button key={m} type="button" className="ml-chip" aria-pressed={m === months} onClick={() => setMonths(m)}>{m} mo</button>)}
        </div>
      </section>

      <section className="flex flex-col gap-1.5 p-4 rounded-[10px] bg-brand-soft" aria-live="polite">
        <span className="text-[13px] font-medium text-brand">Your monthly payment</span>
        {quote.data ? (
          <>
            <span className="font-display text-[32px] leading-[38px] font-semibold text-brand tabular-nums">{formatKina(quote.data.monthly_payment)}</span>
            <span className="text-[13px] leading-[18px]">{months} payments. You pay back about {formatKina(quote.data.total_repayable)}, of which {formatKina(quote.data.total_interest)} is interest.</span>
          </>
        ) : quote.isError ? (
          <div className="flex flex-col items-start gap-2" role="alert">
            <span className="text-[13px] leading-[18px]">We couldn't work out the payment just now.</span>
            <Button variant="secondary" onClick={() => quote.refetch()}>Try again</Button>
          </div>
        ) : <Skeleton h={60} />}
      </section>

      <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }}>
        <h2 className="ml-h2">About your income</h2>
        <Field label="Take-home pay each month (PGK)" prefix="K" inputMode="decimal" value={income} onChange={(e) => setIncome(e.target.value)}
          hint="We check this against your latest 3 payslips." error={touched ? incomeError : undefined} />
        <Field label="Other loan payments each month (PGK)" prefix="K" inputMode="decimal" value={debt} onChange={(e) => setDebt(e.target.value)}
          hint="Store cards, bank loans, other lenders. Enter 0 if none." error={touched ? debtError : undefined} />
        {stretch && <p className="ml-alert ml-alert-warning m-0" role="note">Your loan payments would be more than 40% of your pay. A longer term or a smaller amount is more likely to be approved.</p>}
      </section>

      {send.error && <div className="ml-alert ml-alert-danger" role="alert">{(send.error as Error).message}</div>}
      <Button variant="primary" className="justify-center" style={{ height: 48 }} disabled={send.isPending || !quote.data}
        onClick={() => { setTouched(true); if (!incomeError && !debtError) send.mutate() }}>
        {send.isPending ? 'Sending…' : 'Send application'}
      </Button>
      <p className="m-0 text-[12px] leading-4 text-ink-muted">Example at {quote.data ? Number(quote.data.annual_rate) : 24}% a year on the reducing balance. Your final rate and payment are confirmed in your loan agreement before you sign.</p>
    </PortalShell>
  )
}
