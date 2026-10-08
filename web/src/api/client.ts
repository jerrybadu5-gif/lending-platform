// Typed client for the McLender API. Money arrives as decimal strings ("1318.74"); keep it a string
// until it is shown (formatKina), so no rounding happens in the browser.

export type Money = string
export type LoanState =
  | 'PENDING' | 'APPROVED' | 'REJECTED' | 'ACTIVE' | 'ARREARS' | 'ARREARS_LATE' | 'CLOSED' | 'WRITTEN_OFF' | 'WITHDRAWN'
export type Recommendation = 'APPROVE' | 'REFER' | 'DECLINE'
export type PaymentMethod = 'cash' | 'bank' | 'mobile' | 'payroll'

export type Gender = 'female' | 'male'
export type DocumentKind = 'id' | 'payslip' | 'bank_statement' | 'deduction_authority' | 'other' | 'signed_agreement' | 'receipt'
export const DOCUMENT_LABELS: Record<DocumentKind, string> = {
  id: "ID (NID card, passport or driver's licence)",
  payslip: 'Latest 3 payslips',
  bank_statement: 'Bank statement (last 3 months)',
  deduction_authority: 'Payroll deduction authority (signed)',
  other: 'Other document',
  signed_agreement: 'Signed loan agreement',
  receipt: 'Payment receipt',
}

