import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type LoanState, type LoanSummary, type ReviewStage } from '../api/client'
import { DataTable, ErrorNote, Money, Skeleton, StatusPill } from '../components'
import { formatDate } from '../lib/format'
import { pillFor } from '../lib/loan'
import { useMe } from '../lib/me'

type View = { key: string; label: string; state: LoanState; stages?: ReviewStage[]; empty: string }

// The loan officer prepares and sends applications up; the credit manager decides them.
const OFFICER_VIEWS: View[] = [
  { key: 'review', label: 'To review', state: 'PENDING', stages: ['DRAFT', 'RETURNED'], empty: 'Nothing waiting for your review.' },
  { key: 'sent', label: 'With the credit manager', state: 'PENDING', stages: ['SUBMITTED'], empty: 'Nothing waiting for a decision.' },
  { key: 'approved', label: 'Approved, not paid out', state: 'APPROVED', empty: 'No approved loans waiting for pay-out.' },
  { key: 'rejected', label: 'Rejected', state: 'REJECTED', empty: 'No rejected applications.' },
]
const MANAGER_VIEWS: View[] = [
  { key: 'decide', label: 'Waiting for your decision', state: 'PENDING', stages: ['SUBMITTED'], empty: 'Nothing waiting for a decision.' },
  { key: 'officers', label: 'With loan officers', state: 'PENDING', stages: ['DRAFT', 'RETURNED'], empty: 'No applications being prepared.' },
  { key: 'approved', label: 'Approved, not paid out', state: 'APPROVED', empty: 'No approved loans waiting for pay-out.' },
  { key: 'rejected', label: 'Rejected', state: 'REJECTED', empty: 'No rejected applications.' },
]

export function stageLabel(l: LoanSummary): { text: string; tone: 'muted' | 'warning' | 'brand' } | null {
  if (l.state !== 'PENDING' || !l.review_stage) return null
  if (l.review_stage === 'SUBMITTED') return { text: 'Sent for approval', tone: 'brand' }
  if (l.review_stage === 'RETURNED') return { text: 'Sent back', tone: 'warning' }
  return { text: 'Being reviewed', tone: 'muted' }
}

export function Applications() {
  const { isApprover, loading } = useMe()
  const views = isApprover ? MANAGER_VIEWS : OFFICER_VIEWS
  const [key, setKey] = useState<string | null>(null)
  const view = views.find((v) => v.key === key) ?? views[0]
  const q = useQuery({ queryKey: ['loans', view.state], queryFn: () => api.staff.loans(view.state), enabled: !loading })
  const pending = useQuery({ queryKey: ['loans', 'PENDING'], queryFn: () => api.staff.loans('PENDING'), enabled: !loading })
  const nav = useNavigate()
  const keep = (l: LoanSummary) => !view.stages || view.stages.includes(l.review_stage ?? 'DRAFT')
  const rows = (q.data ?? []).filter(keep)
  const count = (v: View) => (v.stages ? (pending.data ?? []).filter((l) => v.stages!.includes(l.review_stage ?? 'DRAFT')).length : undefined)

  return (
    <>
      <h1 className="ml-title">Loan applications</h1>
      <div role="tablist" aria-label="Applications" className="flex flex-wrap gap-1 border-b border-line pb-2">
        {views.map((v) => {
          const n = count(v)
          return (
            <button key={v.key} role="tab" aria-selected={view.key === v.key}
              className={`ml-btn ml-btn-sm ${view.key === v.key ? '' : 'ml-btn-quiet'}`} onClick={() => setKey(v.key)}>
              {v.label}{n !== undefined ? ` (${n})` : ''}
            </button>
          )
        })}
      </div>
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : q.isLoading || loading ? <Skeleton h={240} /> : (
        <DataTable rows={rows} onRowClick={(r) => nav(`/staff/loans/${r.id}`)} empty={view.empty}
          columns={[
            { key: 'ref', label: 'Loan', render: (r) => <span className="ml-ref">{r.ref}</span> },
            { key: 'borrower_name', label: 'Borrower', render: (r) => <>{r.borrower_name}<div className="text-[13px] text-ink-muted">{r.product}</div></> },
            { key: 'submitted_on', label: 'Applied', render: (r) => formatDate(r.submitted_on) },
            { key: 'status', label: 'Status', render: (r) => {
              const stage = stageLabel(r)
              return (
                <span className="flex flex-col items-start gap-1">
                  {r.recommendation && r.state === 'PENDING' ? <StatusPill status={r.recommendation} /> : <StatusPill {...pillFor(r.state, r.days_overdue)} />}
                  {stage && <span className={`text-[12px] ${stage.tone === 'warning' ? 'text-warning' : stage.tone === 'brand' ? 'text-brand' : 'text-ink-muted'}`}>{stage.text}</span>}
                </span>
              )
            } },
            { key: 'term', label: 'Term', align: 'right', render: (r) => `${r.term_months} mo` },
            { key: 'principal', label: 'Amount', align: 'right', render: (r) => <Money amount={r.principal} /> },
          ]} />
      )}
    </>
  )
}
