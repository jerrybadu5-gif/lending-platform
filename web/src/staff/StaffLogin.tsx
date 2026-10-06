import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Button, Field } from '../components'

export function StaffLogin() {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const qc = useQueryClient()

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true)
    setError('')
    try {
      const user = await api.staff.login(String(f.get('username')), String(f.get('password')))
      qc.setQueryData(['me'], user)
      nav((loc.state as { from?: string } | null)?.from ?? '/staff', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid place-items-center bg-surface px-4">
      <form onSubmit={submit} className="ml-card flex flex-col gap-4 w-full" style={{ maxWidth: 380 }} noValidate>
        <div>
          <div className="font-display text-[28px] leading-[34px] font-semibold text-brand-deep">McLender</div>
          <div className="text-[13px] text-ink-muted">Breez Lending staff sign-in</div>
        </div>
        <Field label="Username" name="username" autoComplete="username" required autoFocus />
        <Field label="Password" name="password" type="password" autoComplete="current-password" required />
        {error && <div className="ml-alert ml-alert-danger" role="alert">{error}</div>}
        <Button type="submit" variant="primary" disabled={busy} className="justify-center">{busy ? 'Signing in…' : 'Sign in'}</Button>
        <p className="m-0 text-[12px] leading-4 text-ink-muted">Use your Fineract username and password.</p>
      </form>
    </div>
  )
}
