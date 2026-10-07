import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

// Same list as the API (app/routers/staff.py); the API is what enforces it.
const APPROVER_ROLES = ['credit manager', 'super user', 'branch manager']

export function isApproverRole(roles: string[]): boolean {
  return roles.some((r) => APPROVER_ROLES.includes(r.toLowerCase()))
}

/** The signed-in staff member, and whether they decide loans (credit manager) or prepare them (loan officer). */
export function useMe() {
  const q = useQuery({ queryKey: ['me'], queryFn: api.staff.me, staleTime: 5 * 60_000 })
  return { me: q.data, isApprover: isApproverRole(q.data?.roles ?? []), loading: q.isLoading }
}
