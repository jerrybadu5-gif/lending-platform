// Typed client for the McLender API. Money arrives as decimal strings ("1318.74"); keep it a string
// until it is shown (formatKina), so no rounding happens in the browser.

export type Money = string
export type LoanState =
  | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ACTIVE' | 'ARREARS' | 'ARREARS_LATE' | 'CLOSED' | 'WRITTEN_OFF' | 'WITHDRAWN'
export type Recommendation = 'APPROVE' | 'REFER' | 'DECLINE'
export type PaymentMethod = 'cash' | 'bank' | 'mobile' | 'payroll'

export interface StaffUser { username: string; display_name: string; roles: string[] }
export interface Borrower {
  id: number; name: string; phone: string | null; national_id: string | null; employer: string | null
  address: string | null; monthly_income: Money | null; existing_monthly_debt: Money | null
  credit_score: number | null; monthly_business_noi: Money | null; income_verified: boolean | null
}
export interface Installment {
  number: number; due_date: string; principal: Money; interest: Money; fees: Money; total: Money; paid: Money
  balance_after: Money; complete: boolean
}
export interface Assessment {
  recommendation: Recommendation; risk_score: Money; monthly_payment: Money; dti: Money | null; dscr: Money | null
  max_recommended_principal: Money; max_dti: Money; policy_version: string; assessed_on: string; notes: string[]
}
export interface LoanSummary {
  id: number; ref: string; borrower_id: number; borrower_name: string; product: string; principal: Money
  annual_rate: Money; term_months: number; state: LoanState; days_overdue: number; outstanding: Money
  overdue_amount: Money; next_due_date: string | null; next_due_amount: Money | null; submitted_on: string | null
  recommendation: Recommendation | null
}
export interface Payment { paid_on: string; amount: Money; method: string }
export interface LoanDetail extends LoanSummary {
  interest_method: 'DECLINING_BALANCE' | 'FLAT'; borrower: Borrower; schedule: Installment[]; total_interest: Money
  assessment: Assessment | null; history: { when: string; text: string; who: string | null }[]; payments: Payment[]
  payment_reference: string
}
export interface Dashboard {
  as_of: string; gross_portfolio: Money; active_loans: number; disbursed_this_month: number; par30_ratio: Money
  due_today_amount: Money; due_today_count: number; collected_today_count: number; pending_count: number
  arrears_buckets: { label: string; amount: Money; loans: number }[]; arrears_total: Money; arrears_loans: number
}
export interface CollectionItem {
  loan_id: number; ref: string; borrower_name: string; phone: string | null; state: LoanState; days_overdue: number
  amount_due: Money; note: string
}
export interface ActionResult { loan_id: number; state: LoanState; message: string }
export interface Receipt {
  receipt_no: string; loan_id: number; ref: string; borrower_name: string; amount: Money; method: PaymentMethod
  reference: string; received_on: string; sms_sent_to: string | null
}
export interface PortalLoan {
  ref: string; borrowed: Money; left_to_pay: Money; payments_made: number; payments_total: number
  next_due_date: string | null; next_due_amount: Money | null; days_overdue: number; payment_reference: string
  ways_to_pay: { name: string; how: string }[]; recent_payments: Payment[]; schedule: Installment[]
}
export interface PortalHome { first_name: string; company_name: string; loan: PortalLoan | null }
export interface Quote {
  amount: Money; months: number; annual_rate: Money; monthly_payment: Money; total_repayable: Money; total_interest: Money
}

export class ApiError extends Error {
  status: number
  fields: { field: string; message: string }[]
  constructor(status: number, message: string, fields: { field: string; message: string }[] = []) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'No connection. Check your internet and try again.')
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Something went wrong. Try again.'
    throw new ApiError(res.status, detail, data.fields ?? [])
  }
  return data as T
}

export const api = {
  staff: {
    login: (username: string, password: string) => request<StaffUser>('POST', '/api/staff/login', { username, password }),
    logout: () => request<void>('POST', '/api/staff/logout'),
    me: () => request<StaffUser>('GET', '/api/staff/me'),
    dashboard: () => request<Dashboard>('GET', '/api/staff/dashboard'),
    loans: (state?: LoanState) => request<LoanSummary[]>('GET', `/api/staff/loans${state ? `?state=${state}` : ''}`),
    loan: (id: number) => request<LoanDetail>('GET', `/api/staff/loans/${id}`),
    assess: (id: number) => request<LoanDetail>('POST', `/api/staff/loans/${id}/assess`),
    approve: (id: number, amount: string, note: string) =>
      request<ActionResult>('POST', `/api/staff/loans/${id}/approve`, { amount, note }),
    reject: (id: number, note: string) => request<ActionResult>('POST', `/api/staff/loans/${id}/reject`, { note }),
    disburse: (id: number) => request<ActionResult>('POST', `/api/staff/loans/${id}/disburse`),
    collections: (view: 'today' | 'arrears' | 'all') =>
      request<CollectionItem[]>('GET', `/api/staff/collections?view=${view}`),
    repay: (id: number, body: { amount: string; method: PaymentMethod; reference: string; received_on: string }) =>
      request<Receipt>('POST', `/api/staff/loans/${id}/repayments`, body),
  },
  portal: {
    requestCode: (phone: string) => request<{ message: string }>('POST', '/api/portal/otp', { phone }),
    verify: (phone: string, code: string) => request<{ first_name: string }>('POST', '/api/portal/verify', { phone, code }),
    logout: () => request<void>('POST', '/api/portal/logout'),
    home: () => request<PortalHome>('GET', '/api/portal/home'),
    quote: (amount: string, months: number) => request<Quote>('POST', '/api/portal/quote', { amount, months }),
    apply: (body: { amount: string; months: number; monthly_income: string; existing_monthly_debt: string }) =>
      request<{ ref: string; amount: Money; months: number; monthly_payment: Money; message: string }>(
        'POST', '/api/portal/applications', body),
  },
}
