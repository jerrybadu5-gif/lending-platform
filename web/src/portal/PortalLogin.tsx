import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Button, Field } from '../components'
import { PortalShell } from './PortalShell'

export default function PortalLogin() {
  const [phone, setPhone] = useState('')
  const [step, setStep] = useState<'phone' | 'code'>('phone')
  const [code, setCode] = useState('')
  const [info, setInfo] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const qc = useQueryClient()

  async function sendCode(e?: FormEvent) {
    e?.preventDefault()
    if (phone.replace(/\D/g, '').length < 7) return setError('Enter the mobile number you gave us, like 7123 4567.')
    setBusy(true); setError('')
    try {
      setInfo((await api.portal.requestCode(phone)).message)
      setStep('code')
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  async function verify(e: FormEvent) {
    e.preventDefault()
    if (!/^\d{6}$/.test(code)) return setError('The code has 6 digits.')
    setBusy(true); setError('')
    try {
      await api.portal.verify(phone, code)
      qc.removeQueries({ queryKey: ['portal'] })
      nav('/portal', { replace: true })
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <PortalShell tabs={false}>
      <div className="flex flex-col gap-1 pt-6">
        <span className="text-[13px] text-ink-muted">Breez Lending</span>
        <h1 className="ml-title" style={{ fontSize: 28, lineHeight: '34px' }}>See your loan</h1>
      </div>
      {step === 'phone' ? (
        <form onSubmit={sendCode} className="ml-card flex flex-col gap-4" style={{ padding: 16 }} noValidate>
          <Field label="Your mobile number" type="tel" inputMode="tel" autoComplete="tel" placeholder="7123 4567"
            value={phone} onChange={(e) => setPhone(e.target.value)} hint="We'll send a 6-digit code by SMS." />
          {error && <div className="ml-alert ml-alert-danger" role="alert">{error}</div>}
          <Button type="submit" variant="primary" className="justify-center" style={{ height: 48 }} disabled={busy}>Send code</Button>
        </form>
      ) : (
        <form onSubmit={verify} className="ml-card flex flex-col gap-4" style={{ padding: 16 }} noValidate>
          <p className="m-0 text-[13px] leading-[18px] text-ink-muted" role="status">{info}</p>
          <Field label="6-digit code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} autoFocus />
          {error && <div className="ml-alert ml-alert-danger" role="alert">{error}</div>}
          <Button type="submit" variant="primary" className="justify-center" style={{ height: 48 }} disabled={busy}>Sign in</Button>
          <div className="flex justify-between">
            <Button variant="quiet" size="sm" onClick={() => { setStep('phone'); setCode(''); setError('') }}>Change number</Button>
            <Button variant="quiet" size="sm" disabled={busy} onClick={() => sendCode()}>Send a new code</Button>
          </div>
        </form>
      )}
      <p className="m-0 text-[12px] leading-4 text-ink-muted">Breez Lending will never ask for your code by phone. Don't share it with anyone.</p>
    </PortalShell>
  )
}
