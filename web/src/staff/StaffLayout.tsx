import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Button, Skeleton } from '../components'

const icon = (d: string) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: d }} />
)
const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  apps: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h5"/>',
  repay: '<rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/>',
}

export function StaffLayout() {
  const me = useQuery({ queryKey: ['me'], queryFn: api.staff.me, staleTime: 5 * 60_000 })
  const dash = useQuery({ queryKey: ['dashboard'], queryFn: api.staff.dashboard, enabled: me.isSuccess })
  const qc = useQueryClient()
  const nav = useNavigate()
  const loc = useLocation()

  if (me.error instanceof ApiError && me.error.status === 401) {
    return <Navigate to="/staff/login" replace state={{ from: loc.pathname }} />
  }
  if (!me.data) return <div className="p-8"><Skeleton h={200} /></div>

  async function signOut() {
    await api.staff.logout()
    qc.clear()
    nav('/staff/login')
  }

  return (
    <div className="flex flex-wrap min-h-screen bg-surface">
      <aside className="flex flex-col gap-6 px-4 py-6 bg-surface-sunken border-r border-line" style={{ flex: '1 1 232px', maxWidth: 260 }}>
        <div className="px-3">
          <div className="font-display text-[22px] leading-[26px] font-semibold text-brand-deep">McLender</div>
          <div className="text-[13px] leading-[18px] font-medium text-ink-muted">Breez Lending</div>
        </div>
        <nav className="ml-nav flex flex-col gap-1" aria-label="Main">
          <NavLink to="/staff" end>{icon(ICONS.dashboard)}Dashboard</NavLink>
          <NavLink to="/staff/applications">{icon(ICONS.apps)}Applications
            {dash.data && dash.data.pending_count > 0 && <span className="ml-pill ml-pill-info ml-auto">{dash.data.pending_count}</span>}
          </NavLink>
          <NavLink to="/staff/repayments">{icon(ICONS.repay)}Repayments</NavLink>
        </nav>
        <div className="mt-auto px-3 flex flex-col gap-2 text-[13px] leading-[18px] text-ink-muted">
          <span>{me.data.display_name}<br />{me.data.roles.join(', ')}</span>
          <Button size="sm" variant="quiet" className="self-start" onClick={signOut}>Sign out</Button>
        </div>
      </aside>
      <main className="flex flex-col gap-6 p-8 box-border" style={{ flex: '999 1 560px', minWidth: 0, maxWidth: 1200 }}>
        <Outlet />
      </main>
    </div>
  )
}
