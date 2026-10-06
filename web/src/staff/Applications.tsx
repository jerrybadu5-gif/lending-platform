import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type LoanState } from '../api/client'
import { DataTable, ErrorNote, Money, Skeleton, StatusPill } from '../components'
import { formatDate } from '../lib/format'
import { pillFor } from '../lib/loan'

const VIEWS: { state: LoanState; label: string }[] = [
  { state: 'PENDING', label: 'Pending approval' },
  { state: 'APPROVED', label: 'Approved, not disbursed' },
  { state: 'REJECTED', label: 'Rejected' },
]

export function Applications() {
  const [view, setView] = useState<LoanState>('PENDING')
  const q = useQuery({ queryKey: ['loans', view], queryFn: () => api.staff.loans(view) })
  const nav = useNavigate()
  return (
    <>
      <h1 className="ml-title">Loan applications</h1>
      <div role="tablist" aria-label="Applications" className="flex flex-wrap gap-1 border-b border-line pb-2">
        {VIEWS.map((v) => (
          <button key={v.state} role="tab" aria-selected={view === v.state}
            className={`ml-btn ml-btn-sm ${view === v.state ? '' : 'ml-btn-quiet'}`} onClick={() => setView(v.state)}>{v.label}</button>
        ))}
      </div>
      {q.error ? <ErrorNote error={q.error} retry={() => q.refetch()} /> : q.isLoading ? <Skeleton h={240} /> : (
        <DataTable rows={q.data ?? []} onRowClick={(r) => nav(`/staff/loans/${r.id}`)} empty="No loans in this list."
          columns={[
            { key: 'ref', label: 'Loan', render: (r) => <span className="ml-ref">{r.ref}</span> },
            { key: 'borrower_name', label: 'Borrower', render: (r) => <>{r.borrower_name}<div className="text-[13px] text-ink-muted">{r.product}</div></> },
            { key: 'submitted_on', label: 'Submitted', render: (r) => formatDate(r.submitted_on) },
            { key: 'status', label: 'Status', render: (r) => r.recommendation && view === 'PENDING'
              ? <StatusPill status={r.recommendation} /> : <StatusPill {...pillFor(r.state, r.days_overdue)} /> },
            { key: 'term', label: 'Term', align: 'right', render: (r) => `${r.term_months} mo` },
            { key: 'principal', label: 'Amount', align: 'right', render: (r) => <Money amount={r.principal} /> },
          ]} />
      )}
    </>
  )
}
