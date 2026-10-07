import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api, files, type ActionResult, type LoanDetail, type PayoutMethod } from '../api/client'
import { Button, ErrorNote, Field, Skeleton } from '../components'
import { DownloadLink } from '../components/DownloadLink'
import { formatDate, formatKina } from '../lib/format'

const METHODS: { id: PayoutMethod; label: string; ref: string; refHint: string }[] = [
  { id: 'bank', label: 'Bank transfer', ref: 'Bank transfer reference', refHint: 'e.g. TT-0012345' },
  { id: 'mobile', label: 'Mobile money', ref: 'Mobile money transaction ID', refHint: 'e.g. CM8841203377' },
  { id: 'cash', label: 'Cash', ref: 'Cash voucher number', refHint: 'e.g. CV-0091' },
]
const ACCEPT = 'application/pdf,image/jpeg,image/png'

export function usePayout(loan: LoanDetail) {
  return useQuery({
    queryKey: ['payout', loan.id], queryFn: () => api.staff.payout(loan.id), enabled: loan.state === 'APPROVED',
  })
}

/** The pay-out steps for an approved loan: agreement, tell the borrower, signed copy, pay out. */
export function PayoutSteps({ loan, onDone }: { loan: LoanDetail; onDone: (r: ActionResult) => void }) {
  const q = usePayout(loan)
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['payout', loan.id] })
    qc.invalidateQueries({ queryKey: ['loan', loan.id] })
  }
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <Skeleton h={240} />
  const p = q.data
  const told = p.told_done
  const signed = !!p.signed_agreement

  return (
    <ol className="m-0 p-0 list-none flex flex-col" aria-label="Steps to pay out">
      <Step n={1} done title="Print the loan agreement" >
        <p className="m-0 text-[13px] text-ink-muted">Approved for {formatKina(loan.principal)}. Print two copies: one for the borrower, one to keep.</p>
        <DownloadLink href={files.agreement(loan.id)} className="ml-btn ml-btn-sm self-start no-underline">Loan agreement (PDF)</DownloadLink>
      </Step>

      <Step n={2} done={told} title="Ask the borrower to come in and sign">
        {p.borrower_told.length > 0
          ? <ul className="m-0 pl-[18px] text-[13px] flex flex-col gap-1">
              {p.borrower_told.map((e, i) => <li key={i}>{formatDate(e.when)} · {e.text}{e.who && <span className="text-ink-muted"> · {e.who}</span>}</li>)}
            </ul>
          : <p className="m-0 text-[13px] text-ink-muted">No contact recorded yet. If the loan was approved by a second approver or in Mifos X, no SMS has gone: send it now.</p>}
        {!p.sms_delivers && <p className="m-0 text-[13px] text-warning">No SMS provider is set up yet, so texts don't reach the borrower. Phone them and log the call.</p>}
        <Contact loan={loan} phone={p.phone} smsDelivers={p.sms_delivers} onSaved={refresh} />
      </Step>

      <Step n={3} done={signed} title="Upload the signed agreement">
        {p.signed_agreement
          ? <p className="m-0 text-[13px]">Signed copy on file: <DownloadLink href={files.loanDocument(loan.id, p.signed_agreement.id)}>{p.signed_agreement.file_name}</DownloadLink> · {formatDate(p.signed_agreement.uploaded_on)}</p>
          : <p className="m-0 text-[13px] text-ink-muted">Scan or photograph every signed page (one PDF is best). The loan can't be paid out without it.</p>}
        <UploadSigned loanId={loan.id} again={signed} onSaved={refresh} />
      </Step>

      <Step n={4} done={false} title="Pay out and record it" last>
        {p.ready
          ? <PayOut loan={loan} account={p.bank?.account_number ?? ''} phone={p.phone ?? ''} bank={p.bank ? `${p.bank.bank}${p.bank.branch ? `, ${p.bank.branch}` : ''} · ${p.bank.account_name}` : null} onDone={onDone} />
          : <p className="m-0 text-[13px] text-ink-muted">{p.missing.join(' ') || 'Not ready yet.'}</p>}
      </Step>
    </ol>
  )
}

function Step({ n, title, done, last, children }: { n: number; title: string; done: boolean; last?: boolean; children: ReactNode }) {
  return (
    <li className={`flex gap-3 py-3 ${last ? '' : 'border-b border-line'}`}>
      <span aria-hidden="true" className={`shrink-0 w-6 h-6 rounded-full grid place-items-center text-[12px] font-semibold ${done ? 'bg-brand text-on-brand' : 'bg-surface-sunken text-ink-muted'}`}>{done ? '✓' : n}</span>
      <div className="flex flex-col gap-2 min-w-0 flex-1">
        <span className="font-semibold">{title}{done && <span className="sr-only"> (done)</span>}</span>
        {children}
      </div>
    </li>
  )
}

function Contact({ loan, phone, smsDelivers, onSaved }: { loan: LoanDetail; phone: string | null; smsDelivers: boolean; onSaved: () => void }) {
  const [note, setNote] = useState('')
  const [calling, setCalling] = useState(false)
  const sms = useMutation({ mutationFn: () => api.staff.contact(loan.id, 'sms'), onSuccess: onSaved })
  const call = useMutation({
    mutationFn: () => api.staff.contact(loan.id, 'phone', note.trim()),
    onSuccess: () => { setNote(''); setCalling(false); onSaved() },
  })
  const error = sms.error ?? call.error
  return (
    <div className="flex flex-col gap-2">
      {!calling && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={smsDelivers ? 'secondary' : 'quiet'} disabled={!phone || sms.isPending} onClick={() => sms.mutate()}>{sms.isPending ? 'Sending…' : 'Send SMS again'}</Button>
          <Button size="sm" variant={smsDelivers ? 'quiet' : 'secondary'} onClick={() => setCalling(true)}>Log a phone call</Button>
        </div>
      )}
      {calling && (
        <form className="flex flex-col gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); call.mutate() }}>
          <Field label="What was agreed?" optional value={note} onChange={(e) => setNote(e.target.value)} placeholder="Coming Friday 10am to sign" maxLength={300} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" variant="primary" disabled={call.isPending}>Save call</Button>
            <Button size="sm" variant="quiet" onClick={() => setCalling(false)}>Cancel</Button>
          </div>
        </form>
      )}
      {!phone && <span className="text-[12px] text-ink-muted">No phone number on file. Add one on the borrower's profile.</span>}
      {error && <span className="text-[12px] text-danger" role="alert">{(error as Error).message}</span>}
    </div>
  )
}

function UploadSigned({ loanId, again, onSaved }: { loanId: number; again: boolean; onSaved: () => void }) {
  const input = useRef<HTMLInputElement>(null)
  const up = useMutation({ mutationFn: (f: File) => api.staff.uploadSigned(loanId, f), onSuccess: onSaved })
  return (
    <div className="flex flex-col gap-1 items-start">
      <input ref={input} type="file" accept={ACCEPT} hidden data-testid="upload-signed-agreement" aria-label="Signed agreement: choose file"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = '' }} />
      <Button size="sm" variant={again ? 'quiet' : 'secondary'} disabled={up.isPending} onClick={() => input.current?.click()}>
        {up.isPending ? 'Uploading…' : again ? 'Replace signed copy' : 'Upload signed agreement'}
      </Button>
      {up.error && <span className="text-[12px] text-danger" role="alert">{(up.error as Error).message}</span>}
    </div>
  )
}

