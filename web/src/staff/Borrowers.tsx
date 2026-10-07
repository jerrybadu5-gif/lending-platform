import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { DataTable, ErrorNote, Skeleton } from '../components'

/** Wait until typing pauses, so each keystroke doesn't call the server (matters on slow connections). */
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function Borrowers() {
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const q = useDebounced(text.trim())
  const nav = useNavigate()
  useEffect(() => { setParams(q ? { q } : {}, { replace: true }) }, [q, setParams])
  const list = useQuery({ queryKey: ['borrowers', q], queryFn: () => api.staff.borrowers(q) })

  return (
    <>
      <header className="flex flex-wrap justify-between items-center gap-3">
        <h1 className="ml-title">Borrowers</h1>
        <Link to="/staff/borrowers/new" className="ml-btn ml-btn-primary no-underline">New borrower</Link>
      </header>
      <div className="ml-field" style={{ maxWidth: 480 }}>
        <label className="ml-label" htmlFor="borrower-search">Find a borrower</label>
        <input id="borrower-search" className="ml-input" type="search" value={text} autoFocus
          placeholder="Name, phone, NID number or employer" onChange={(e) => setText(e.target.value)} />
      </div>
      {list.error ? <ErrorNote error={list.error} retry={() => list.refetch()} /> : list.isLoading ? <Skeleton h={240} /> : (
        <DataTable rows={list.data ?? []} onRowClick={(r) => nav(`/staff/borrowers/${r.id}`)}
          empty={q ? <>No borrower matches “{q}”. <Link to="/staff/borrowers/new">Sign up a new borrower</Link></> : 'No borrowers yet.'}
          columns={[
            { key: 'name', label: 'Name', render: (r) => <Link to={`/staff/borrowers/${r.id}`}>{r.name}</Link> },
            { key: 'phone', label: 'Phone', render: (r) => r.phone ?? '—' },
            { key: 'national_id', label: 'NID number', render: (r) => <span className="ml-ref">{r.national_id ?? '—'}</span> },
            { key: 'employer', label: 'Employer', render: (r) => r.employer ?? '—' },
          ]} />
      )}
    </>
  )
}
