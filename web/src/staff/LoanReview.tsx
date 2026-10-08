import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, DOCUMENT_LABELS, files, type ActionResult, type LoanDetail } from '../api/client'
import { AssessmentCard, Button, DataTable, ErrorNote, LoanStepper, Money, Skeleton, StatusPill } from '../components'
import { formatDate, formatKina } from '../lib/format'
import { useMe } from '../lib/me'
import { pillFor, stepFor } from '../lib/loan'
import { DownloadLink } from '../components/DownloadLink'
import { PayoutSteps, usePayout } from './Payout'
import { ManagerDecision, OfficerReview, OfficerSummary, ReviewDocuments, useLoanRefresh } from './Review'
import { DocumentViewer } from '../components/DocumentViewer'

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

          {['PENDING', 'APPROVED'].includes(loan.state) && <ReviewDocuments borrowerId={b.id} />}

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

/** Files kept on the loan in Fineract: the signed agreement and a PDF receipt for each repayment. */
function FiledDocuments({ loan }: { loan: LoanDetail }) {
  const q = useQuery({ queryKey: ['loan-documents', loan.id, loan.payments.length], queryFn: () => api.staff.loanDocuments(loan.id) })
  const [open, setOpen] = useState<number | null>(null)
  const docs = q.data ?? []
  const doc = docs.find((d) => d.id === open)
  if (!docs.length) return null
  return (
    <>
      <h3 className="m-0 text-[13px] font-semibold text-ink-muted">Kept on file</h3>
      <ul className="m-0 p-0 list-none flex flex-col gap-1.5 text-[13px]">
        {docs.slice(0, 8).map((d) => (
          <li key={d.id} className="flex justify-between gap-3">
            <button className="ml-linkbtn text-left break-all" onClick={() => setOpen(d.id)}>{d.file_name}</button>
            <span className="text-ink-muted shrink-0">{(DOCUMENT_LABELS[d.kind] ?? 'Document').replace('Payment receipt', 'Receipt')} · {formatDate(d.uploaded_on)}</span>
          </li>
        ))}
      </ul>
      {doc && <DocumentViewer doc={doc} href={files.loanDocument(loan.id, doc.id)} onClose={() => setOpen(null)}
        removeNote={doc.kind === 'receipt' ? 'Receipts are part of the payment record and stay on file.'
          : doc.kind === 'signed_agreement' ? 'A signed agreement can only be removed before pay-out, from the pay-out steps.' : undefined} />}
    </>
  )
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
      <FiledDocuments loan={loan} />
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

function Decision({ loan }: { loan: LoanDetail }) {
  const { isApprover, me } = useMe()
  const refresh = useLoanRefresh(loan.id)
  const [result, setResult] = useState<ActionResult | null>(null)
  const done = (r: ActionResult) => { setResult(r); refresh() }
  const stage = loan.review?.stage ?? 'DRAFT'
  const qc = useQueryClient()
  const reassess = useMutation({ mutationFn: () => api.staff.assess(loan.id), onSuccess: (d) => qc.setQueryData(['loan', loan.id], d) })
  // The credit manager always decides; the loan officer reviews until he has sent it up.
  const title = loan.state !== 'PENDING' ? 'Next step'
    : isApprover ? 'Decision' : stage === 'SUBMITTED' ? 'With the credit manager' : 'Your review'

  return (
    <section className="ml-card flex flex-col gap-4" aria-label="Decision">
      <h2 className="ml-h2">{title}</h2>
      {result && <div role="status" className="ml-alert" style={{ background: 'var(--surface-sunken)', color: 'var(--ink)' }}>{result.message}</div>}

      {loan.state === 'PENDING' && !me && <Skeleton h={160} />}
      {loan.state === 'PENDING' && me && isApprover && (
        <ManagerDecision loan={loan} suggested={suggestedAmount(loan)} onDone={done} username={me.username} reviewRequired={me.review_required ?? true} />
      )}
      {loan.state === 'PENDING' && me && !isApprover && stage !== 'SUBMITTED' && <OfficerReview loan={loan} suggested={suggestedAmount(loan)} />}
      {loan.state === 'PENDING' && me && !isApprover && stage === 'SUBMITTED' && (
        <>
          <OfficerSummary loan={loan} />
          <p className="m-0 text-[13px] text-ink-muted">Waiting for a credit manager to approve, reject or send it back to you.</p>
        </>
      )}
      {loan.state === 'PENDING' && (
        <Button variant="quiet" className="self-start" disabled={reassess.isPending} onClick={() => reassess.mutate()}>Run the affordability check again</Button>
      )}

      {loan.state === 'APPROVED' && <PayoutSteps loan={loan} onDone={done} canPayOut={isApprover} />}

      {['ACTIVE', 'ARREARS', 'ARREARS_LATE'].includes(loan.state) && (
        <>
          <p className="m-0">Next payment {formatKina(loan.next_due_amount)} on {formatDate(loan.next_due_date)}. Still owed {formatKina(loan.outstanding)}.</p>
          <Link to={`/staff/repayments?loan=${loan.id}`} className="ml-btn ml-btn-primary self-start no-underline">Record repayment</Link>
        </>
      )}

      {loan.state === 'PENDING' && isApprover && <p className="m-0 text-[13px] leading-[18px] text-ink-muted">If maker-checker is on in Fineract, a second credit manager confirms approvals and disbursements.</p>}
    </section>
  )
}