function PayOut({ loan, account, phone, bank, onDone }:
  { loan: LoanDetail; account: string; phone: string; bank: string | null; onDone: (r: ActionResult) => void }) {
  const [method, setMethod] = useState<PayoutMethod>('bank')
  const [to, setTo] = useState(account)
  // Each method fills in its own destination, so a bank account number is never recorded as a wallet.
  const choose = (next: PayoutMethod) => {
    setMethod(next)
    setTo(next === 'bank' ? account : next === 'mobile' ? phone : '')
  }
  const [reference, setReference] = useState('')
  const [touched, setTouched] = useState(false)
  const m = METHODS.find((x) => x.id === method)!
  const pay = useMutation({
    mutationFn: () => api.staff.disburse(loan.id, { method, reference: reference.trim(), account: method === 'cash' ? null : to.trim() || null }),
    onSuccess: onDone,
  })
  const refError = reference.trim().length < 2 ? 'Enter the reference so the payment can be traced.' : undefined
  const toError = method === 'bank' && to.trim().length < 4 ? "Enter the borrower's account number." : undefined
  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!refError && !toError) pay.mutate()
  }
  return (
    <form className="flex flex-col gap-3" onSubmit={submit} noValidate aria-label="Record disbursement">
      <p className="m-0 text-[13px]">Pay <strong>{formatKina(loan.principal)}</strong> to {loan.borrower.name}, then record it here.</p>
      <div className="grid grid-cols-3 gap-2" role="group" aria-label="Paid by">
        {METHODS.map((x) => <button type="button" key={x.id} className="ml-chip" aria-pressed={x.id === method} onClick={() => choose(x.id)}>{x.label}</button>)}
      </div>
      {method !== 'cash' && (
        <Field label={method === 'bank' ? 'Paid into account number' : 'Mobile money number'} value={to} onChange={(e) => setTo(e.target.value)}
          hint={method === 'bank' && bank ? bank : undefined} error={touched ? toError : undefined} />
      )}
      <Field label={m.ref} placeholder={m.refHint} value={reference} onChange={(e) => setReference(e.target.value)} error={touched ? refError : undefined} />
      {pay.error && <div className="ml-alert ml-alert-danger" role="alert">{(pay.error as Error).message}</div>}
      <Button type="submit" variant="primary" disabled={pay.isPending}>{pay.isPending ? 'Saving…' : 'Record disbursement'}</Button>
    </form>
  )
}
