import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, type Borrower, type BorrowerIn, type Gender, type IdScan } from '../api/client'
import { Button, ErrorNote, Field, Skeleton } from '../components'
import { formatKina, parseKina } from '../lib/format'

type Form = {
  first_name: string; last_name: string; phone: string; date_of_birth: string; gender: Gender | ''; address: string
  national_id: string; employer: string; payroll_number: string; monthly_income: string; existing_monthly_debt: string
  bank: string; branch: string; account_name: string; account_number: string
  nok_name: string; nok_relationship: string; nok_phone: string
}

const EMPTY: Form = {
  first_name: '', last_name: '', phone: '', date_of_birth: '', gender: '', address: '', national_id: '', employer: '',
  payroll_number: '', monthly_income: '', existing_monthly_debt: '0.00', bank: '', branch: '', account_name: '',
  account_number: '', nok_name: '', nok_relationship: '', nok_phone: '',
}

const BANKS = ['BSP', 'Kina Bank', 'Westpac', 'ANZ', 'TISA Bank', 'Nationwide Microbank', 'Women’s Micro Bank']

function fromBorrower(b: Borrower): Form {
  const [first, ...rest] = b.name.split(' ')
  return {
    first_name: first ?? '', last_name: rest.join(' '), phone: b.phone ?? '', date_of_birth: b.date_of_birth ?? '',
    gender: b.gender ?? '', address: b.address ?? '', national_id: b.national_id ?? '', employer: b.employer ?? '',
    payroll_number: b.payroll_number ?? '',
    monthly_income: b.monthly_income ? formatKina(b.monthly_income, { currency: false }) : '',
    existing_monthly_debt: formatKina(b.existing_monthly_debt ?? '0', { currency: false }),
    bank: b.bank?.bank ?? '', branch: b.bank?.branch ?? '', account_name: b.bank?.account_name ?? '',
    account_number: b.bank?.account_number ?? '', nok_name: b.next_of_kin?.name ?? '',
    nok_relationship: b.next_of_kin?.relationship ?? '', nok_phone: b.next_of_kin?.phone ?? '',
  }
}

function ageOn(dob: string, today = new Date()): number {
  const d = new Date(`${dob}T00:00:00`)
  let age = today.getFullYear() - d.getFullYear()
  if (today.getMonth() < d.getMonth() || (today.getMonth() === d.getMonth() && today.getDate() < d.getDate())) age--
  return age
}

const digits = (s: string) => s.replace(/\D/g, '')

/** Field errors staff can fix before sending; the server checks again. */
export function validate(f: Form): Partial<Record<keyof Form, string>> {
  const e: Partial<Record<keyof Form, string>> = {}
  if (!f.first_name.trim()) e.first_name = 'Enter the first name.'
  if (!f.last_name.trim()) e.last_name = 'Enter the last name.'
  const p = digits(f.phone)
  if (!(p.length === 8 || (p.length === 11 && p.startsWith('675')))) e.phone = 'Enter an 8-digit PNG mobile number, like 7012 3344.'
  if (!f.date_of_birth) e.date_of_birth = 'Enter the date of birth.'
  else if (ageOn(f.date_of_birth) < 18) e.date_of_birth = 'Borrowers must be 18 or older.'
  if (!f.gender) e.gender = 'Choose one.'
  if (f.address.trim().length < 3) e.address = 'Enter where the borrower lives (section, lot, suburb).'
  if (f.national_id && !/^[0-9A-Za-z -]{4,30}$/.test(f.national_id.trim())) e.national_id = 'Use numbers and letters only.'
  if (f.monthly_income && parseKina(f.monthly_income) === null) e.monthly_income = 'Enter an amount like 3,800.00'
  if (parseKina(f.existing_monthly_debt || '0') === null) e.existing_monthly_debt = 'Enter an amount like 250.00, or 0.'
  const anyBank = f.bank || f.account_number || f.account_name
  if (anyBank) {
    if (!f.bank) e.bank = 'Choose the bank.'
    if (!/^[0-9 -]{4,30}$/.test(f.account_number.trim())) e.account_number = 'Enter the account number (numbers only).'
    if (f.account_name.trim().length < 2) e.account_name = 'Enter the name on the account.'
  }
  const anyNok = f.nok_name || f.nok_phone || f.nok_relationship
  if (anyNok) {
    if (f.nok_name.trim().length < 2) e.nok_name = 'Enter their name.'
    if (f.nok_relationship.trim().length < 2) e.nok_relationship = 'For example: wife, brother, uncle.'
    if (digits(f.nok_phone).length < 7) e.nok_phone = 'Enter their phone number.'
  }
  return e
}

