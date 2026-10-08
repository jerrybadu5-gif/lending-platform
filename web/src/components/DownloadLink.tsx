import { useState, type MouseEvent, type ReactNode } from 'react'
import { staffHeaders } from '../api/client'

/** File name from a Content-Disposition header (prefers the UTF-8 form). */
export function fileNameFrom(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (star) {
    try { return decodeURIComponent(star[1]) } catch { /* fall through to the plain name */ }
  }
  const plain = /filename="([^"]+)"/i.exec(header)
  return plain ? plain[1] : null
}

/**
 * A download link that fetches the file first, so a refused download (session ended, document
 * missing, loan not approved yet) shows its message instead of saving the error as a file.
 * The href stays real, so the link still works with a middle click or without JavaScript.
 */
export function DownloadLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function click(e: MouseEvent<HTMLAnchorElement>) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(href, { credentials: 'same-origin', headers: staffHeaders(href) })
      if (!res.ok) {
        let msg = res.status === 401 ? 'Your session has ended. Sign in again, then try.' : "This file couldn't be downloaded. Try again."
        if (res.status !== 401) {
          try {
            const body = await res.json()
            if (body && typeof body.detail === 'string') msg = body.detail
          } catch { /* not JSON: keep the plain message */ }
        }
        setError(msg)
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileNameFrom(res.headers.get('content-disposition')) ?? href.split('/').pop() ?? 'download'
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
    } catch {
      setError('No connection. Check your internet and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex flex-col gap-1">
      <a href={href} onClick={click} className={className} aria-busy={busy || undefined}>{children}</a>
      {error && <span role="alert" className="text-[12px] leading-4 text-danger">{error}</span>}
    </span>
  )
}
