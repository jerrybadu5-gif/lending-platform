import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, files, type CollectionItem, type PaymentMethod, type Receipt } from '../api/client'
import { Button, DataTable, ErrorNote, Field, Money, Skeleton, StatusPill } from '../components'
import { formatDate, formatKina, parseKina } from '../lib/format'
import { DownloadLink } from '../components/DownloadLink'

type View = 'today' | 'arrears' | 'all'
const METHODS: { id: PaymentMethod; label: string; hint: string; ref: string; refHint: string }[] = [
  { id: 'cash', label: 'Cash', hint: 'At the branch', ref: 'Receipt book number', refHint: 'e.g. 004127' },
  { id: 'bank', label: 'Bank transfer', hint: 'BSP, Kina Bank, ANZ, Westpac', ref: 'Bank reference', refHint: 'Reference on the statement' },
  { id: 'mobile', label: 'Mobile money', hint: 'CellMoni, MiCash', ref: 'Mobile money transaction ID', refHint: 'e.g. CM8841203377' },
  { id: 'payroll', label: 'Payroll deduction', hint: 'Employer remittance', ref: 'Remittance advice number', refHint: 'From the employer' },
]

export function Repayments() {
  const [view, setView] = useState<View>('today')
  const [params] = useSearchParams()
  const q = useQuery({ queryKey: ['collections', view], queryFn: () => api.staff.collections(view) })
  const all = useQuery({ queryKey: ['collections', 'all'], queryFn: () => api.staff.collections('all') })
  const asOf = useQuery({ queryKey: ['dashboard'], queryFn: api.staff.dashboard }).data?.as_of
  const [picked, setPicked] = useState<CollectionItem | null>(null)
  const fromLink = params.get('loan') ? Number(params.get('loan')) : null
  const rows = q.data ?? []
  // Keep the picked loan even after it drops off the list (just paid), so its receipt stays on screen.
  const sel = picked ?? (all.data ?? []).find((c) => c.loan_id === fromLink) ?? rows[0]
  const setSelected = (loanId: number) => setPicked((all.data ?? []).find((c) => c.loan_id === loanId) ?? null)
  const counts = { today: all.data?.filter((c) => c.days_overdue === 0).length, arrears: all.data?.filter((c) => c.days_overdue > 0).length, all: all.data?.length }

  return (
    <>
      <header className="flex flex-col gap-1">
        <div className="ml-eyebrow">{asOf ? formatDate(asOf) : ' '}</div>
        <h1 className="ml-title">Repayments and collections</h1>
      </header>
      <div role="tablist" aria-label="Collections list" className="flex flex-wrap gap-1 border-b border-line pb-2">
        {(['today', 'arrears', 'all'] as View[]).map((v) => (
          <button key={v} role="tab" aria-selected={view === v} className={`ml-btn ml-btn-sm ${view === v ? '' : 'ml-btn-quiet'}`} onClick={() => setView(v)}>
            {{ today: 'Due today', arrears: 'In arrears', all: 'All open' }[v]}{counts[v] !== undefined ? ` (${counts[v]})` : ''}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-6 items-start">
        <section style={{ flex: '3 1 520px', minWidth: 0 }} aria-label="Loans">
          {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : q.isLoading ? <Skeleton h={240} /> : (
            <DataTable rows={rows.map((r) => ({ ...r, id: r.loan_id }))} selectedId={sel?.loan_id} onRowClick={(r) => setSelected(r.loan_id)}
              empty={view === 'today' ? 'Nothing else is due today.' : 'No loans in arrears.'}
              columns={[
                { key: 'borrower_name', label: 'Borrower', render: (r) => <><button className="ml-linkbtn" onClick={() => setSelected(r.loan_id)}>{r.borrower_name}</button><div className="ml-ref text-ink-muted">{r.ref}</div></> },
                { key: 'state', label: 'Status', render: (r) => r.days_overdue ? <StatusPill status={r.days_overdue > 30 ? 'ARREARS_LATE' : 'ARREARS'} days={r.days_overdue} /> : <StatusPill status="DUE" /> },
                { key: 'phone', label: 'Phone', render: (r) => <span className="tabular-nums">{r.phone ?? '—'}</span> },
                { key: 'amount_due', label: 'Amount due', align: 'right', render: (r) => <strong><Money amount={r.amount_due} tone={r.days_overdue > 30 ? 'danger' : r.days_overdue ? undefined : 'gold'} /></strong> },
              ]} />
          )}
        </section>
        <section className="ml-card flex flex-col gap-4" aria-label="Record repayment" style={{ flex: '2 1 360px', minWidth: 0 }}>
          {sel && asOf ? <RecordForm key={sel.loan_id} item={sel} today={asOf} /> : <p className="m-0 text-ink-muted">Choose a loan on the left to record a payment.</p>}
        </section>
      </div>
    </>
  )
}

function RecordForm({ item, today }: { item: CollectionItem; today: string }) {
  const qc = useQueryClient()
  const [method, setMethod] = useState<PaymentMethod>('mobile')
  const [amount, setAmount] = useState(formatKina(item.amount_due, { currency: false }))
  const [reference, setReference] = useState('')
  const [date, setDate] = useState(today)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const m = METHODS.find((x) => x.id === method)!
  const save = useMutation({
    mutationFn: () => api.staff.repay(item.loan_id, { amount: parseKina(amount) ?? '', method, reference: reference.trim(), received_on: date }),
    onSuccess: (r) => {
      setReceipt(r)
      qc.invalidateQueries({ queryKey: ['collections'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['loan', item.loan_id] })
    },
  })
  const amountError = parseKina(amount) === null ? 'Enter the amount received, like 1,318.74' : undefined
  const refError = reference.trim().length < 2 ? 'Enter the reference so the payment can be traced.' : undefined
  const [touched, setTouched] = useState(false)

  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!amountError && !refError) save.mutate()
  }

  if (receipt) {
    return (
      <div role="status" className="flex flex-col gap-4">
        <StatusPill status="PAID" label="Repayment recorded" />
        <div className="flex flex-col gap-1">
          <span className="font-display text-[32px] leading-[38px] font-semibold tabular-nums">{formatKina(receipt.amount)}</span>
          <span>from {receipt.borrower_name} by {METHODS.find((x) => x.id === receipt.method)?.label.toLowerCase()}</span>
        </div>
        <dl className="m-0 grid gap-x-4 gap-y-2 text-[13px]" style={{ gridTemplateColumns: 'auto minmax(0,1fr)' }}>
          <dt className="text-ink-muted">Receipt</dt><dd className="m-0 ml-ref">{receipt.receipt_no}</dd>
          <dt className="text-ink-muted">Loan</dt><dd className="m-0 ml-ref">{receipt.ref}</dd>
          <dt className="text-ink-muted">SMS receipt</dt><dd className="m-0">{receipt.sms_sent_to ? `Sent to ${receipt.sms_sent_to}` : 'No phone on file'}</dd>
        </dl>
        {receipt.payment_id != null && (
          <DownloadLink href={files.receipt(receipt.loan_id, receipt.payment_id)} className="ml-btn ml-btn-sm self-start no-underline">Print receipt (PDF)</DownloadLink>
        )}
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1">
        <div className="ml-eyebrow">Record repayment</div>
        <h2 className="ml-h2">{item.borrower_name}</h2>
        <div className="text-[13px] text-ink-muted"><span className="ml-ref">{item.ref}</span> · {item.note}</div>
      </div>
      <fieldset className="border-0 m-0 p-0 flex flex-col gap-2">
        <legend className="ml-label mb-2">Paid by</legend>
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
          {METHODS.map((x) => (
            <button type="button" key={x.id} className="ml-method" aria-pressed={x.id === method} onClick={() => setMethod(x.id)}>
              <span className="font-semibold">{x.label}</span><small className="text-[12px] text-ink-muted">{x.hint}</small>
            </button>
          ))}
        </div>
      </fieldset>
      <Field label="Amount received (PGK)" prefix="K" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)}
        error={touched ? amountError : undefined} hint="Paid in the order penalties, fees, interest, principal." />
      <Field label={m.ref} placeholder={m.refHint} value={reference} onChange={(e) => setReference(e.target.value)} error={touched ? refError : undefined} />
      <Field label="Date received" type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} />
      {save.error && <div className="ml-alert ml-alert-danger" role="alert">{(save.error as Error).message}</div>}
      <Button type="submit" variant="primary" className="justify-center" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Record repayment'}</Button>
    </form>
  )
}
