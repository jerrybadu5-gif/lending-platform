import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, files, type ActionResult, type LoanDetail } from '../api/client'
import { AssessmentCard, Button, DataTable, ErrorNote, Field, LoanStepper, Money, Skeleton, StatusPill } from '../components'
import { formatDate, formatKina, parseKina } from '../lib/format'
import { pillFor, stepFor } from '../lib/loan'
import { DownloadLink } from '../components/DownloadLink'
import { PayoutSteps, usePayout } from './Payout'

function suggestedAmount(l: LoanDetail): string {
  const cap = l.assessment ? Number(l.assessment.max_recommended_principal) : Number(l.principal)
  const n = Math.min(Number(l.principal), Math.floor(cap / 100) * 100)
  return formatKina(n > 0 ? n : l.principal, { currency: false })
}

export function LoanReview() {
  const id = Number(useParams().id)
  const q = useQuery({ queryKey: ['loan', id], queryFn: () => api.staff.loan(id) })
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <Skeleton h={400} />
  return <Review loan={q.data} />
}

function Review({ loan }: { loan: LoanDetail }) {
  const [showAll, setShowAll] = useState(false)
  const b = loan.borrower
  const a = loan.assessment
  const rows = showAll ? loan.schedule : loan.schedule.slice(0, 6)
  const payout = usePayout(loan)
  return (
    <>
      <div className="text-[13px] text-ink-muted"><Link to="/staff/applications">Applications</Link> / <span className="ml-ref">{loan.ref}</span></div>
      <header className="flex flex-wrap justify-between items-start gap-4">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="ml-title">{b.name}</h1>
            <StatusPill {...pillFor(loan.state, loan.days_overdue)} />
          </div>
          <div className="text-ink-muted">
            {loan.product} · {formatKina(loan.principal)} over {loan.term_months} months at {Number(loan.annual_rate)}% a year,{' '}
            {loan.interest_method === 'FLAT' ? 'flat' : 'reducing balance'} · <span className="ml-ref">{loan.ref}</span>
          </div>
        </div>
        <LoanStepper current={stepFor(loan.state, !!a, !!payout.data?.signed_agreement)} />
      </header>

      <div className="flex flex-wrap gap-6 items-start">
        <div className="flex flex-col gap-6" style={{ flex: '3 1 520px', minWidth: 0 }}>
          <section className="ml-card flex flex-col gap-4">
            <div className="flex flex-wrap justify-between items-center gap-3">
              <h2 className="ml-h2">Borrower</h2>
              <Link to={`/staff/borrowers/${b.id}`} className="text-[13px]">Open profile and documents</Link>
            </div>
            <dl className="grid gap-x-6 gap-y-4 m-0" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
              <Fact k="National ID" v={<span className="ml-ref">{b.national_id ?? '—'}</span>} />
              <Fact k="Phone" v={b.phone ?? '—'} />
              <Fact k="Employer or income source" v={b.employer ?? '—'} />
              <Fact k="Monthly income" v={<><strong>{formatKina(b.monthly_income)}</strong>{b.income_verified === false && <span className="text-warning"> · not yet verified</span>}</>} />
              <Fact k="Existing monthly debt" v={formatKina(b.existing_monthly_debt)} />
              <Fact k="Credit bureau score" v={b.credit_score ?? 'Not recorded'} />
              {b.monthly_business_noi && <Fact k="Business net income, monthly" v={formatKina(b.monthly_business_noi)} />}
            </dl>
          </section>

          <section className="ml-card p-0 overflow-hidden" style={{ padding: 0 }}>
            <div className="flex flex-wrap justify-between items-center gap-3 px-6 py-4">
              <h2 className="ml-h2">{loan.state === 'PENDING' ? 'Proposed schedule' : 'Repayment schedule'}</h2>
              <span className="text-[13px] text-ink-muted">Total interest {formatKina(loan.total_interest)}</span>
            </div>
            <DataTable rows={rows.map((r) => ({ ...r, id: r.number }))} columns={[
              { key: 'number', label: '#' },
              { key: 'due_date', label: 'Due', render: (r) => formatDate(r.due_date) },
              { key: 'principal', label: 'Principal', align: 'right', render: (r) => <Money amount={r.principal} /> },
              { key: 'interest', label: 'Interest', align: 'right', render: (r) => <Money amount={r.interest} /> },
              { key: 'total', label: 'Payment', align: 'right', render: (r) => <strong><Money amount={r.total} /></strong> },
              { key: 'state', label: 'Paid', align: 'right', render: (r) => r.complete ? <StatusPill status="PAID" /> : Number(r.paid) > 0 ? <Money amount={r.paid} /> : '—' },
            ]} />
            {loan.schedule.length > 6 && (
              <div className="px-6 py-3 border-t border-line text-[13px] text-ink-muted">
                Showing {rows.length} of {loan.schedule.length} installments.{' '}
                <button className="ml-linkbtn" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : 'Show all'}</button>
              </div>
            )}
          </section>
        </div>

        <div className="flex flex-col gap-6" style={{ flex: '2 1 360px', minWidth: 0 }}>
          {a && <AssessmentCard recommendation={a.recommendation} score={a.risk_score} dti={a.dti} maxDti={a.max_dti}
            monthlyPayment={a.monthly_payment} cap={a.max_recommended_principal} notes={a.notes} />}
          <Decision loan={loan} />
          <LoanDocuments loan={loan} />
          <section className="ml-card flex flex-col gap-3">
            <h2 className="ml-h2">History</h2>
            <ol className="m-0 pl-[18px] flex flex-col gap-2 text-[13px] leading-[18px]">
              {loan.history.map((h, i) => (
                <li key={i}>{formatDate(h.when)} · {h.text}{h.who && <span className="text-ink-muted"> · {h.who}</span>}</li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </>
  )
}

function Fact({ k, v }: { k: string; v: ReactNode }) {
  return <div><dt className="text-[13px] leading-[18px] text-ink-muted font-medium">{k}</dt><dd className="m-0 mt-0.5">{v}</dd></div>
}

const AGREEMENT_STATES = ['APPROVED', 'ACTIVE', 'ARREARS', 'ARREARS_LATE', 'CLOSED']
const STATEMENT_STATES = ['ACTIVE', 'ARREARS', 'ARREARS_LATE', 'CLOSED', 'WRITTEN_OFF']

function LoanDocuments({ loan }: { loan: LoanDetail }) {
  const links = [
    // While approved, the agreement is step 1 of the pay-out steps instead.
    AGREEMENT_STATES.includes(loan.state) && loan.state !== 'APPROVED' && { href: files.agreement(loan.id), label: 'Loan agreement' },
    { href: files.schedule(loan.id), label: 'Repayment schedule' },
    STATEMENT_STATES.includes(loan.state) && { href: files.statement(loan.id), label: 'Statement' },
  ].filter(Boolean) as { href: string; label: string }[]
  return (
    <section className="ml-card flex flex-col gap-3" aria-label="Documents">
      <h2 className="ml-h2">Print</h2>
      <div className="flex flex-wrap gap-2">
        {links.map((l) => <DownloadLink key={l.label} href={l.href} className="ml-btn ml-btn-sm no-underline">{l.label} (PDF)</DownloadLink>)}
      </div>
      {loan.state === 'PENDING' && <p className="m-0 text-[13px] text-ink-muted">The loan agreement can be printed once the loan is approved.</p>}
      {loan.payments.length > 0 && (
        <>
          <h3 className="m-0 text-[13px] font-semibold text-ink-muted">Receipts</h3>
          <ul className="m-0 p-0 list-none flex flex-col gap-1.5 text-[13px]">
            {loan.payments.slice(0, 6).map((p, i) => (
              <li key={p.id ?? i} className="flex justify-between gap-3">
                <span>{formatDate(p.paid_on)} · {formatKina(p.amount)} · {p.method}</span>
                {p.id != null && <DownloadLink href={files.receipt(loan.id, p.id)}>Receipt</DownloadLink>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function KycWarning({ borrowerId }: { borrowerId: number }) {
  const kyc = useQuery({ queryKey: ['kyc', borrowerId], queryFn: () => api.staff.kyc(borrowerId) })
  if (!kyc.data || kyc.data.complete) return null
  return (
    <div className="ml-alert ml-alert-warning flex flex-col gap-1" role="note">
      <strong>Documents still needed before approval</strong>
      <ul className="m-0 pl-[18px]">{kyc.data.missing.map((m) => <li key={m}>{m}</li>)}</ul>
      <Link to={`/staff/borrowers/${borrowerId}`}>Upload them on the borrower's profile</Link>
    </div>
  )
}

function Decision({ loan }: { loan: LoanDetail }) {
  const qc = useQueryClient()
  const kyc = useQuery({ queryKey: ['kyc', loan.borrower.id], queryFn: () => api.staff.kyc(loan.borrower.id), enabled: loan.state === 'PENDING' })
  const kycMissing = kyc.data ? !kyc.data.complete : false
  const [amount, setAmount] = useState(suggestedAmount(loan))
  const [note, setNote] = useState('')
  const [confirmReject, setConfirmReject] = useState(false)
  const [result, setResult] = useState<ActionResult | null>(null)
  const done = (r: ActionResult) => {
    setResult(r)
    setConfirmReject(false)
    qc.invalidateQueries({ queryKey: ['loan', loan.id] })
    qc.invalidateQueries({ queryKey: ['payout', loan.id] })
    qc.invalidateQueries({ queryKey: ['loans'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const approve = useMutation({ mutationFn: () => api.staff.approve(loan.id, parseKina(amount) ?? '', note), onSuccess: done })
  const reject = useMutation({ mutationFn: () => api.staff.reject(loan.id, note), onSuccess: done })
  const reassess = useMutation({ mutationFn: () => api.staff.assess(loan.id), onSuccess: (d) => qc.setQueryData(['loan', loan.id], d) })
  const error = approve.error ?? reject.error ?? reassess.error
  const amountError = parseKina(amount) === null ? 'Enter an amount like 13,000.00' : undefined

  return (
    <section className="ml-card flex flex-col gap-4" aria-label="Decision">
      <h2 className="ml-h2">{loan.state === 'PENDING' ? 'Decision' : 'Next step'}</h2>
      {result && <div role="status" className="ml-alert" style={{ background: 'var(--surface-sunken)', color: 'var(--ink)' }}>{result.message}</div>}
      {error && <div className="ml-alert ml-alert-danger" role="alert">{(error as Error).message}</div>}

      {loan.state === 'PENDING' && !confirmReject && (
        <>
          <KycWarning borrowerId={loan.borrower.id} />
          <Field label="Approved amount (PGK)" prefix="K" inputMode="decimal" value={amount}
            onChange={(e) => setAmount(e.target.value)} error={amountError}
            hint={loan.assessment ? `Policy capacity is ${formatKina(loan.assessment.max_recommended_principal)} for this client.` : undefined} />
          <div className="ml-field">
            <label className="ml-label" htmlFor="decision-note">Note for the file</label>
            <textarea id="decision-note" className="ml-input" style={{ height: 88, padding: '10px 12px' }} value={note}
              onChange={(e) => setNote(e.target.value)} placeholder="Why this decision, for the next person who reads the file" />
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" disabled={!!amountError || approve.isPending || kycMissing} onClick={() => approve.mutate()}>
              Approve {parseKina(amount) ? formatKina(parseKina(amount)) : ''}
            </Button>
            <Button variant="danger" onClick={() => setConfirmReject(true)}>Reject</Button>
            <Button variant="quiet" disabled={reassess.isPending} onClick={() => reassess.mutate()}>Run check again</Button>
          </div>
        </>
      )}

      {loan.state === 'PENDING' && confirmReject && (
        <div className="flex flex-col gap-3 p-4 rounded-md bg-danger-soft">
          <strong className="text-danger">Reject this application?</strong>
          <span className="text-[13px] leading-[18px]">The borrower is told by SMS and the loan moves to Rejected. This can't be undone.</span>
          {note.trim().length < 3 && <span className="text-[13px] font-medium text-danger">Add a note saying why before you reject.</span>}
          <div className="flex flex-wrap gap-3">
            <Button variant="danger" disabled={note.trim().length < 3 || reject.isPending} onClick={() => reject.mutate()}>Reject application</Button>
            <Button variant="quiet" onClick={() => setConfirmReject(false)}>Keep reviewing</Button>
          </div>
        </div>
      )}

      {loan.state === 'APPROVED' && <PayoutSteps loan={loan} onDone={done} />}

      {['ACTIVE', 'ARREARS', 'ARREARS_LATE'].includes(loan.state) && (
        <>
          <p className="m-0">Next payment {formatKina(loan.next_due_amount)} on {formatDate(loan.next_due_date)}. Still owed {formatKina(loan.outstanding)}.</p>
          <Link to={`/staff/repayments?loan=${loan.id}`} className="ml-btn ml-btn-primary self-start no-underline">Record repayment</Link>
        </>
      )}

      {loan.state === 'PENDING' && <p className="m-0 text-[13px] leading-[18px] text-ink-muted">If maker-checker is on in Fineract, a second credit manager confirms approvals and disbursements.</p>}
    </section>
  )
}
