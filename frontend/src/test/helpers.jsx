import { render } from '@testing-library/react'
import { vi } from 'vitest'
import App from '../App.jsx'
import { LanguageProvider } from '../i18n/LanguageContext.jsx'
import { ThemeProvider } from '../theme/ThemeContext.jsx'
import samplesFile from '../samples/samples.json'

export const sample = (id) => structuredClone(samplesFile.samples.find((s) => s.id === id))

/** A response shaped exactly like the backend's AnalyzeResponse (taken from a pipeline-built fixture). */
export function liveResponse(id = 'trial-autorenew') {
  const s = sample(id)
  return { terms: s.terms, expectation: s.expectation, body: { ...s.response, model: 'muse-spark-1.3' } }
}

export const HEALTH = {
  notConfigured: { status: 'ok', model: 'muse-spark-1.3', base_url: 'https://api.meta.ai/v1', model_configured: false, live_calls_enabled: false },
  disabled: { status: 'ok', model: 'muse-spark-1.3', base_url: 'https://api.meta.ai/v1', model_configured: true, live_calls_enabled: false },
  live: { status: 'ok', model: 'muse-spark-1.3', base_url: 'https://api.meta.ai/v1', model_configured: true, live_calls_enabled: true },
}

export function fakeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError('no body')
      return body
    },
  }
}

/**
 * Stub fetch by URL: /api/health always answers with `health` (null = unreachable);
 * /api/analyze answers with the queued responses in order.
 */
export function mockFetchWith(health, ...responses) {
  const queue = [...responses]
  const fn = vi.fn(async (url) => {
    if (String(url).endsWith('/api/health')) {
      if (health === null) throw new TypeError('Failed to fetch')
      return fakeResponse(200, health)
    }
    if (!queue.length) throw new Error(`unexpected request: ${url}`)
    return queue.shift()
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

export function mockFetch(...responses) {
  return mockFetchWith(HEALTH.notConfigured, ...responses)
}

export const analyzeCalls = (fn) => fn.mock.calls.filter(([url]) => String(url).endsWith('/api/analyze'))

// The app opens on the home page; most tests start on the form, which is what the hash says here.
export function renderApp(lang = 'en', hash = '#/analyze') {
  if (!window.location.hash) window.history.replaceState(null, '', hash)
  return render(
    <ThemeProvider>
      <LanguageProvider initialLang={lang}>
        <App />
      </LanguageProvider>
    </ThemeProvider>,
  )
}