function toBody(f: Form): BorrowerIn {
  const clean = (s: string) => s.trim() || null
  return {
    first_name: f.first_name.trim(), last_name: f.last_name.trim(), phone: f.phone.trim(),
    date_of_birth: f.date_of_birth, gender: f.gender as Gender, address: f.address.trim(),
    national_id: clean(f.national_id), employer: clean(f.employer), payroll_number: clean(f.payroll_number),
    monthly_income: f.monthly_income ? parseKina(f.monthly_income) : null,
    existing_monthly_debt: parseKina(f.existing_monthly_debt || '0') ?? '0.00',
    bank: f.bank ? { bank: f.bank, branch: clean(f.branch), account_name: f.account_name.trim(), account_number: f.account_number.trim() } : null,
    next_of_kin: f.nok_name ? { name: f.nok_name.trim(), relationship: f.nok_relationship.trim(), phone: f.nok_phone.trim() } : null,
  }
}

// Server field names ("bank.account_number") to form keys.
const SERVER_FIELDS: Record<string, keyof Form> = {
  'bank.bank': 'bank', 'bank.branch': 'branch', 'bank.account_name': 'account_name', 'bank.account_number': 'account_number',
  'next_of_kin.name': 'nok_name', 'next_of_kin.relationship': 'nok_relationship', 'next_of_kin.phone': 'nok_phone',
}

export function NewBorrower() {
  return <BorrowerForm initial={EMPTY} />
}

/** Details read from the ID card replace what's on file only where the card had a value. */
export function withCard(form: Form, card: IdScan['suggestions'] | undefined): { form: Form; changed: (keyof Form)[] } {
  if (!card) return { form, changed: [] }
  const next = { ...form }
  const changed: (keyof Form)[] = []
  const put = (k: keyof Form, v: string | null | undefined) => {
    if (v && v !== form[k]) { (next[k] as string) = v; changed.push(k) }
  }
  put('first_name', card.first_name)
  put('last_name', card.last_name)
  put('national_id', card.national_id)
  put('date_of_birth', card.date_of_birth)
  put('gender', card.gender)
  return { form: next, changed }
}

const CARD_LABELS: Partial<Record<keyof Form, string>> = {
  first_name: 'first name', last_name: 'last name', national_id: 'NID number', date_of_birth: 'date of birth', gender: 'gender',
}

export function EditBorrower() {
  const id = Number(useParams().id)
  const card = (useLocation().state as { fromCard?: IdScan['suggestions'] } | null)?.fromCard
  const q = useQuery({ queryKey: ['borrower', id], queryFn: () => api.staff.borrower(id) })
  if (q.error) return <ErrorNote error={q.error} retry={() => q.refetch()} />
  if (!q.data) return <Skeleton h={400} />
  const { form, changed } = withCard(fromBorrower(q.data.borrower), card)
  return <BorrowerForm id={id} initial={form} fromCard={changed} />
}

