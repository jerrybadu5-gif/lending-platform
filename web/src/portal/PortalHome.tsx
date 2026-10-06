import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Button, ErrorNote, Skeleton, StatusPill } from '../components'
import { formatDate, formatKina, weekdayDate } from '../lib/format'
import { PortalShell } from './PortalShell'

export default function PortalHome() {
  const q = useQuery({ queryKey: ['portal', 'home'], queryFn: api.portal.home })
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()

  if (q.error instanceof ApiError && q.error.status === 401) return <Navigate to="/portal/login" replace />
  if (q.error) return <PortalShell><ErrorNote error={q.error} retry={() => q.refetch()} /></PortalShell>
  if (!q.data) return <PortalShell><Skeleton h={140} /><Skeleton h={120} /></PortalShell>
  const { first_name, company_name, loan } = q.data

  async function signOut() {
    await api.portal.logout()
    qc.removeQueries({ queryKey: ['portal'] })
    nav('/portal/login')
  }

  return (
    <PortalShell>
      <header className="flex justify-between items-center">
        <div className="flex flex-col gap-0.5">
          <span className="text-[13px] text-ink-muted">{company_name}</span>
          <span className="text-[18px] leading-[26px] font-semibold">Hello, {first_name}</span>
        </div>
        <Button variant="quiet" size="sm" onClick={signOut}>Sign out</Button>
      </header>

      {!loan ? (
        <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }}>
          <h2 className="ml-h2">You have no loan with us right now</h2>
          <Link to="/portal/apply" className="ml-btn ml-btn-primary justify-center no-underline">Apply for a loan</Link>
        </section>
      ) : (
        <>
          <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }}>
            <span className="text-[13px] text-ink-muted font-medium">Left to pay, including interest</span>
            <span className="font-display text-[32px] leading-[38px] font-semibold tabular-nums">{formatKina(loan.left_to_pay)}</span>
            <div className="flex flex-col gap-1.5">
              <div className="h-2 rounded bg-surface-sunken" role="img" aria-label={`${loan.payments_made} of ${loan.payments_total} payments made`}>
                <div className="h-2 rounded bg-brand" style={{ width: `${(loan.payments_made / Math.max(loan.payments_total, 1)) * 100}%` }} />
              </div>
              <span className="text-[13px] text-ink-muted">{loan.payments_made} of {loan.payments_total} payments made · you borrowed {formatKina(loan.borrowed)} · <span className="ml-ref">{loan.ref}</span></span>
            </div>
          </section>

          {loan.next_due_amount && loan.next_due_date && (
            <section className="flex flex-col gap-2 p-4 rounded-[10px]" style={{ background: loan.days_overdue ? 'var(--danger-soft)' : 'var(--kina-gold-soft)' }}>
              <span className="ml-eyebrow" style={{ color: loan.days_overdue ? 'var(--danger)' : 'var(--kina-gold)' }}>
                {loan.days_overdue ? `Overdue by ${loan.days_overdue} days` : 'Next payment'}
              </span>
              <span className="text-[24px] leading-[30px] font-semibold tabular-nums" style={{ color: loan.days_overdue ? 'var(--danger)' : 'var(--kina-gold)' }}>
                {formatKina(loan.next_due_amount)}
              </span>
              <span className="text-[13px]">Due {weekdayDate(loan.next_due_date)}</span>
              <Button variant="primary" className="justify-center" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Hide ways to pay' : 'How to pay'}</Button>
            </section>
          )}

          {open && (
            <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }} aria-label="Ways to pay">
              <h2 className="ml-h2">Ways to pay</h2>
              <p className="m-0 text-[13px] leading-[18px] text-ink-muted">Always use your payment reference so we can match your payment.</p>
              <div className="flex justify-between items-center p-3 rounded-md bg-surface-sunken">
                <span className="text-[13px] text-ink-muted">Your reference</span>
                <span className="ml-ref" style={{ fontSize: 18 }}>{loan.payment_reference}</span>
              </div>
              {loan.ways_to_pay.map((w) => (
                <div key={w.name} className="flex flex-col gap-0.5 p-3 rounded-md border border-line-strong">
                  <strong>{w.name}</strong><span className="text-[13px] text-ink-muted">{w.how}</span>
                </div>
              ))}
              <p className="m-0 text-[13px] leading-[18px] text-ink-muted">You get an SMS receipt when we record your payment.</p>
            </section>
          )}

          <section className="ml-card flex flex-col gap-3" style={{ padding: 16 }}>
            <h2 className="ml-h2">Recent payments</h2>
            {loan.recent_payments.length === 0 && <p className="m-0 text-ink-muted">No payments yet.</p>}
            {loan.recent_payments.map((p, i) => (
              <div key={i} className="flex justify-between items-center gap-3 pt-3 border-t border-line">
                <span className="flex flex-col gap-0.5"><span>{formatDate(p.paid_on)}</span><span className="text-[13px] text-ink-muted">{p.method}</span></span>
                <span className="flex flex-col items-end gap-1"><strong className="tabular-nums">{formatKina(p.amount)}</strong><StatusPill status="PAID" label="Received" /></span>
              </div>
            ))}
          </section>
        </>
      )}
    </PortalShell>
  )
}
