import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { Decision } from '../../src/staff/LoanReview'
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
