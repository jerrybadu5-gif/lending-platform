import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../../src/api/client'

function reply(status: number, body: string) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status, headers: { 'Content-Type': 'application/json' } })))
}

describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('passes the server message on for an error', async () => {
    reply(422, JSON.stringify({ detail: 'Enter a reference.', fields: [{ field: 'reference', message: 'Required' }] }))
    const err = await api.staff.me().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Enter a reference.')
    expect(err.fields).toHaveLength(1)
  })

  it('treats an unreadable success answer as an error, not as data', async () => {
    reply(200, '<html>proxy page</html>')
    await expect(api.staff.me()).rejects.toBeInstanceOf(ApiError)
  })

  it('gives a plain message when an error body is not JSON', async () => {
    reply(502, 'Bad gateway')
    await expect(api.staff.me()).rejects.toThrow('Something went wrong. Try again.')
  })
})
