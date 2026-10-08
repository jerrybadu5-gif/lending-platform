import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, DOCUMENT_LABELS, files, type ActionResult, type LoanDetail, type OfficerAdvice } from '../api/client'
import { Button, Field, Skeleton } from '../components'
import { FilePreview } from '../components/DocumentViewer'
import { DownloadLink } from '../components/DownloadLink'
import { formatDate, formatKina, parseKina } from '../lib/format'

const KYC_ORDER = ['id', 'payslip', 'bank_statement', 'deduction_authority', 'other']

export function useLoanRefresh(loanId: number) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['loan', loanId] })
    qc.invalidateQueries({ queryKey: ['payout', loanId] })
    qc.invalidateQueries({ queryKey: ['loans'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
}

function NoteBox({ id, label, value, onChange, placeholder, error }:
  { id: string; label: string; value: string; onChange: (v: string) => void; placeholder: string; error?: string }) {
  return (
    <div className="ml-field">
      <label className="ml-label" htmlFor={id}>{label}</label>
      <textarea id={id} className="ml-input" style={{ height: 96, padding: '10px 12px' }} value={value} maxLength={1000}
        aria-invalid={!!error || undefined} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      {error && <span className="text-[13px] text-danger">{error}</span>}
    </div>
  )
}

/** Loan officer: check the documents and the affordability check, then send it up with a recommendation. */
export function OfficerReview({ loan, suggested }: { loan: LoanDetail; suggested: string }) {
  const refresh = useLoanRefresh(loan.id)
  const qc = useQueryClient()
  const kyc = useQuery({ queryKey: ['kyc', loan.borrower.id], queryFn: () => api.staff.kyc(loan.borrower.id) })
  const [advice, setAdvice] = useState<OfficerAdvice>(loan.assessment?.recommendation === 'DECLINE' ? 'DECLINE' : 'APPROVE')
  const [amount, setAmount] = useState(suggested)
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)
  const send = useMutation({
    mutationFn: () => api.staff.submit(loan.id, { recommendation: advice, amount: advice === 'APPROVE' ? parseKina(amount) : null, note: note.trim() }),
    onSuccess: (d) => { qc.setQueryData(['loan', loan.id], d); refresh() },
  })
  const review = loan.review
  const missing = kyc.data && !kyc.data.complete ? kyc.data.missing : []
  const noteError = note.trim().length < 10 ? 'Write what you checked and why (at least a sentence).' : undefined
  const amountError = advice === 'APPROVE' && parseKina(amount) === null ? 'Enter an amount like 13,000.00' : undefined
  // The application goes up only with every document on file (the API checks too).
  const checking = !kyc.data && !kyc.error
  const blocked = checking || missing.length > 0

  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!noteError && !amountError && !blocked) send.mutate()
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={submit} noValidate aria-label="Loan officer review">
      {review?.stage === 'RETURNED' && (
        <div className="ml-alert ml-alert-warning flex flex-col gap-1" role="note">
          <strong>Sent back by {review.returned_by ?? 'the credit manager'}{review.returned_on ? ` on ${formatDate(review.returned_on)}` : ''}</strong>
          <span>{review.returned_note}</span>
        </div>
      )}
      {missing.length > 0 && (
        <div className="ml-alert ml-alert-warning flex flex-col gap-1" role="note">
          <strong>Documents still needed</strong>
          <ul className="m-0 pl-[18px]">{missing.map((m) => <li key={m}>{m}</li>)}</ul>
          <Link to={`/staff/borrowers/${loan.borrower.id}`}>Upload them on the borrower's profile</Link>
        </div>
      )}
      <fieldset className="border-0 m-0 p-0 flex flex-col gap-2">
        <legend className="ml-label mb-2">Your recommendation</legend>
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className="ml-chip" aria-pressed={advice === 'APPROVE'} onClick={() => setAdvice('APPROVE')}>Approve</button>
          <button type="button" className="ml-chip" aria-pressed={advice === 'DECLINE'} onClick={() => setAdvice('DECLINE')}>Decline</button>
        </div>
      </fieldset>
      {advice === 'APPROVE' && (
        <Field label="Recommended amount (PGK)" prefix="K" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)}
          error={touched ? amountError : undefined}
          hint={loan.assessment ? `Applied for ${formatKina(loan.principal)}. Policy capacity ${formatKina(loan.assessment.max_recommended_principal)}.` : `Applied for ${formatKina(loan.principal)}.`} />
      )}
      <NoteBox id="officer-note" label="Your assessment" value={note} onChange={setNote} error={touched ? noteError : undefined}
        placeholder="What you checked: ID matches, payslips and bank statement agree, employer confirmed, purpose…" />
      {send.error && <div className="ml-alert ml-alert-danger" role="alert">{(send.error as Error).message}</div>}
      <Button type="submit" variant="primary" disabled={send.isPending || blocked}>{send.isPending ? 'Sending…' : 'Send to credit manager'}</Button>
      {missing.length > 0 && <span className="text-[13px] text-ink-muted">Upload the missing documents first; the credit manager reviews them with your recommendation.</span>}
    </form>
  )
}

