import { forwardRef, useLayoutEffect, useRef } from 'react'
import { LIMITS } from '../api/client.js'
import { SAVED_EXAMPLES, exampleTitle } from '../examples/index.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { ArrowIcon, Spinner } from './icons.jsx'

const TextArea = forwardRef(function TextArea({ id, label, error, value, onChange, max, placeholder, rows }, ref) {
  const { t } = useLang()
  const errorId = `${id}-error`
  const countId = `${id}-count`
  const over = value.length > max
  const showCount = value.length >= max * 0.9 // the limit is out of mind until it is close
  const inner = useRef(null)

  // Starts small and grows with the text; a long contract scrolls inside a capped box.
  useLayoutEffect(() => {
    const el = inner.current
    if (!el) return
    el.style.height = 'auto'
    if (el.scrollHeight) el.style.height = `${el.scrollHeight + 2}px`
  }, [value])

  return (
    <div className="w-full min-w-0">
      <label htmlFor={id} className="label">
        {label}
      </label>
      <textarea
        ref={(node) => {
          inner.current = node
          if (ref) ref.current = node
        }}
        id={id}
        name={id}
        dir="auto"
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={[error ? errorId : null, showCount ? countId : null].filter(Boolean).join(' ') || undefined}
        className={`field mt-2 max-h-[22rem] resize-none break-words ${error ? 'field-invalid' : ''}`}
      />
      {error || showCount ? (
        <div className="mt-1.5 flex items-start justify-between gap-3 text-xs">
          <p id={errorId} className="font-medium text-contra-fg" role={error ? 'alert' : undefined}>
            {error || ''}
          </p>
          {showCount ? (
            <p id={countId} className={`shrink-0 tabular-nums ${over ? 'font-semibold text-contra-fg' : 'text-muted'}`}>
              {t('form.counter', { count: value.length.toLocaleString('en-US'), max: max.toLocaleString('en-US') })}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
})

/** Honest note about availability, with a way forward. Only "live" may mention Muse Spark as the engine. */
export function AvailabilityNote({ status, onRetry, onOpenExample }) {
  const { t } = useLang()
  // Replay is introduced by the recorded examples themselves (ExamplesList), not by a banner.
  if (status === 'checking' || status === 'replay') return null
  if (status === 'live') {
    return (
      <p className="text-xs text-muted" data-testid="availability" data-status={status}>
        {t('analyze.poweredBy')}
      </p>
    )
  }
  return (
    <div className="rounded-xl bg-unknown-bg px-4 py-3 text-sm text-unknown-fg" role="status" data-testid="availability" data-status={status}>
      <p>{t(`analyze.unavailable.${status}`)}</p>
      <p className="mt-1 flex flex-wrap gap-x-4">
        {status === 'unreachable' ? (
          <button type="button" className="inline-flex min-h-[32px] items-center rounded font-medium underline underline-offset-4" onClick={onRetry}>
            {t('analyze.retryConnection')}
          </button>
        ) : null}
        <button type="button" className="inline-flex min-h-[32px] items-center rounded font-medium underline underline-offset-4" onClick={() => onOpenExample(SAVED_EXAMPLES[0].id)}>
          {t('analyze.openExample')}
        </button>
      </p>
    </div>
  )
}

/** In replay mode these are the only inputs that answer, so they lead the page and say so. */
function ExamplesList({ onChoose, recorded }) {
  const { t, lang } = useLang()
  return (
    <div className="min-w-0" data-testid="examples">
      {recorded ? (
        <>
          <h2 className="text-base font-semibold text-fg" id="examples-heading">
            {t('examples.recordedTitle')}
          </h2>
          <p className="mt-0.5 text-sm text-muted" role="status" data-testid="availability" data-status="replay">
            {t('analyze.unavailable.replay')}
          </p>
        </>
      ) : (
        <p className="text-sm font-medium text-muted" id="examples-heading">
          {t('examples.title')}
        </p>
      )}
      <ul className="mt-2 flex flex-wrap gap-2" aria-labelledby="examples-heading">
        {SAVED_EXAMPLES.map((ex) => (
          <li key={ex.id} className="min-w-0">
            <button type="button" onClick={() => onChoose(ex.id)} data-testid={`example-${ex.id}`} className="inline-flex min-h-[40px] items-center rounded-full border border-line bg-surface px-4 text-start text-sm font-medium text-fg transition-colors hover:border-focus">
              {exampleTitle(ex.id, lang)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function AnalyzeForm({ terms, expectation, onTermsChange, onExpectationChange, errors, loading, onSubmit, onCancel, onClear, termsRef, expectationRef, status, onRetryConnection, onOpenExample, onChooseExample }) {
  const { t } = useLang()
  return (
    <div className="space-y-5">
      <AvailabilityNote status={status} onRetry={onRetryConnection} onOpenExample={onOpenExample} />
      {status === 'replay' ? <ExamplesList recorded onChoose={onChooseExample} /> : null}
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (!loading) onSubmit()
        }}
        className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-lift sm:p-7"
        aria-label={t('analyze.title')}
      >
        <TextArea ref={termsRef} id="terms" label={t('form.termsLabel')} placeholder={t('form.termsPlaceholder')} error={errors.terms} value={terms} onChange={onTermsChange} max={LIMITS.terms} rows={5} />
        <TextArea ref={expectationRef} id="expectation" label={t('form.expectationLabel')} placeholder={t('form.expectationPlaceholder')} error={errors.expectation} value={expectation} onChange={onExpectationChange} max={LIMITS.expectation} rows={2} />
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className="btn-primary btn-cta flex-1" disabled={loading} aria-busy={loading}>
            {loading ? <Spinner width={18} height={18} /> : null}
            {loading ? t('form.analyzing') : t('form.analyze')}
            {loading ? null : <ArrowIcon width={17} height={17} />}
          </button>
          {loading ? (
            <button type="button" className="btn-ghost btn-cta" onClick={onCancel}>
              {t('form.cancel')}
            </button>
          ) : terms || expectation ? (
            <button type="button" className="btn-ghost btn-cta" onClick={onClear}>
              {t('form.clear')}
            </button>
          ) : null}
        </div>
      </form>
      {status === 'replay' ? null : <ExamplesList onChoose={onChooseExample} />}
    </div>
  )
}
