import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { DOCUMENT_LABELS, staffHeaders, type BorrowerDocument } from '../api/client'
import { formatDate } from '../lib/format'
import { DownloadLink } from './DownloadLink'
import { Button, Field } from './index'

const PREVIEWABLE = new Set(['application/pdf', 'image/jpeg', 'image/png'])

export function fileSize(n: number) {
  return n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
}

/** Fetches a stored file and shows it in the page (PDF or photo). The blob URL never outlives the viewer. */
export function FilePreview({ href, contentType, title, height = 520 }: { href: string; contentType: string; title: string; height?: number }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!PREVIEWABLE.has(contentType)) return
    let gone = false
    let made: string | null = null
    fetch(href, { credentials: 'same-origin', headers: staffHeaders(href) })
      .then(async (res) => {
        if (!res.ok) throw new Error(res.status === 401 ? 'Your session has ended. Sign in again.' : "This file couldn't be opened.")
        // Re-type the blob from what the server checked at upload, not from the response.
        const blob = new Blob([await res.blob()], { type: contentType })
        if (gone) return
        made = URL.createObjectURL(blob)
        setUrl(made)
      })
      .catch((e: Error) => { if (!gone) setError(e.message || "This file couldn't be opened.") })
    return () => { gone = true; if (made) URL.revokeObjectURL(made) }
  }, [href, contentType])

  if (!PREVIEWABLE.has(contentType)) return <p className="m-0 text-[13px] text-ink-muted">No preview for this kind of file. Download it to open it.</p>
  if (error) return <p className="m-0 text-[13px] text-danger" role="alert">{error}</p>
  if (!url) return <div className="bg-surface-sunken rounded-md animate-pulse" style={{ height }} aria-label="Loading preview" />
  return contentType === 'application/pdf'
    ? <iframe src={url} title={title} className="w-full rounded-md border border-line bg-white" style={{ height }} />
    : <img src={url} alt={title} className="max-w-full rounded-md border border-line object-contain self-start" style={{ maxHeight: height }} />
}

/**
 * A document opened from a list: preview, download, and (when allowed) remove with a reason.
 * The reason is written to the file's record before the document goes.
 */
export function DocumentViewer({ doc, href, onClose, onRemove, removeNote, extra }: {
  doc: BorrowerDocument
  href: string
  onClose: () => void
  onRemove?: (reason: string) => Promise<unknown>
  removeNote?: ReactNode
  extra?: ReactNode
}) {
  const box = useRef<HTMLDivElement>(null)
  const [removing, setRemoving] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const label = DOCUMENT_LABELS[doc.kind] ?? 'Document'

  const close = useRef(onClose)
  useEffect(() => { close.current = onClose })
  // Focus moves into the viewer once, and back to where it was when it closes.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    box.current?.focus()
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') close.current() }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); before?.focus?.() }
  }, [])

  async function remove(e: FormEvent) {
    e.preventDefault()
    if (!onRemove) return
    if (reason.trim().length < 3) { setError('Say why it is being removed, for the record.'); return }
    setBusy(true)
    setError(null)
    try {
      await onRemove(reason.trim())
      onClose()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={box} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`${label}: ${doc.file_name}`}
        className="ml-card flex flex-col gap-4 w-full outline-none" style={{ maxWidth: 820, maxHeight: '92vh', overflow: 'auto' }}>
        <header className="flex justify-between items-start gap-3">
          <div className="flex flex-col gap-0.5 min-w-0">
            <h2 className="ml-h2">{label}</h2>
            <span className="text-[13px] text-ink-muted break-all">{doc.file_name} · {fileSize(doc.size)}{doc.uploaded_on ? ` · uploaded ${formatDate(doc.uploaded_on)}` : ''}</span>
          </div>
          <Button size="sm" variant="quiet" onClick={onClose} aria-label="Close">Close</Button>
        </header>
        <FilePreview href={href} contentType={doc.content_type} title={`${label}: ${doc.file_name}`} />
        <div className="flex flex-wrap gap-2 items-start">
          <DownloadLink href={href} className="ml-btn ml-btn-sm no-underline">Download</DownloadLink>
          {onRemove && !removing && <Button size="sm" variant="quiet" className="text-danger" onClick={() => setRemoving(true)}>Remove…</Button>}
        </div>
        {extra}
        {!onRemove && removeNote && <p className="m-0 text-[13px] text-ink-muted">{removeNote}</p>}
        {onRemove && removing && (
          <form onSubmit={remove} className="flex flex-col gap-2 border-t border-line pt-3" aria-label="Remove document">
            <Field label="Why remove it?" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300}
              placeholder="Wrong borrower's payslip; uploaded by mistake" hint="Kept on the record with your name." />
            {error && <span className="text-[13px] text-danger" role="alert">{error}</span>}
            <div className="flex gap-2">
              <Button type="submit" size="sm" variant="primary" disabled={busy}>{busy ? 'Removing…' : 'Remove document'}</Button>
              <Button size="sm" variant="quiet" onClick={() => { setRemoving(false); setError(null) }}>Cancel</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
