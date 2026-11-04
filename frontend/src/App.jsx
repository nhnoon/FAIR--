import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, LIMITS, analyzeOffer, getHealth, liveStatus } from './api/client.js'
import AboutView from './components/AboutView.jsx'
import AnalyzeForm from './components/AnalyzeForm.jsx'
import AppShell, { VIEWS } from './components/AppShell.jsx'
import ErrorBanner from './components/ErrorBanner.jsx'
import HomeView from './components/HomeView.jsx'
import ResultsView from './components/ResultsView.jsx'
import { ArrowIcon, Spinner } from './components/icons.jsx'
import { findExample } from './examples/index.js'
import { useLang } from './i18n/LanguageContext.jsx'

/** Client-side checks mirroring backend AnalyzeRequest. Returns {field: {key, vars}}. */
export function validate({ terms, expectation }) {
  const errors = {}
  const max = (n) => ({ max: n.toLocaleString('en-US') })
  if (!terms) errors.terms = { key: 'form.errors.termsRequired' }
  else if (terms.length > LIMITS.terms) errors.terms = { key: 'form.errors.termsTooLong', vars: max(LIMITS.terms) }
  if (!expectation) errors.expectation = { key: 'form.errors.expectationRequired' }
  else if (expectation.length > LIMITS.expectation)
    errors.expectation = { key: 'form.errors.expectationTooLong', vars: max(LIMITS.expectation) }
  return errors
}

