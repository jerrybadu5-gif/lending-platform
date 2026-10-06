import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api, DOCUMENT_LABELS, files, type BorrowerProfile as Profile, type DocumentKind,
} from '../api/client'
import { Button, DataTable, ErrorNote, Field, Money, Skeleton, StatusPill } from '../components'
import { formatDate, formatKina, parseKina } from '../lib/format'
import { pillFor } from '../lib/loan'
import { DownloadLink } from '../components/DownloadLink'

const KYC_KINDS: DocumentKind[] = ['id', 'payslip', 'bank_statement', 'deduction_authority']
const TERMS = [3, 6, 12, 18, 24, 36]
const ACCEPT = 'application/pdf,image/jpeg,image/png'

export function BorrowerProfile() {
  const id = Number(useParams().id)
  const q = useQuery({ queryKey: ['borrower', id], queryFn: () => api.staff.borrower(id) })
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <Skeleton h={400} />
  return <ProfileView p={q.data} />
}

function ProfileView({ p }: { p: Profile }) {
  const b = p.borrower
  const pending = p.loans.find((l) => l.state === 'PENDING')
  return (
    <>
      <div className="text-[13px] text-ink-muted"><Link to="/staff/borrowers">Borrowers</Link> / {b.name}</div>
      <header className="flex flex-wrap justify-between items-start gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="ml-title">{b.name}</h1>
          <span className="text-ink-muted">{b.phone ?? 'No phone'} · {b.employer ?? 'Employer not recorded'}</span>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {p.kyc.complete
            ? <StatusPill status="ACTIVE" label="Documents complete" />
            : <StatusPill status="ARREARS" label={`${p.kyc.missing.length} document${p.kyc.missing.length === 1 ? '' : 's'} needed`} />}
          <Link to={`/staff/borrowers/${b.id}/edit`} className="ml-btn ml-btn-sm no-underline">Edit details</Link>
        </div>
      </header>

      <div className="flex flex-wrap gap-6 items-start">
        <div className="flex flex-col gap-6" style={{ flex: '3 1 520px', minWidth: 0 }}>
          <section className="ml-card flex flex-col gap-4">
            <h2 className="ml-h2">Details</h2>
            <dl className="grid gap-x-6 gap-y-4 m-0" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
              <Fact k="NID number" v={<span className="ml-ref">{b.national_id ?? '—'}</span>} />
              <Fact k="Date of birth" v={formatDate(b.date_of_birth)} />
              <Fact k="Gender" v={b.gender ? (b.gender === 'female' ? 'Female' : 'Male') : '—'} />
              <Fact k="Address" v={b.address ?? '—'} />
              <Fact k="Payroll number" v={b.payroll_number ?? '—'} />
              <Fact k="Take-home pay, monthly" v={formatKina(b.monthly_income)} />
              <Fact k="Other loan payments, monthly" v={formatKina(b.existing_monthly_debt)} />
              <Fact k="Bank account" v={b.bank ? <>{b.bank.bank}{b.bank.branch ? `, ${b.bank.branch}` : ''}<br /><span className="ml-ref">{b.bank.account_number}</span> · {b.bank.account_name}</> : 'Not recorded'} />
              <Fact k="Next of kin" v={b.next_of_kin ? <>{b.next_of_kin.name} ({b.next_of_kin.relationship})<br />{b.next_of_kin.phone}</> : 'Not recorded'} />
            </dl>
          </section>

          <Documents p={p} />

          <section className="ml-card p-0 overflow-hidden" style={{ padding: 0 }}>
            <h2 className="ml-h2 px-6 py-4">Loans</h2>
            <LoansTable p={p} />
          </section>
        </div>

        <div className="flex flex-col gap-6" style={{ flex: '2 1 340px', minWidth: 0 }}>
          <KycChecklist p={p} />
          {pending
            ? <section className="ml-card flex flex-col gap-2"><h2 className="ml-h2">Application waiting</h2>
                <p className="m-0"><Link to={`/staff/loans/${pending.id}`}>{pending.ref}</Link> for {formatKina(pending.principal)} is waiting for a decision.</p></section>
            : <NewApplication borrowerId={b.id} />}
        </div>
      </div>
    </>
  )
}

function Fact({ k, v }: { k: string; v: ReactNode }) {
  return <div><dt className="text-[13px] leading-[18px] text-ink-muted font-medium">{k}</dt><dd className="m-0 mt-0.5">{v}</dd></div>
}

function useUpload(borrowerId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, file }: { kind: DocumentKind; file: File }) => api.staff.upload(borrowerId, kind, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['borrower', borrowerId] })
      qc.invalidateQueries({ queryKey: ['kyc', borrowerId] })
    },
  })
}

function UploadButton({ borrowerId, kind, label, variant = 'secondary' }:
  { borrowerId: number; kind: DocumentKind; label: string; variant?: 'secondary' | 'quiet' }) {
  const input = useRef<HTMLInputElement>(null)
  const up = useUpload(borrowerId)
  return (
    <span className="flex flex-col gap-1 items-end">
      <input ref={input} type="file" accept={ACCEPT} hidden aria-label={`${label}: choose file`}
        data-testid={`upload-${kind}`}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate({ kind, file: f }); e.target.value = '' }} />
      <Button size="sm" variant={variant} disabled={up.isPending} onClick={() => input.current?.click()}>
        {up.isPending ? 'Uploading…' : label}
      </Button>
      {up.error && <span className="text-[12px] text-danger" role="alert">{(up.error as Error).message}</span>}
    </span>
  )
}

