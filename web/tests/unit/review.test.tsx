import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { Decision, LoanReview } from '../../src/staff/LoanReview'
import { type LoanDetail } from '../../src/api/client'

afterEach(cleanup)

function application(stage: 'DRAFT' | 'SUBMITTED', amount: string): LoanDetail {
  return {
    id: 538, state: 'PENDING', principal: '3000',
    review: { stage, officer_amount: amount, submitted_user: 'demo', officer_note: 'Checked documents' },
  } as LoanDetail
}

function manager(allow = false, required = true) {
  const client = new QueryClient()
  client.setQueryData(['me'], {
    username: 'demo', roles: ['Credit manager'], review_required: required, allow_self_approval: allow,
  })
  return client
}

function setup(allowSelfApproval = false, reviewRequired = true) {
  const loan = {
    id: 538, state: 'PENDING', principal: '1200', annual_rate: '24', term_months: 12,
    borrower: { id: 1, name: 'Test Borrower' }, schedule: [], payments: [], history: [], assessment: null,
    review: { stage: 'SUBMITTED', officer_amount: '1000', officer_recommendation: 'APPROVE', submitted_user: 'demo' },
  } as unknown as LoanDetail
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['loan', 538], loan)
  client.setQueryData(['me'], {
    username: 'demo',
    roles: ['credit manager'],
    allow_self_approval: allowSelfApproval,
    review_required: reviewRequired,
  })
  client.setQueryData(['borrower', 1], { documents: [] })
  client.setQueryData(['loan-documents', 538, 0], [])
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/staff/loans/538']}>
        <Routes>
          <Route path="/staff/loans/:id" element={<LoanReview />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { client, loan }
}

it('resets the open decision amount when the officer review changes', () => {
  const client = manager(true)
  const view = (loan: LoanDetail) => <QueryClientProvider client={client}><Decision loan={loan} /></QueryClientProvider>
  const { rerender } = render(view(application('DRAFT', '1200')))
  fireEvent.change(screen.getByLabelText('Approved amount (PGK)'), { target: { value: '999' } })
  rerender(view(application('SUBMITTED', '1500')))
  expect(screen.getByLabelText('Approved amount (PGK)')).toHaveValue('1,500.00')
  fireEvent.change(screen.getByLabelText('Approved amount (PGK)'), { target: { value: '888' } })
  rerender(view(application('SUBMITTED', '1800')))
  expect(screen.getByLabelText('Approved amount (PGK)')).toHaveValue('1,800.00')
})

it.each([
  [false, true, 'SUBMITTED', true],
  [true, true, 'SUBMITTED', false],
  [true, true, 'DRAFT', true],
  [false, false, 'SUBMITTED', false],
] as const)('matches approval settings %s %s %s', (allow, required, stage, disabled) => {
  render(<QueryClientProvider client={manager(allow, required)}><Decision loan={application(stage, '1200')} /></QueryClientProvider>)
  expect(screen.getByRole('button', { name: /^Approve/ })).toHaveProperty('disabled', disabled)
})

it.each([false, true])('matches the API self-approval setting in the review screen: %s', (enabled) => {
  setup(enabled)
  const approve = screen.getByRole('button', { name: /^Approve K/ })
  if (enabled) expect(approve).toBeEnabled()
  else expect(approve).toBeDisabled()
})

it('allows approval of an own submission when the review gate is off', () => {
  setup(false, false)
  expect(screen.getByRole('button', { name: /^Approve K/ })).toBeEnabled()
})

it('resets the manager amount when the officer amount or review stage changes', async () => {
  const { client, loan } = setup(true)
  const amount = () => screen.getByLabelText('Approved amount (PGK)')
  expect(amount()).toHaveValue('1,000.00')
  fireEvent.change(amount(), { target: { value: '900' } })
  const updated = { ...loan, review: { ...loan.review!, officer_amount: '800' } }
  act(() => { client.setQueryData(['loan', 538], updated) })
  await waitFor(() => expect(amount()).toHaveValue('800.00'))
  fireEvent.change(amount(), { target: { value: '700' } })
  act(() => { client.setQueryData(['loan', 538], { ...updated, review: { ...updated.review, stage: 'RETURNED' } }) })
  await waitFor(() => expect(amount()).toHaveValue('800.00'))
  expect(screen.getByRole('button', { name: /^Approve K/ })).toBeDisabled()
})