function BorrowerForm({ id, initial, fromCard = [] }: { id?: number; initial: Form; fromCard?: (keyof Form)[] }) {
  const [f, setF] = useState<Form>(initial)
  const [touched, setTouched] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  const errors = validate(f)
  const save = useMutation({
    mutationFn: () => (id ? api.staff.updateBorrower(id, toBody(f)) : api.staff.createBorrower(toBody(f))),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ['borrowers'] })
      qc.invalidateQueries({ queryKey: ['borrower', b.id] })
      nav(`/staff/borrowers/${b.id}`)
    },
  })
  const serverErrors: Partial<Record<keyof Form, string>> = {}
  if (save.error instanceof ApiError) {
    for (const fe of save.error.fields) {
      const key = (SERVER_FIELDS[fe.field] ?? fe.field) as keyof Form
      if (key in EMPTY) serverErrors[key] = fe.message.replace(/^Value error, /, '')
    }
  }
  const err = (k: keyof Form) => (touched ? errors[k] : undefined) ?? serverErrors[k]
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  function submit(e: FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (Object.keys(errors).length === 0) save.mutate()
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-6" style={{ maxWidth: 820 }}>
      <div className="text-[13px] text-ink-muted"><Link to="/staff/borrowers">Borrowers</Link> / {id ? 'Edit' : 'New borrower'}</div>
      <h1 className="ml-title">{id ? `Edit ${initial.first_name} ${initial.last_name}` : 'New borrower'}</h1>
      {fromCard.length > 0 && (
        <div className="ml-alert ml-alert-warning" role="note">
          Filled in from the ID card: {fromCard.map((k) => CARD_LABELS[k]).join(', ')}. Check each one against the card before you save.
        </div>
      )}

      <Section title="Personal details">
        <Field label="First name" autoComplete="off" value={f.first_name} onChange={set('first_name')} error={err('first_name')} />
        <Field label="Last name" autoComplete="off" value={f.last_name} onChange={set('last_name')} error={err('last_name')} />
        <Field label="Date of birth" type="date" value={f.date_of_birth} onChange={set('date_of_birth')} error={err('date_of_birth')} />
        <fieldset className={`ml-field border-0 m-0 p-0${err('gender') ? ' ml-field-error' : ''}`}>
          <legend className="ml-label">Gender</legend>
          <div className="flex gap-2 mt-1.5 items-start">
            {(['female', 'male'] as Gender[]).map((g) => (
              <button type="button" key={g} className="ml-chip" style={{ height: 40, minWidth: 96 }} aria-pressed={f.gender === g} onClick={() => setF({ ...f, gender: g })}>
                {g === 'female' ? 'Female' : 'Male'}
              </button>
            ))}
          </div>
          {err('gender') && <div className="ml-error" role="alert">{err('gender')}</div>}
        </fieldset>
        <Field label="NID number" optional value={f.national_id} onChange={set('national_id')} error={err('national_id')}
          hint="From the National ID card. Upload a photo of the card under Documents." />
      </Section>

      <Section title="Contact">
        <Field label="Mobile number" inputMode="tel" placeholder="7012 3344" value={f.phone} onChange={set('phone')} error={err('phone')}
          hint="The borrower signs in to the portal and gets SMS receipts on this number." />
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="Home address" placeholder="Section 12, Lot 4, Gerehu Stage 2, NCD" value={f.address} onChange={set('address')} error={err('address')} />
        </div>
      </Section>

      <Section title="Work and income">
        <Field label="Employer" optional value={f.employer} onChange={set('employer')} error={err('employer')} />
        <Field label="Payroll or employee number" optional value={f.payroll_number} onChange={set('payroll_number')}
          hint="Needed for payroll deductions." />
        <Field label="Take-home pay each month (PGK)" optional prefix="K" inputMode="decimal" value={f.monthly_income}
          onChange={set('monthly_income')} error={err('monthly_income')} hint="From the latest payslips." />
        <Field label="Other loan payments each month (PGK)" prefix="K" inputMode="decimal" value={f.existing_monthly_debt}
          onChange={set('existing_monthly_debt')} error={err('existing_monthly_debt')} />
      </Section>

      <Section title="Bank account for payout" note="Optional now; needed before the loan is paid out.">
        <div className={`ml-field${err('bank') ? ' ml-field-error' : ''}`}>
          <label className="ml-label" htmlFor="bank">Bank</label>
          <select id="bank" className="ml-input" value={f.bank} onChange={set('bank')}>
            <option value="">—</option>
            {BANKS.map((b) => <option key={b}>{b}</option>)}
          </select>
          {err('bank') && <div className="ml-error" role="alert">{err('bank')}</div>}
        </div>
        <Field label="Branch" optional value={f.branch} onChange={set('branch')} />
        <Field label="Name on the account" value={f.account_name} onChange={set('account_name')} error={err('account_name')} />
        <Field label="Account number" inputMode="numeric" value={f.account_number} onChange={set('account_number')} error={err('account_number')} />
      </Section>

      <Section title="Next of kin" note="Optional. Someone we can contact if we can't reach the borrower.">
        <Field label="Name" value={f.nok_name} onChange={set('nok_name')} error={err('nok_name')} />
        <Field label="Relationship" placeholder="Wife, brother, uncle…" value={f.nok_relationship} onChange={set('nok_relationship')} error={err('nok_relationship')} />
        <Field label="Phone" inputMode="tel" value={f.nok_phone} onChange={set('nok_phone')} error={err('nok_phone')} />
      </Section>

      {save.error && <div className="ml-alert ml-alert-danger" role="alert">{(save.error as Error).message}</div>}
      {touched && Object.keys(errors).length > 0 && <div className="ml-alert ml-alert-warning" role="alert">Fix the fields marked in red, then save again.</div>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" disabled={save.isPending}>{save.isPending ? 'Saving…' : id ? 'Save changes' : 'Save borrower'}</Button>
        <Link to={id ? `/staff/borrowers/${id}` : '/staff/borrowers'} className="ml-btn ml-btn-quiet no-underline">Cancel</Link>
      </div>
    </form>
  )
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="ml-card flex flex-col gap-4">
      <div><h2 className="ml-h2">{title}</h2>{note && <p className="m-0 mt-1 text-[13px] text-ink-muted">{note}</p>}</div>
      <div className="grid gap-x-6 gap-y-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>{children}</div>
    </section>
  )
}