export interface StaffUser { username: string; display_name: string; roles: string[]; review_required?: boolean; allow_self_approval?: boolean }
export interface BankAccount { bank: string; branch: string | null; account_name: string; account_number: string }
export interface NextOfKin { name: string; relationship: string; phone: string }
export interface Borrower {
  id: number; name: string; first_name?: string | null; last_name?: string | null
  phone: string | null; national_id: string | null; employer: string | null
  address: string | null; monthly_income: Money | null; existing_monthly_debt: Money | null
  credit_score: number | null; monthly_business_noi: Money | null; income_verified: boolean | null
  has_photo?: boolean
  date_of_birth: string | null; gender: Gender | null; payroll_number: string | null
  bank: BankAccount | null; next_of_kin: NextOfKin | null
}
export interface BorrowerIn {
  first_name: string; last_name: string; phone: string; date_of_birth: string; gender: Gender; address: string
  national_id: string | null; employer: string | null; payroll_number: string | null
  monthly_income: Money | null; existing_monthly_debt: Money; bank: BankAccount | null; next_of_kin: NextOfKin | null
}
export interface BorrowerListItem { id: number; name: string; phone: string | null; national_id: string | null; employer: string | null }
export interface BorrowerDocument {
  id: number; kind: DocumentKind; file_name: string; content_type: string; size: number; uploaded_on: string | null
}
export interface KycStatus { complete: boolean; missing: string[]; have: Partial<Record<DocumentKind, number>> }
export interface LoanEvent { when: string; text: string; who: string | null }
export interface PayoutStatus {
  loan_id: number; borrower_told: LoanEvent[]; told_done: boolean; sms_delivers: boolean; payout_pending: boolean
  signed_agreement: BorrowerDocument | null; bank: BankAccount | null
  phone: string | null; ready: boolean; missing: string[]
}
export type PayoutMethod = 'bank' | 'mobile' | 'cash'
export interface BorrowerProfile {
  borrower: Borrower; documents: BorrowerDocument[]; kyc: KycStatus; loans: LoanSummary[]
  notes: LoanEvent[]; has_photo: boolean
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
  review_stage?: ReviewStage | null
}
export type ReviewStage = 'DRAFT' | 'SUBMITTED' | 'RETURNED'
export type OfficerAdvice = 'APPROVE' | 'DECLINE'
export interface LoanReview {
  stage: ReviewStage; officer_recommendation: OfficerAdvice | null; officer_amount: Money | null; officer_note: string | null
  submitted_by: string | null; submitted_user?: string | null; submitted_on: string | null
  returned_note: string | null; returned_by: string | null; returned_on: string | null
}
export interface IdScan {
  photo: string | null
  suggestions: {
    national_id: string | null; first_name: string | null; last_name: string | null; date_of_birth: string | null; gender: Gender | null
    document_type?: 'passport' | 'national_id' | 'licence' | null; document_number?: string | null
  }
  text_read: boolean; problems: string[]
}
export interface Payment { id: number | null; paid_on: string; amount: Money; method: string; reference: string | null }
export interface LoanDetail extends LoanSummary {
  interest_method: 'DECLINING_BALANCE' | 'FLAT'; borrower: Borrower; schedule: Installment[]; total_interest: Money
  assessment: Assessment | null; history: { when: string; text: string; who: string | null }[]; payments: Payment[]
  payment_reference: string; approved_on?: string | null
  review?: LoanReview | null
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
  reference: string; received_on: string; sms_sent_to: string | null; payment_id: number | null
  filed?: boolean
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

// Which staff member this browser tab is signed in as. Each tab keeps its own (sessionStorage), so a loan
// officer and a credit manager can work side by side in one browser; the API picks that person's session.
const TAB_USER = 'mcl-staff-user'
const TAB_CREDENTIAL = 'mcl-staff-tab'

export function tabUser(): string | null {
  try { return sessionStorage.getItem(TAB_USER) } catch { return null }
}

export function setTabUser(username: string | null, credential?: string) {
  try {
    if (username && credential) {
      sessionStorage.setItem(TAB_USER, username)
      sessionStorage.setItem(TAB_CREDENTIAL, credential)
    } else {
      sessionStorage.removeItem(TAB_USER)
      sessionStorage.removeItem(TAB_CREDENTIAL)
    }
  } catch { /* Requests without both stored values are rejected by the API. */ }
}

/** Headers for a staff request, naming this tab's person. */
export function staffHeaders(path: string): Record<string, string> {
  const user = path.startsWith('/api/staff') ? tabUser() : null
  try {
    const credential = sessionStorage.getItem(TAB_CREDENTIAL)
    return user && credential ? { 'X-MCL-User': user, 'X-MCL-Tab': credential } : {}
  } catch { return {} }
}

async function request<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData
  let res: Response
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      // FormData sets its own multipart Content-Type (with the boundary).
      headers: { ...staffHeaders(path), ...(body === undefined || form ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'No connection. Check your internet and try again.')
  }
  if (res.status === 204) return undefined as T
  let data: unknown
  try {
    data = await res.json()
  } catch {
    if (res.ok) throw new ApiError(res.status, 'The server sent an answer we could not read. Try again.')
    data = null
  }
  if (!res.ok) {
    // An error body may be anything (null, a list, HTML): read fields only from an object.
    const body = (data !== null && typeof data === 'object' ? data : {}) as { detail?: unknown; fields?: unknown }
    const detail = typeof body.detail === 'string' ? body.detail : 'Something went wrong. Try again.'
    const fields = Array.isArray(body.fields) ? (body.fields as { field: string; message: string }[]) : []
    throw new ApiError(res.status, detail, fields)
  }
  return data as T
}

