import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { StaffLayout } from './staff/StaffLayout'
import { StaffLogin } from './staff/StaffLogin'
import { Dashboard } from './staff/Dashboard'
import { Applications } from './staff/Applications'
import { LoanReview } from './staff/LoanReview'
import { Repayments } from './staff/Repayments'
import { Borrowers } from './staff/Borrowers'
import { EditBorrower, NewBorrower } from './staff/BorrowerForm'
import { BorrowerProfile } from './staff/BorrowerProfile'
import { Skeleton } from './components'

// The borrower portal is a separate bundle so phones on slow networks don't download the staff app.
const PortalLogin = lazy(() => import('./portal/PortalLogin'))
const PortalHome = lazy(() => import('./portal/PortalHome'))
const PortalApply = lazy(() => import('./portal/PortalApply'))

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/staff" replace />} />
      <Route path="/staff/login" element={<StaffLogin />} />
      <Route path="/staff" element={<StaffLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="applications" element={<Applications />} />
        <Route path="loans/:id" element={<LoanReview />} />
        <Route path="repayments" element={<Repayments />} />
        <Route path="borrowers" element={<Borrowers />} />
        <Route path="borrowers/new" element={<NewBorrower />} />
        <Route path="borrowers/:id" element={<BorrowerProfile />} />
        <Route path="borrowers/:id/edit" element={<EditBorrower />} />
      </Route>
      <Route path="/portal/*" element={
        <Suspense fallback={<div className="p-4"><Skeleton h={120} /></div>}>
          <Routes>
            <Route path="login" element={<PortalLogin />} />
            <Route index element={<PortalHome />} />
            <Route path="apply" element={<PortalApply />} />
          </Routes>
        </Suspense>
      } />
      <Route path="*" element={<div className="p-8"><h1 className="ml-title">Page not found</h1><p><a href="/staff">Go to McLender</a></p></div>} />
    </Routes>
  )
}
