import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { AssessmentCard, Field, StatusPill } from '../../src/components'

it('status pills always carry a word', () => {
  render(<><StatusPill status="ARREARS" days={12} /><StatusPill status="REFER" /></>)
  expect(screen.getByText('In arrears · 12 days')).toBeInTheDocument()
  expect(screen.getByText('Refer')).toBeInTheDocument()
})

it('assessment card states DTI in words for screen readers', () => {
  render(<AssessmentCard recommendation="REFER" score="55.8" dti="0.4446" maxDti="0.40" monthlyPayment="1418.39" cap="13113.42" notes={['DTI above limit']} />)
  expect(screen.getByRole('img', { name: 'Debt-to-income 44.5% against a limit of 40%' })).toBeInTheDocument()
  expect(screen.getByText('K 13,113.42')).toBeInTheDocument()
})

it('field links its label, hint and error', () => {
  render(<Field label="Monthly income (PGK)" error="Required" />)
  const input = screen.getByLabelText('Monthly income (PGK)')
  expect(input).toHaveAttribute('aria-invalid', 'true')
  expect(input).toHaveAccessibleDescription('Required')
})
