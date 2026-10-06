import type { LoanState } from '../api/client'
import type { PillStatus } from '../components'

/** Where a loan is on the LoanStepper (Submitted, Assessed, Approved, Disbursed, Repaying, Closed). */
export function stepFor(state: LoanState, assessed: boolean): number {
  switch (state) {
    case 'PENDING': return assessed ? 1 : 0
    case 'APPROVED': return 2
    case 'ACTIVE': case 'ARREARS': case 'ARREARS_LATE': return 4
    case 'CLOSED': return 6
    default: return 0
  }
}

export function pillFor(state: LoanState, daysOverdue = 0): { status: PillStatus; days?: number } {
  if (state === 'ARREARS' || state === 'ARREARS_LATE') return { status: state, days: daysOverdue }
  return { status: state as PillStatus }
}