// Views live in the URL hash (#/home, #/analyze, #/results, #/about): no reload, back button works,
// no routing dependency. State lives here, so switching views never loses input or results.
function viewFromHash() {
  const m = window.location.hash.match(/^#\/([a-z]+)$/)
  return m && VIEWS.includes(m[1]) ? m[1] : null
}

export default function App({ analyze = analyzeOffer }) {
  const { t, lang } = useLang()
  const [view, setView] = useState(() => {
    const initial = viewFromHash()
    if (initial === 'results') return 'analyze' // nothing to show yet in a fresh session
    return initial || 'home'
  })
  const [terms, setTerms] = useState('')
  const [expectation, setExpectation] = useState('')
  const [errorKeys, setErrorKeys] = useState({}) // field -> {key, vars} so messages re-translate on language switch
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null) // { kind: 'live' | 'preview', id, data, terms, expectation }
  const [status, setStatus] = useState('checking')
  const abortRef = useRef(null)
  const termsRef = useRef(null)
  const expectationRef = useRef(null)
  const headingRef = useRef(null)
  const resultRef = useRef(null)
  const firstRender = useRef(true)
  const mounted = useRef(false)
  resultRef.current = result

  const go = useCallback((next) => {
    if (next === 'results' && !resultRef.current) return
    setView(next)
    if (window.location.hash !== `#/${next}`) window.location.hash = `/${next}`
  }, [])

  // Canonical default route, and browser back/forward support.
  useEffect(() => {
    if (viewFromHash() !== view) window.history.replaceState(null, '', `#/${view}`)
    const onHash = () => {
      const next = viewFromHash()
      if (!next) return
      if (next === 'results' && !resultRef.current) {
        window.history.replaceState(null, '', '#/analyze')
        setView('analyze')
        return
      }
      setView(next)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Move focus to the new view's heading (not on first load).
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    headingRef.current?.focus({ preventScroll: true })
    window.scrollTo?.({ top: 0 })
  }, [view, result])

  // Truthful system status. Configuration only; it never claims a call succeeded.
  const checkHealth = useCallback(() => {
    setStatus('checking')
    return getHealth().then((h) => {
      if (mounted.current) setStatus(liveStatus(h))
    })
  }, [])

  useEffect(() => {
    mounted.current = true
    checkHealth()
    return () => {
      mounted.current = false
    }
  }, [checkHealth])

  useEffect(() => () => abortRef.current?.abort(), [])

  // Development only: ?sample=<id> opens a labeled synthetic preview. The fixture file is
  // not part of production builds (this branch is removed when import.meta.env.DEV is false).
  useEffect(() => {
    if (!import.meta.env.DEV) return undefined
    const id = new URLSearchParams(window.location.search).get('sample')
    if (!id) return undefined
    let active = true
    import('./samples/samples.json').then(({ default: file }) => {
      const s = file.samples.find((x) => x.id === id)
      if (!s || !active) return
      setResult({ kind: 'preview', id: `preview-${id}`, sampleId: id, data: s.response, terms: s.terms, expectation: s.expectation })
      resultRef.current = true
      go('results')
    })
    return () => {
      active = false
    }
  }, [go])

  // Always labelled as saved. It works with no server, because the result was stored at build time.
  function openSaved(id) {
    const ex = findExample(id)
    setTerms(ex.terms)
    setExpectation(ex.expectation)
    setErrorKeys({})
    setError(null)
    setResult({ kind: 'saved', id: `saved-${id}-${Date.now()}`, data: ex.response, terms: ex.terms, expectation: ex.expectation })
    resultRef.current = true
    go('results')
  }

  // A running server analyses it for real (replay answers from its saved outputs). Otherwise, open the saved result.
  function chooseExample(id) {
    if (status !== 'replay' && status !== 'live') return openSaved(id)
    const ex = findExample(id)
    setTerms(ex.terms)
    setExpectation(ex.expectation)
    setErrorKeys({})
    setError(null)
    return undefined
  }

  async function submit() {
    const payload = { terms: terms.trim(), expectation: expectation.trim(), language: lang }
    const keys = validate(payload)
    setErrorKeys(keys)
    if (keys.terms || keys.expectation) {
      ;(keys.terms ? termsRef : expectationRef).current?.focus()
      return
    }

    setError(null)
    setResult(null) // never keep an earlier result next to a new request's outcome
    setLoading(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const data = await analyze(payload, { signal: controller.signal })
      // Evidence offsets refer to the trimmed text that was actually sent.
      setResult({ kind: 'live', id: `live-${Date.now()}`, data, terms: payload.terms, expectation: payload.expectation })
      resultRef.current = true
      go('results')
    } catch (e) {
      let err = e instanceof ApiError ? e : new ApiError('unknown')
      // The replay server answers only its saved cases; say that, not that a service is down.
      if (status === 'replay' && err.code === 'model_unavailable') err = new ApiError('replay_unsupported')
      if (err.code === 'cancelled') return
      if (err.code === 'network') checkHealth()
      if (err.code === 'invalid_request' && Array.isArray(err.details)) {
        const serverKeys = {}
        err.details.forEach((d) => {
          const field = String(d.field || '').split('.')[0]
          if ((field === 'terms' || field === 'expectation') && !serverKeys[field]) serverKeys[field] = { raw: d.message }
        })
        setErrorKeys(serverKeys)
      }
      setError(err)
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setLoading(false)
    }
  }

  const fieldErrors = Object.fromEntries(
    Object.entries(errorKeys).map(([field, e]) => [field, e.raw ? t('form.errors.serverField', { message: e.raw }) : t(e.key, e.vars)]),
  )

  return (
    <AppShell
      view={view}
      onNavigate={go}
      hasResult={!!result}
      status={status}
    >
      {view === 'home' ? <HomeView ref={headingRef} onStart={() => go('analyze')} onOpenExample={openSaved} /> : null}

      {view === 'analyze' ? (
        <div className="page max-w-3xl space-y-6 pb-16 pt-8 sm:pt-12" data-testid="view-analyze">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 ref={headingRef} tabIndex={-1} className="text-3xl font-semibold tracking-tight text-fg focus:outline-none sm:text-4xl">
                {t('analyze.title')}
              </h1>
            </div>
            {result ? (
              <button type="button" onClick={() => go('results')} className="btn-ghost text-link">
                {t('analyze.latestResult')}
                <ArrowIcon width={16} height={16} />
              </button>
            ) : null}
          </div>

          <AnalyzeForm
            terms={terms}
            expectation={expectation}
            onTermsChange={setTerms}
            onExpectationChange={setExpectation}
            errors={fieldErrors}
            loading={loading}
            onSubmit={submit}
            onCancel={() => abortRef.current?.abort()}
            onClear={() => {
              setTerms('')
              setExpectation('')
              setErrorKeys({})
            }}
            termsRef={termsRef}
            expectationRef={expectationRef}
            status={status}
            onRetryConnection={checkHealth}
            onOpenExample={openSaved}
            onChooseExample={chooseExample}
          />

          <div aria-live="polite" aria-busy={loading} className="space-y-4">
            {error ? <ErrorBanner error={error} onRetry={submit} onDismiss={() => setError(null)} /> : null}
            {loading ? (
              <div className="flex items-center gap-4 rounded-2xl border border-line bg-surface p-4" data-testid="loading">
                <Spinner className="text-link" width={24} height={24} />
                <div>
                  <p className="font-medium text-fg">{t('states.loadingTitle')}</p>
                  <p className="text-sm text-muted">{t('states.loadingBody')}</p>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {view === 'results' ? (
        <div data-testid="view-results">
          <ResultsView
            ref={headingRef}
            key={result?.id || 'empty'}
            result={result}
            onEdit={() => go('analyze')}
            onNew={() => {
              setTerms('')
              setExpectation('')
              setErrorKeys({})
              go('analyze')
            }}
            onClosePreview={() => {
              setResult(null)
              resultRef.current = null
              go('analyze')
            }}
          />
        </div>
      ) : null}

      {view === 'about' ? (
        <div data-testid="view-about">
          <AboutView ref={headingRef} />
        </div>
      ) : null}
    </AppShell>
  )
}
