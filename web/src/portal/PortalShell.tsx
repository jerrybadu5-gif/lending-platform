import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

const Svg = ({ children }: { children: ReactNode }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)

/** Phone-width frame with the borrower tab bar. */
export function PortalShell({ children, tabs = true }: { children: ReactNode; tabs?: boolean }) {
  return (
    <div className="min-h-screen bg-surface flex justify-center">
      <div className="w-full flex flex-col min-h-screen" style={{ maxWidth: 480 }}>
        <div className="flex-1 flex flex-col gap-4 px-4 py-6">{children}</div>
        {tabs && (
          <nav aria-label="Borrower" className="sticky bottom-0 flex border-t border-line bg-surface-raised px-2 py-1"
            style={{ paddingBottom: 'calc(4px + env(safe-area-inset-bottom, 0px))' }}>
            <NavLink to="/portal" end className={({ isActive }) => `ml-tab${isActive ? ' active' : ''}`}><Svg><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /></Svg>Home</NavLink>
            <NavLink to="/portal/apply" className={({ isActive }) => `ml-tab${isActive ? ' active' : ''}`}><Svg><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" /></Svg>Apply</NavLink>
          </nav>
        )}
      </div>
    </div>
  )
}