function KycChecklist({ p }: { p: Profile }) {
  return (
    <section className="ml-card flex flex-col gap-3" aria-label="Documents needed for approval">
      <h2 className="ml-h2">Documents for approval</h2>
      <p className="m-0 text-[13px] text-ink-muted">PDF or photo (JPG, PNG), up to 5 MB each. A loan can't be approved until these are on file.</p>
      <ul className="m-0 p-0 list-none flex flex-col">
        {KYC_KINDS.map((kind) => {
          const n = p.kyc.have[kind] ?? 0
          const needed = p.kyc.missing.includes(DOCUMENT_LABELS[kind])
          return (
            <li key={kind} className="flex justify-between items-center gap-3 py-3 border-t border-line">
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{DOCUMENT_LABELS[kind]}</span>
                {needed
                  ? <span className="text-[13px] text-danger">Needed</span>
                  : <span className="text-[13px] text-success">{n ? `${n} on file` : 'Not required'}</span>}
              </span>
              <UploadButton borrowerId={p.borrower.id} kind={kind} label={n ? 'Add' : 'Upload'} variant={needed ? 'secondary' : 'quiet'} />
            </li>
          )
        })}
        <li className="flex justify-between items-center gap-3 py-3 border-t border-line">
          <span className="text-[13px] text-ink-muted">Anything else (employer letter, payment proof)</span>
          <UploadButton borrowerId={p.borrower.id} kind="other" label="Upload" variant="quiet" />
        </li>
      </ul>
    </section>
  )
}

function Documents({ p }: { p: Profile }) {
  const size = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
  return (
    <section className="ml-card p-0 overflow-hidden" style={{ padding: 0 }}>
      <h2 className="ml-h2 px-6 py-4">Documents on file</h2>
      <DataTable rows={p.documents} empty="No documents yet. Upload them from the checklist."
        columns={[
          { key: 'kind', label: 'Document', render: (d) => DOCUMENT_LABELS[d.kind] },
          { key: 'file_name', label: 'File', render: (d) => <DownloadLink href={files.document(p.borrower.id, d.id)}>{d.file_name}</DownloadLink> },
          { key: 'uploaded_on', label: 'Uploaded', render: (d) => formatDate(d.uploaded_on) },
          { key: 'size', label: 'Size', align: 'right', render: (d) => size(d.size) },
        ]} />
    </section>
  )
}

function LoansTable({ p }: { p: Profile }) {
  const nav = useNavigate()
  return (
    <DataTable rows={p.loans} onRowClick={(l) => nav(`/staff/loans/${l.id}`)} empty="No loans yet."
      columns={[
        { key: 'ref', label: 'Loan', render: (l) => <span className="ml-ref">{l.ref}</span> },
        { key: 'product', label: 'Product' },
        { key: 'submitted_on', label: 'Applied', render: (l) => formatDate(l.submitted_on) },
        { key: 'state', label: 'Status', render: (l) => <StatusPill {...pillFor(l.state, l.days_overdue)} /> },
        { key: 'principal', label: 'Amount', align: 'right', render: (l) => <Money amount={l.principal} /> },
      ]} />
  )
}

function NewApplication({ borrowerId }: { borrowerId: number }) {
  const [amount, setAmount] = useState('')
  const [months, setMonths] = useState(12)
  const [purpose, setPurpose] = useState('')
  const [touched, setTouched] = useState(false)
  const nav = useNavigate()
  const qc = useQueryClient()
  const value = parseKina(amount)
  const amountError = value === null || Number(value) < 200 || Number(value) > 50000
    ? 'Enter an amount between K 200 and K 50,000.' : undefined
  const quote = useQuery({
    queryKey: ['quote', value, months], enabled: !amountError, queryFn: () => api.portal.quote(value!, months),
  })
  const apply = useMutation({
    mutationFn: () => api.staff.apply(borrowerId, { amount: value!, months, purpose: purpose.trim() }),
    onSuccess: (loan) => {
      qc.invalidateQueries({ queryKey: ['borrower', borrowerId] })
      qc.invalidateQueries({ queryKey: ['loans'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      nav(`/staff/loans/${loan.id}`)
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!amountError) apply.mutate()
  }
  return (
    <form className="ml-card flex flex-col gap-4" onSubmit={submit} noValidate aria-label="New loan application">
      <h2 className="ml-h2">New loan application</h2>
      <Field label="Amount (PGK)" prefix="K" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)}
        error={touched ? amountError : undefined} />
      <div className="flex flex-col gap-1.5">
        <span className="ml-label" id="app-term">Term</span>
        <div className="grid grid-cols-3 gap-2" role="group" aria-labelledby="app-term">
          {TERMS.map((m) => <button type="button" key={m} className="ml-chip" aria-pressed={m === months} onClick={() => setMonths(m)}>{m} mo</button>)}
        </div>
      </div>
      <Field label="Purpose" optional value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="School fees, house repairs…" />
      {quote.data && <p className="m-0 text-[13px]">About <strong>{formatKina(quote.data.monthly_payment)}</strong> a month at {Number(quote.data.annual_rate)}% a year. The affordability check runs when you save.</p>}
      {apply.error && <div className="ml-alert ml-alert-danger" role="alert">{(apply.error as Error).message}</div>}
      <Button type="submit" variant="primary" disabled={apply.isPending}>{apply.isPending ? 'Saving…' : 'Save application'}</Button>
    </form>
  )
}