/** What the loan officer found and recommended, for the credit manager. */
export function OfficerSummary({ loan }: { loan: LoanDetail }) {
  const r = loan.review
  if (!r || r.stage !== 'SUBMITTED') return null
  return (
    <div className="flex flex-col gap-2 p-4 rounded-md bg-surface-sunken">
      <div className="flex flex-wrap justify-between gap-2">
        <strong>Loan officer recommends {r.officer_recommendation === 'APPROVE' ? `approving ${formatKina(r.officer_amount)}` : 'declining'}</strong>
        <span className="text-[13px] text-ink-muted">{r.submitted_by}{r.submitted_on ? ` · ${formatDate(r.submitted_on)}` : ''}</span>
      </div>
      {r.officer_note && <p className="m-0 text-[13px] leading-[18px] whitespace-pre-wrap">{r.officer_note}</p>}
      {r.returned_note && <p className="m-0 text-[12px] text-ink-muted">Earlier sent back: {r.returned_note}</p>}
    </div>
  )
}

/** Credit manager, the final say: approve, reject, or send back to the loan officer with a note. */
export function ManagerDecision({ loan, suggested, onDone, username, reviewRequired = true, allowSelfApproval = false }:
  { loan: LoanDetail; suggested: string; onDone: (r: ActionResult) => void; username?: string; reviewRequired?: boolean; allowSelfApproval?: boolean }) {
  const qc = useQueryClient()
  const stage = loan.review?.stage ?? 'DRAFT'
  const submitted = stage === 'SUBMITTED'
  // Approval waits for the officer's review (MCL_REVIEW_REQUIRED); rejecting or sending back doesn't.
  const waiting = reviewRequired && !submitted
  const own = reviewRequired && !allowSelfApproval && submitted && !!username && loan.review?.submitted_user === username
  const refresh = useLoanRefresh(loan.id)
  const officerAmount = loan.review?.officer_amount ? formatKina(loan.review.officer_amount, { currency: false }) : null
  const [amount, setAmount] = useState(officerAmount ?? suggested)
  const [note, setNote] = useState('')
  const [confirm, setConfirm] = useState<'reject' | 'return' | null>(null)
  const approve = useMutation({ mutationFn: () => api.staff.approve(loan.id, parseKina(amount) ?? '', note), onSuccess: onDone })
  const reject = useMutation({ mutationFn: () => api.staff.reject(loan.id, note), onSuccess: onDone })
  const back = useMutation({
    mutationFn: () => api.staff.sendBack(loan.id, note.trim()),
    onSuccess: (d) => { qc.setQueryData(['loan', loan.id], d); refresh(); onDone({ loan_id: loan.id, state: 'PENDING', message: 'Sent to the loan officer with your note.' }) },
  })
  const error = approve.error ?? reject.error ?? back.error
  const amountError = parseKina(amount) === null ? 'Enter an amount like 13,000.00' : undefined
  const needNote = note.trim().length < 3

  return (
    <div className="flex flex-col gap-4">
      <OfficerSummary loan={loan} />
      {stage === 'DRAFT' && (
        <div className="ml-alert ml-alert-warning" role="note">
          The loan officer hasn't sent his review yet.{waiting ? ' You can approve once he has; you can reject it now, or send it to him with a note.' : ''}
        </div>
      )}
      {stage === 'RETURNED' && loan.review && (
        <div className="ml-alert ml-alert-warning flex flex-col gap-1" role="note">
          <strong>With the loan officer: sent back{loan.review.returned_by ? ` by ${loan.review.returned_by}` : ''}{loan.review.returned_on ? ` on ${formatDate(loan.review.returned_on)}` : ''}</strong>
          <span>{loan.review.returned_note}</span>
        </div>
      )}
      {error && <div className="ml-alert ml-alert-danger" role="alert">{(error as Error).message}</div>}
      {own && <div className="ml-alert ml-alert-warning" role="note">You sent this application up yourself, so another credit manager must approve it. You can still send it back or reject it.</div>}
      {!confirm && (
        <>
          <Field label="Approved amount (PGK)" prefix="K" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} error={amountError}
            hint={loan.assessment ? `Policy capacity is ${formatKina(loan.assessment.max_recommended_principal)} for this client.` : undefined} />
          <NoteBox id="decision-note" label="Note for the file" value={note} onChange={setNote}
            placeholder="Why this decision, for the next person who reads the file" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" disabled={!!amountError || approve.isPending || own || waiting} onClick={() => approve.mutate()}>
              Approve {parseKina(amount) ? formatKina(parseKina(amount)) : ''}
            </Button>
            <Button variant="danger" onClick={() => setConfirm('reject')}>Reject</Button>
            <Button variant="quiet" onClick={() => setConfirm('return')}>{submitted ? 'Send back' : 'Note to loan officer'}</Button>
          </div>
        </>
      )}
      {confirm === 'reject' && (
        <div className="flex flex-col gap-3 p-4 rounded-md bg-danger-soft">
          <strong className="text-danger">Reject this application?</strong>
          <span className="text-[13px] leading-[18px]">The borrower is told by SMS and the loan moves to Rejected. This can't be undone.</span>
          {needNote && <span className="text-[13px] font-medium text-danger">Add a note saying why before you reject.</span>}
          <div className="flex flex-wrap gap-3">
            <Button variant="danger" disabled={needNote || reject.isPending} onClick={() => reject.mutate()}>Reject application</Button>
            <Button variant="quiet" onClick={() => setConfirm(null)}>Keep reviewing</Button>
          </div>
        </div>
      )}
      {confirm === 'return' && (
        <div className="flex flex-col gap-3 p-4 rounded-md bg-surface-sunken">
          <strong>{submitted ? 'Send back to the loan officer?' : 'Send a note to the loan officer?'}</strong>
          <span className="text-[13px] leading-[18px]">It goes to his "To review" list with your note, and comes back to you when he sends it up again.</span>
          <NoteBox id="return-note" label="What needs doing" value={note} onChange={setNote}
            placeholder="e.g. The payslip is from June; get the latest three." />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" disabled={needNote || back.isPending} onClick={() => back.mutate()}>Send to loan officer</Button>
            <Button variant="quiet" onClick={() => setConfirm(null)}>Keep reviewing</Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** The borrower's documents, shown in the page so the reviewer needn't download each one. */
export function ReviewDocuments({ borrowerId }: { borrowerId: number }) {
  const q = useQuery({ queryKey: ['borrower', borrowerId], queryFn: () => api.staff.borrower(borrowerId) })
  const [picked, setPicked] = useState<number | null>(null)
  if (!q.data) return q.error ? null : <Skeleton h={120} />
  const docs = [...q.data.documents].sort((a, b) => KYC_ORDER.indexOf(a.kind) - KYC_ORDER.indexOf(b.kind))
  const doc = docs.find((d) => d.id === picked) ?? docs[0]
  return (
    <section className="ml-card flex flex-col gap-3" aria-label="Documents to review">
      <div className="flex flex-wrap justify-between items-center gap-3">
        <h2 className="ml-h2">Documents</h2>
        <Link to={`/staff/borrowers/${borrowerId}`} className="text-[13px]">Borrower's profile</Link>
      </div>
      {!doc ? <p className="m-0 text-ink-muted">No documents on file.</p> : (
        <>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Document">
            {docs.map((d) => (
              <button key={d.id} role="tab" aria-selected={d.id === doc.id} className={`ml-btn ml-btn-sm ${d.id === doc.id ? '' : 'ml-btn-quiet'}`}
                onClick={() => setPicked(d.id)} title={d.file_name}>
                {(DOCUMENT_LABELS[d.kind] ?? d.kind).split(' (')[0]}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap justify-between gap-2 text-[13px] text-ink-muted">
            <span className="break-all">{doc.file_name}{doc.uploaded_on ? ` · uploaded ${formatDate(doc.uploaded_on)}` : ''}</span>
            <DownloadLink href={files.document(borrowerId, doc.id)}>Download</DownloadLink>
          </div>
          <FilePreview key={doc.id} href={files.document(borrowerId, doc.id)} contentType={doc.content_type} title={`${DOCUMENT_LABELS[doc.kind]}: ${doc.file_name}`} height={460} />
        </>
      )}
    </section>
  )
}
