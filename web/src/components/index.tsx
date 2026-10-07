// McLender design-system components (TypeScript port of the design system bundle; same props and classes).
import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'
import { formatKina, formatPercent } from '../lib/format'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

export function Button({ variant = 'secondary', size, className, type = 'button', ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger'; size?: 'md' | 'sm' }) {
  return <button type={type} {...rest} className={cx('ml-btn', `ml-btn-${variant}`, size === 'sm' && 'ml-btn-sm', className)} />
}

export function Money({ amount, size, tone, className }:
  { amount: string | number | null | undefined; size?: 'md' | 'lg'; tone?: 'gold' | 'danger' | 'success' | 'warning' | 'muted'; className?: string }) {
  return <span className={cx('ml-money', size && `ml-money-${size}`, tone && `ml-tone-${tone}`, className)}>{formatKina(amount)}</span>
}

export type PillStatus =
  | 'DRAFT' | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ACTIVE' | 'ARREARS' | 'ARREARS_LATE' | 'CLOSED' | 'WRITTEN_OFF'
  | 'WITHDRAWN' | 'PAID' | 'DUE' | 'OVERDUE' | 'APPROVE' | 'REFER' | 'DECLINE'
const STATUS: Record<PillStatus, [string, string]> = {
  DRAFT: ['Draft', 'neutral'], PENDING: ['Pending approval', 'info'], APPROVED: ['Approved', 'brand'],
  REJECTED: ['Rejected', 'danger'], ACTIVE: ['Active', 'success'], ARREARS: ['In arrears', 'warning'],
  ARREARS_LATE: ['In arrears', 'danger'], CLOSED: ['Closed', 'neutral'], WRITTEN_OFF: ['Written off', 'danger'],
  WITHDRAWN: ['Withdrawn', 'neutral'], PAID: ['Paid', 'success'], DUE: ['Due', 'gold'], OVERDUE: ['Overdue', 'danger'],
  APPROVE: ['Approve', 'success'], REFER: ['Refer', 'warning'], DECLINE: ['Decline', 'danger'],
}

export function StatusPill({ status, days, label }: { status: PillStatus; days?: number; label?: string }) {
  const [word, tone] = STATUS[status] ?? [status, 'neutral']
  return (
    <span className={`ml-pill ml-pill-${tone}`}>
      <span className="ml-pill-dot" aria-hidden="true" />
      {label ?? (days ? `${word} · ${days} days` : word)}
    </span>
  )
}

export function StatTile({ label, value, delta, deltaTone = 'muted', hint, emphasis }:
  { label: string; value: ReactNode; delta?: string; deltaTone?: 'success' | 'warning' | 'danger' | 'muted'; hint?: string; emphasis?: 'gold' }) {
  return (
    <div className={cx('ml-stat', emphasis && `ml-stat-${emphasis}`)}>
      <div className="ml-stat-label">{label}</div>
      <div className="ml-stat-value">{value}</div>
      {delta && <div className={`ml-stat-delta ml-tone-${deltaTone}`}>{delta}</div>}
      {hint && <div className="ml-stat-hint">{hint}</div>}
    </div>
  )
}

export function Field({ label, hint, error, prefix, optional, ...input }:
  InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; prefix?: string; optional?: boolean }) {
  const autoId = useId()
  const id = input.id ?? autoId
  const hintId = `${id}-hint`
  const control = (
    <input {...input} id={id} className="ml-input" aria-invalid={error ? true : undefined}
      aria-describedby={hint || error ? hintId : undefined} />
  )
  return (
    <div className={cx('ml-field', error && 'ml-field-error')}>
      <label className="ml-label" htmlFor={id}>
        {label}{optional && <span className="ml-optional"> optional</span>}
      </label>
      {prefix ? <div className="ml-affix"><span className="ml-prefix">{prefix}</span>{control}</div> : control}
      {(error || hint) && <div id={hintId} className={error ? 'ml-error' : 'ml-hint'} role={error ? 'alert' : undefined}>{error ?? hint}</div>}
    </div>
  )
}

export interface Column<R> { key: string; label: string; align?: 'left' | 'right'; render?: (row: R) => ReactNode }

export function DataTable<R extends { id?: number | string }>({ columns, rows, caption, selectedId, onRowClick, empty }:
  { columns: Column<R>[]; rows: R[]; caption?: string; selectedId?: number | string; onRowClick?: (row: R) => void; empty?: ReactNode }) {
  return (
    <div className="ml-table-wrap">
      <table className="ml-table">
        {caption && <caption>{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c.key} scope="col" className={c.align === 'right' ? 'ml-right' : undefined}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={columns.length} className="ml-muted">{empty ?? 'Nothing here.'}</td></tr>}
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className={cx(selectedId != null && r.id === selectedId && 'ml-selected', onRowClick && 'ml-click')}
              onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === 'right' ? 'ml-right' : undefined}>
                  {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const STEPS = ['Submitted', 'Assessed', 'Approved', 'Signed', 'Disbursed', 'Repaying', 'Closed']
export function LoanStepper({ current, steps = STEPS }: { current: number; steps?: string[] }) {
  return (
    <ol className="ml-steps" aria-label="Loan progress">
      {steps.map((s, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'todo'
        return (
          <li key={s} className={`ml-step ml-step-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
            <span className="ml-step-mark" aria-hidden="true">{state === 'done' ? '✓' : i + 1}</span><span>{s}</span>
          </li>
        )
      })}
    </ol>
  )
}

export function AssessmentCard({ recommendation, score, dti, maxDti = '0.40', monthlyPayment, cap, notes = [] }:
  { recommendation: 'APPROVE' | 'REFER' | 'DECLINE'; score: string; dti: string | null; maxDti?: string; monthlyPayment: string; cap: string; notes?: string[] }) {
  const d = Number(dti ?? 0), max = Number(maxDti)
  const pct = Math.min(d / (max * 1.5), 1) * 100
  const tone = d > max ? (d > max + 0.05 ? 'danger' : 'warning') : 'success'
  return (
    <section className="ml-card ml-assess" aria-label="Affordability assessment">
      <header className="ml-assess-head">
        <div>
          <div className="ml-eyebrow">Affordability check</div>
          <div className="ml-assess-score">{score}<span> / 100 risk score</span></div>
        </div>
        <StatusPill status={recommendation} />
      </header>
      <div className="ml-meter-label"><span>Debt-to-income</span><strong>{formatPercent(dti)}</strong><span className="ml-muted">limit {formatPercent(maxDti, 0)}</span></div>
      <div className="ml-meter" role="img" aria-label={`Debt-to-income ${formatPercent(dti)} against a limit of ${formatPercent(maxDti, 0)}`}>
        <div className={`ml-meter-fill ml-meter-${tone}`} style={{ width: `${pct}%` }} />
        <div className="ml-meter-limit" style={{ left: `${100 / 1.5}%` }} />
      </div>
      <dl className="ml-assess-facts">
        <div><dt>Monthly payment</dt><dd><Money amount={monthlyPayment} /></dd></div>
        <div><dt>Most we can lend</dt><dd><Money amount={cap} /></dd></div>
      </dl>
      {notes.length > 0 && <ul className="ml-assess-notes">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </section>
  )
}

export function Skeleton({ h = 20, className }: { h?: number; className?: string }) {
  return <div className={cx('ml-skeleton', className)} style={{ minHeight: h }} aria-hidden="true" />
}

export function ErrorNote({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className="ml-alert ml-alert-danger flex flex-wrap items-center gap-3" role="alert">
      <span>{msg}</span>{retry && <Button size="sm" onClick={retry}>Try again</Button>}
    </div>
  )
}
