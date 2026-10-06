import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { DataTable, ErrorNote, Money, Skeleton, StatTile, StatusPill } from '../components'
import { formatKina, formatPercent, weekdayDate } from '../lib/format'

export function Dashboard() {
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: api.staff.dashboard })
  const pending = useQuery({ queryKey: ['loans', 'PENDING'], queryFn: () => api.staff.loans('PENDING') })
  const nav = useNavigate()

  if (dash.error) return <ErrorNote error={dash.error} retry={() => dash.refetch()} />
  const d = dash.data
  const maxBucket = d ? Math.max(...d.arrears_buckets.map((b) => Number(b.amount)), 1) : 1

  return (
    <>
      <header className="flex flex-wrap justify-between items-end gap-4">
        <div className="flex flex-col gap-1">
          <div className="ml-eyebrow">{d ? weekdayDate(d.as_of) : ' '}</div>
          <h1 className="ml-title">Portfolio today</h1>
        </div>
        <Link to="/staff/applications" className="ml-btn ml-btn-primary no-underline">Review applications</Link>
      </header>

      <section aria-label="Key figures" className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {!d ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={104} />) : (
          <>
            <StatTile label="Gross portfolio" value={formatKina(d.gross_portfolio)} hint="Principal outstanding on active loans" />
            <StatTile label="Active loans" value={String(d.active_loans)} hint={`${d.disbursed_this_month} disbursed this month`} />
            <StatTile label="Portfolio at risk over 30 days" value={formatPercent(d.par30_ratio)}
              delta={Number(d.par30_ratio) > 0.05 ? 'Above the 5% target' : 'Within the 5% target'}
              deltaTone={Number(d.par30_ratio) > 0.05 ? 'danger' : 'success'} />
            <StatTile label="Due today" value={formatKina(d.due_today_amount)} emphasis="gold"
              hint={`${d.due_today_count} installments · ${d.collected_today_count} collected`} />
          </>
        )}
      </section>

      <div className="flex flex-wrap gap-6 items-start">
        <section className="ml-card p-0 overflow-hidden" style={{ flex: '3 1 480px', minWidth: 0, padding: 0 }}>
          <div className="flex justify-between items-center px-6 py-4">
            <h2 className="ml-h2">Waiting for approval</h2>
            <Link to="/staff/applications" className="text-[13px] font-semibold no-underline">See all</Link>
          </div>
          {pending.isLoading ? <div className="p-6"><Skeleton h={160} /></div> : (
            <DataTable rows={pending.data?.slice(0, 5) ?? []} onRowClick={(r) => nav(`/staff/loans/${r.id}`)}
              empty="No applications are waiting."
              columns={[
                { key: 'ref', label: 'Loan', render: (r) => <span className="ml-ref">{r.ref}</span> },
                { key: 'borrower_name', label: 'Borrower', render: (r) => (
                  <>{r.borrower_name}<div className="text-[13px] text-ink-muted">{r.product} · {r.term_months} months</div></>) },
                { key: 'rec', label: 'Check', render: (r) => r.recommendation ? <StatusPill status={r.recommendation} /> : <span className="text-ink-muted text-[13px]">Not run</span> },
                { key: 'principal', label: 'Amount', align: 'right', render: (r) => <Money amount={r.principal} /> },
                { key: 'go', label: 'Action', align: 'right', render: (r) => <Link to={`/staff/loans/${r.id}`} className="font-semibold no-underline" onClick={(e) => e.stopPropagation()}>Review</Link> },
              ]} />
          )}
        </section>

        <section className="ml-card flex flex-col gap-4" style={{ flex: '2 1 320px', minWidth: 0 }}>
          <h2 className="ml-h2">Arrears by age</h2>
          {!d ? <Skeleton h={140} /> : (
            <>
              <p className="m-0 text-[13px] leading-[18px] text-ink-muted">
                Principal outstanding in arrears, {formatKina(d.arrears_total)} across {d.arrears_loans} loans.
              </p>
              <div className="flex flex-col gap-3">
                {d.arrears_buckets.map((b, i) => (
                  <div key={b.label} className="grid items-center gap-3 text-[13px]" style={{ gridTemplateColumns: '88px minmax(0,1fr) 110px' }}>
                    <span className="text-ink-muted font-medium">{b.label}</span>
                    <div className="h-3 rounded bg-surface-sunken">
                      <div className="h-3 rounded" style={{ width: `${(Number(b.amount) / maxBucket) * 100}%`, background: i === 0 ? 'var(--warning)' : 'var(--danger)' }} />
                    </div>
                    <span className="text-right font-semibold tabular-nums">{formatKina(b.amount)}</span>
                  </div>
                ))}
              </div>
              <Link to="/staff/repayments" className="text-[13px] font-semibold no-underline">Open collections list</Link>
            </>
          )}
        </section>
      </div>
    </>
  )
}
