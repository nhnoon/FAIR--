import { describe, expect, it, vi } from 'vitest'
import { analyzeOffer, apiBaseUrl, getHealth, liveStatus } from '../api/client.js'
import { fakeResponse, liveResponse } from './helpers.jsx'

const req = { terms: 'T', expectation: 'E', language: 'ar' }

describe('apiBaseUrl', () => {
  it('defaults to same origin and strips trailing slashes', () => {
    expect(apiBaseUrl('')).toBe('')
    expect(apiBaseUrl(undefined)).toBe('')
    expect(apiBaseUrl('https://api.example.com//')).toBe('https://api.example.com')
  })
  it.each(['not a url', 'ftp://x.example', 'https://user:pw@x.example', 'https://x.example/?k=1'])(
    'rejects unsafe or invalid value %s',
    (v) => {
      expect(() => apiBaseUrl(v)).toThrow()
    },
  )
})

describe('analyzeOffer', () => {
  it('POSTs the exact backend contract to same-origin /api/analyze with no credentials', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(200, liveResponse().body))
    const body = await analyzeOffer(req, { fetchImpl })
    expect(body.verdict).toBe('CONTRADICTION')
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('/api/analyze')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ terms: 'T', expectation: 'E', language: 'ar' })
    expect(Object.keys(init.headers).map((h) => h.toLowerCase())).not.toContain('authorization')
  })

  it.each([
    [503, 'model_not_configured'],
    [503, 'live_calls_disabled'],
    [502, 'model_invalid_response'],
    [504, 'model_timeout'],
    [422, 'invalid_request'],
  ])('maps HTTP %s with backend error code %s', async (status, code) => {
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(status, { error: { code, message: 'm', details: [] } }))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code, status, message: 'm' })
  })

  it('reports an unreachable backend (proxy error without JSON) as network', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(502))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code: 'network', status: 502 })
  })

  it('reports fetch failure as network', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code: 'network' })
  })

  it('times out and aborts the request', async () => {
    let seenSignal
    const fetchImpl = vi.fn(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          seenSignal = init.signal
          init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    await expect(analyzeOffer(req, { fetchImpl, timeoutMs: 20 })).rejects.toMatchObject({ code: 'timeout' })
    expect(seenSignal.aborted).toBe(true)
  })

  it('distinguishes user cancellation from timeout', async () => {
    const controller = new AbortController()
    const fetchImpl = vi.fn(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    const p = analyzeOffer(req, { fetchImpl, signal: controller.signal })
    controller.abort()
    await expect(p).rejects.toMatchObject({ code: 'cancelled' })
  })

  it('uses VITE_API_BASE_URL for a separately deployed backend, without cookies', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://fair-api.example.com/')
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(200, liveResponse().body))
    await analyzeOffer(req, { fetchImpl })
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('https://fair-api.example.com/api/analyze')
    expect(init.credentials).toBe('omit')
    vi.unstubAllEnvs()
  })

  it('reports a CORS rejection (fetch TypeError) as network', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://fair-api.example.com')
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code: 'network' })
    vi.unstubAllEnvs()
  })

  it('maps the backend rate limit to rate_limited', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(429, { error: { code: 'rate_limited', message: 'x' } }))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code: 'rate_limited', status: 429 })
  })

  it('getHealth returns null instead of throwing when unreachable or malformed', async () => {
    expect(await getHealth({ fetchImpl: vi.fn().mockRejectedValue(new TypeError('x')) })).toBeNull()
    expect(await getHealth({ fetchImpl: vi.fn().mockResolvedValue(fakeResponse(500, {})) })).toBeNull()
    expect(await getHealth({ fetchImpl: vi.fn().mockResolvedValue(fakeResponse(200, { status: 'ok' })) })).toBeNull()
    const ok = { status: 'ok', model: 'm', model_configured: true, live_calls_enabled: false }
    expect(await getHealth({ fetchImpl: vi.fn().mockResolvedValue(fakeResponse(200, ok)) })).toEqual(ok)
  })

  it.each([
    [null, 'unreachable'],
    [{ model_configured: false, live_calls_enabled: true }, 'not_configured'],
    [{ model_configured: true, live_calls_enabled: false }, 'disabled'],
    [{ model_configured: true, live_calls_enabled: true }, 'live'],
  ])('liveStatus(%o) = %s', (health, expected) => {
    expect(liveStatus(health)).toBe(expected)
  })

  it('rejects a 200 response that is not a valid analysis', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(fakeResponse(200, { verdict: 'MAYBE' }))
    await expect(analyzeOffer(req, { fetchImpl })).rejects.toMatchObject({ code: 'unknown' })
  })
})