export const api = {
  staff: {
    login: async (username: string, password: string) => {
      setTabUser(null) // sign in as anyone, whoever this tab was before
      const user = await request<StaffUser & { tab_credential: string }>('POST', '/api/staff/login', { username, password })
      setTabUser(user.username, user.tab_credential)
      return user
    },
    logout: async () => {
      try { await request<void>('POST', '/api/staff/logout') } finally { setTabUser(null) }
    },
    me: () => request<StaffUser>('GET', '/api/staff/me'),
    dashboard: () => request<Dashboard>('GET', '/api/staff/dashboard'),
    loans: (state?: LoanState) => request<LoanSummary[]>('GET', `/api/staff/loans${state ? `?state=${state}` : ''}`),
    loan: (id: number) => request<LoanDetail>('GET', `/api/staff/loans/${id}`),
    assess: (id: number) => request<LoanDetail>('POST', `/api/staff/loans/${id}/assess`),
    approve: (id: number, amount: string, note: string) =>
      request<ActionResult>('POST', `/api/staff/loans/${id}/approve`, { amount, note }),
    submit: (id: number, body: { recommendation: OfficerAdvice; amount: string | null; note: string }) =>
      request<LoanDetail>('POST', `/api/staff/loans/${id}/submit`, body),
    sendBack: (id: number, note: string) => request<LoanDetail>('POST', `/api/staff/loans/${id}/return`, { note }),
    reject: (id: number, note: string) => request<ActionResult>('POST', `/api/staff/loans/${id}/reject`, { note }),
    disburse: (id: number, body: { method: PayoutMethod; reference: string; account: string | null }) =>
      request<ActionResult>('POST', `/api/staff/loans/${id}/disburse`, body),
    payout: (id: number) => request<PayoutStatus>('GET', `/api/staff/loans/${id}/payout`),
    contact: (id: number, channel: 'sms' | 'phone', note = '') =>
      request<LoanEvent>('POST', `/api/staff/loans/${id}/contact`, { channel, note }),
    uploadSigned: (id: number, file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<BorrowerDocument>('POST', `/api/staff/loans/${id}/signed-agreement`, form)
    },
    loanDocuments: (id: number) => request<BorrowerDocument[]>('GET', `/api/staff/loans/${id}/documents`),
    removeLoanDocument: (id: number, docId: number, reason: string) =>
      request<void>('POST', `/api/staff/loans/${id}/documents/${docId}/remove`, { reason }),
    collections: (view: 'today' | 'arrears' | 'all') =>
      request<CollectionItem[]>('GET', `/api/staff/collections?view=${view}`),
    repay: (id: number, body: { amount: string; method: PaymentMethod; reference: string; received_on: string }) =>
      request<Receipt>('POST', `/api/staff/loans/${id}/repayments`, body),
    borrowers: (q: string) => request<BorrowerListItem[]>('GET', `/api/staff/borrowers?q=${encodeURIComponent(q)}`),
    borrower: (id: number) => request<BorrowerProfile>('GET', `/api/staff/borrowers/${id}`),
    createBorrower: (body: BorrowerIn) => request<Borrower>('POST', '/api/staff/borrowers', body),
    updateBorrower: (id: number, body: BorrowerIn) => request<Borrower>('PUT', `/api/staff/borrowers/${id}`, body),
    kyc: (id: number) => request<KycStatus>('GET', `/api/staff/borrowers/${id}/kyc`),
    upload: (id: number, kind: DocumentKind, file: File) => {
      const form = new FormData()
      form.append('kind', kind)
      form.append('file', file)
      return request<BorrowerDocument>('POST', `/api/staff/borrowers/${id}/documents`, form)
    },
    removeDocument: (id: number, docId: number, reason: string) =>
      request<void>('POST', `/api/staff/borrowers/${id}/documents/${docId}/remove`, { reason }),
    scanId: (id: number, docId: number) => request<IdScan>('POST', `/api/staff/borrowers/${id}/documents/${docId}/scan`),
    setPhoto: (id: number, photo: Blob) => {
      const form = new FormData()
      form.append('file', photo, 'photo.jpg')
      return request<void>('PUT', `/api/staff/borrowers/${id}/photo`, form)
    },
    apply: (id: number, body: { amount: string; months: number; purpose: string }) =>
      request<LoanSummary>('POST', `/api/staff/borrowers/${id}/applications`, body),
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

/** Links for files the browser downloads directly (the session cookie goes with them). */
export const files = {
  photo: (borrowerId: number) => `/api/staff/borrowers/${borrowerId}/photo`,
  document: (borrowerId: number, docId: number) => `/api/staff/borrowers/${borrowerId}/documents/${docId}`,
  loanDocument: (loanId: number, docId: number) => `/api/staff/loans/${loanId}/documents/${docId}`,
  agreement: (loanId: number) => `/api/staff/loans/${loanId}/agreement.pdf`,
  schedule: (loanId: number) => `/api/staff/loans/${loanId}/schedule.pdf`,
  statement: (loanId: number) => `/api/staff/loans/${loanId}/statement.pdf`,
  receipt: (loanId: number, paymentId: number) => `/api/staff/loans/${loanId}/payments/${paymentId}/receipt.pdf`,
  portalStatement: '/api/portal/loan/statement.pdf',
  portalSchedule: '/api/portal/loan/schedule.pdf',
}
