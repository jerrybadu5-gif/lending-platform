import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, staffHeaders } from '../../src/api/client'

function reply(status: number, body: string) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(status === 204 ? null : body, { status, headers: { 'Content-Type': 'application/json' } })))
}

afterEach(async () => {
  vi.restoreAllMocks()
  reply(204, '')
  await api.staff.logout().catch(() => {})
  sessionStorage.clear()
  vi.unstubAllGlobals()
})

describe('api client', () => {
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

  it('keeps the status when an error body is JSON null', async () => {
    reply(401, 'null')
    const err = await api.staff.me().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(401)
  })

  it('gives a plain message when an error body is not JSON', async () => {
    reply(502, 'Bad gateway')
    await expect(api.staff.me()).rejects.toThrow('Something went wrong. Try again.')
  })
})

async function signIn() {
  reply(200, JSON.stringify({ username: 'officer', display_name: 'Officer', roles: [], tab_token: 'random-tab-credential' }))
  return api.staff.login('officer', 'password')
}

it('sends the login credential on staff requests and downloads only', async () => {
  const user = await signIn()
  expect(user).not.toHaveProperty('tab_token')
  const headers = { 'X-MCL-User': 'officer', 'X-MCL-Tab': 'random-tab-credential' }
  expect(staffHeaders('/api/staff/loans/1/schedule.pdf')).toEqual(headers)
  expect(staffHeaders('/api/portal/home')).toEqual({})
  reply(200, '{}')
  await api.staff.me()
  expect(fetch).toHaveBeenCalledWith('/api/staff/me', expect.objectContaining({ headers }))
  reply(204, '')
  await api.staff.logout()
  expect(fetch).toHaveBeenCalledWith('/api/staff/logout', expect.objectContaining({ headers }))
  expect(staffHeaders('/api/staff/me')).toEqual({})
})

it('keeps the tab credential in memory when storage cannot be written', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  await signIn()
  expect(staffHeaders('/api/staff/me')['X-MCL-Tab']).toBe('random-tab-credential')
})
