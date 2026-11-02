// Client for the FastAPI backend (contract: backend/app/schemas.py).
// No credentials are ever handled here: the Meta API key lives only on the backend.
//
// VITE_API_BASE_URL (build-time, public): absolute origin of a separately deployed
// backend, e.g. https://fair-api.example.com. Empty = same origin (/api via the Vite
// dev/preview proxy, or a reverse proxy in production).

export const LIMITS = { terms: 20000, expectation: 2000 }

export function apiBaseUrl(raw = import.meta.env.VITE_API_BASE_URL) {
  const value = (raw || '').trim()
  if (!value) return ''
  let url
  try {
    url = new URL(value)
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid absolute URL: "${value}"`)
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('VITE_API_BASE_URL must use http or https')
  }
  if (url.search || url.hash || url.username || url.password) {
    throw new Error('VITE_API_BASE_URL must not contain credentials, a query string, or a fragment')
  }
  return value.replace(/\/+$/, '')
}

export function apiUrl(path) {
  return `${apiBaseUrl()}${path}`
}
export const REQUEST_TIMEOUT_MS = 60_000 // backend: 45 s model timeout, no retries

const VERDICTS = new Set(['MATCH', 'CONTRADICTION', 'UNKNOWN'])

export class ApiError extends Error {
  constructor(code, { status = null, message = '', details = null } = {}) {
    super(message || code)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

/**
 * GET /api/health. Returns the body, or null if the server is unreachable or the
 * body is malformed. It reports configuration only: it does not prove the key works.
 */
export async function getHealth({ fetchImpl = globalThis.fetch, timeoutMs = 8000 } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetchImpl(apiUrl('/api/health'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      mode: 'cors',
      signal: controller.signal,
    })
    if (!res.ok) return null
    const body = await res.json()
    if (typeof body?.model_configured !== 'boolean' || typeof body?.live_calls_enabled !== 'boolean') return null
    return body
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

/** A replay server reports this model prefix. Its results are saved outputs, never live analysis. */
export const isReplayModel = (model) => String(model || '').startsWith('replay:')

/** replay | live | not_configured | disabled | unreachable, from a getHealth() result. */
export function liveStatus(health) {
  if (!health) return 'unreachable'
  if (isReplayModel(health.model)) return 'replay'
  if (!health.model_configured) return 'not_configured'
  if (!health.live_calls_enabled) return 'disabled'
  return 'live'
}

/** Minimal shape check so a malformed body is never rendered as a result. */
export function isAnalyzeResponse(body) {
  return (
    !!body &&
    VERDICTS.has(body.verdict) &&
    typeof body.explanation?.en === 'string' &&
    typeof body.explanation?.ar === 'string' &&
    !!body.extracted_terms &&
    Array.isArray(body.facts) &&
    Array.isArray(body.rejected_facts) &&
    Array.isArray(body.cost?.projections)
  )
}

export async function analyzeOffer(
  { terms, expectation, language },
  { timeoutMs = REQUEST_TIMEOUT_MS, signal, fetchImpl = globalThis.fetch } = {},
) {
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const onCancel = () => controller.abort()
  signal?.addEventListener('abort', onCancel)

  let res
  try {
    res = await fetchImpl(apiUrl('/api/analyze'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ terms, expectation, language }),
      signal: controller.signal,
      credentials: 'omit', // no cookies; the API is stateless
      mode: 'cors',
    })
  } catch {
    // A CORS rejection also lands here: browsers report it as a generic network failure.
    if (timedOut) throw new ApiError('timeout')
    if (signal?.aborted) throw new ApiError('cancelled')
    throw new ApiError('network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onCancel)
  }

  let body = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (!res.ok) {
    const err = body?.error
    if (err?.code) {
      throw new ApiError(err.code, { status: res.status, message: err.message, details: err.details ?? null })
    }
    // No JSON error from FastAPI: the dev proxy could not reach the backend.
    const code = [500, 502, 503, 504].includes(res.status) ? 'network' : 'unknown'
    throw new ApiError(code, { status: res.status })
  }
  if (!isAnalyzeResponse(body)) throw new ApiError('unknown', { status: res.status })
  return body
}
