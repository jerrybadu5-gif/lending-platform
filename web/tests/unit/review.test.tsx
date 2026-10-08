import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import type { LoanDetail } from '../../src/api/client'
import { LoanReview } from '../../src/staff/LoanReview'

afterEach(cleanup)

function setup(allowSelfApproval = false, reviewRequired = true) {
  const loan = {
    id: 538, state: 'PENDING', principal: '1200', annual_rate: '24', term_months: 12,
    borrower: { id: 1, name: 'Test Borrower' }, schedule: [], payments: [], history: [], assessment: null,
    review: { stage: 'SUBMITTED', officer_amount: '1000', officer_recommendation: 'APPROVE', submitted_user: 'demo' },
  } as unknown as LoanDetail
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  qc.setQueryData(['loan', 538], loan)
  qc.setQueryData(['me'], { username: 'demo', roles: ['credit manager'], allow_self_approval: allowSelfApproval, review_required: reviewRequired })
  qc.setQueryData(['borrower', 1], { documents: [] })
  qc.setQueryData(['loan-documents', 538, 0], [])
  render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={['/staff/loans/538']}>
    <Routes><Route path="/staff/loans/:id" element={<LoanReview />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
  return { qc, loan }
}

it.each([false, true])('matches the API self-approval setting: %s', (enabled) => {
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
  const { qc, loan } = setup(true)
  const amount = () => screen.getByLabelText('Approved amount (PGK)')
  expect(amount()).toHaveValue('1,000.00')
  fireEvent.change(amount(), { target: { value: '900' } })
  const updated = { ...loan, review: { ...loan.review!, officer_amount: '800' } }
  act(() => { qc.setQueryData(['loan', 538], updated) })
  await waitFor(() => expect(amount()).toHaveValue('800.00'))
  fireEvent.change(amount(), { target: { value: '700' } })
  act(() => { qc.setQueryData(['loan', 538], { ...updated, review: { ...updated.review, stage: 'RETURNED' } }) })
  await waitFor(() => expect(amount()).toHaveValue('800.00'))
  expect(screen.getByRole('button', { name: /^Approve K/ })).toBeDisabled()
})
