import { forwardRef } from 'react'
import { LIMITS } from '../api/client.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { AlertIcon, ArrowIcon, Spinner } from './icons.jsx'

const TextArea = forwardRef(function TextArea({ id, label, help, error, value, onChange, max, placeholder, rows }, ref) {
  const { t } = useLang()
  const helpId = `${id}-help`
  const errorId = `${id}-error`
  const countId = `${id}-count`
  const over = value.length > max
  return (
    <div className="flex w-full min-w-0 flex-col">
      <label htmlFor={id} className="label">
        {label}
      </label>
      <p id={helpId} className="mt-0.5 text-sm text-muted">
        {help}
      </p>
      <textarea
        ref={ref}
        id={id}
        name={id}
        dir="auto"
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={[helpId, error ? errorId : null, countId].filter(Boolean).join(' ')}
        className={`field mt-2 max-h-[32rem] min-h-[7rem] flex-1 resize-y break-words ${error ? 'field-invalid' : ''}`}
      />
      <div className="mt-1.5 flex items-start justify-between gap-3 text-xs">
        <p id={errorId} className="font-medium text-contra-fg" role={error ? 'alert' : undefined}>
          {error || ''}
        </p>
        <p id={countId} className={`shrink-0 tabular-nums ${over ? 'font-semibold text-contra-fg' : 'text-muted'}`}>
          {t('form.counter', { count: value.length.toLocaleString('en-US'), max: max.toLocaleString('en-US') })}
        </p>
      </div>
    </div>
  )
})

/** Compact, honest note about live availability. Only "live" may mention Muse Spark as the engine. */
export function AvailabilityNote({ status, model }) {
  const { t } = useLang()
  if (status === 'checking') return null
  if (status === 'live') {
    return (
      <p className="text-xs text-muted" data-testid="availability" data-status={status}>
        {t('analyze.poweredBy')}
        {model ? (
          <span dir="ltr" className="mx-1 font-mono">
            ({model})
          </span>
        ) : null}
      </p>
    )
  }
  return (
    <p
      className="flex gap-2 rounded-xl border border-unknown-line bg-unknown-bg px-3 py-2.5 text-sm text-unknown-fg"
      data-testid="availability"
      data-status={status}
    >
      <AlertIcon width={16} height={16} className="mt-0.5 shrink-0" />
      <span>{t(`analyze.unavailable.${status}`)}</span>
    </p>
  )
}

export default function AnalyzeForm({
  terms,
  expectation,
  onTermsChange,
  onExpectationChange,
  errors,
  loading,
  onSubmit,
  onCancel,
  onClear,
  termsRef,
  expectationRef,
  status,
  model,
}) {
  const { t } = useLang()
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        if (!loading) onSubmit()
      }}
      className="card p-5 sm:p-6"
      aria-label={t('analyze.title')}
    >
      <div className="grid gap-5 lg:grid-cols-5 lg:gap-6">
        <div className="flex lg:col-span-3">
          <TextArea
            ref={termsRef}
            id="terms"
            label={t('form.termsLabel')}
            help={t('form.termsHelp')}
            placeholder={t('form.termsPlaceholder')}
            error={errors.terms}
            value={terms}
            onChange={onTermsChange}
            max={LIMITS.terms}
            rows={11}
          />
        </div>
        <div className="flex flex-col gap-4 lg:col-span-2">
          <TextArea
            ref={expectationRef}
            id="expectation"
            label={t('form.expectationLabel')}
            help={t('form.expectationHelp')}
            placeholder={t('form.expectationPlaceholder')}
            error={errors.expectation}
            value={expectation}
            onChange={onExpectationChange}
            max={LIMITS.expectation}
            rows={4}
          />
          <AvailabilityNote status={status} model={model} />
          <div className="mt-auto flex flex-wrap items-center gap-2">
            <button type="submit" className="btn-primary flex-1 text-[15px]" disabled={loading} aria-busy={loading}>
              {loading ? <Spinner width={18} height={18} /> : null}
              {loading ? t('form.analyzing') : t('form.analyze')}
              {loading ? null : <ArrowIcon width={16} height={16} />}
            </button>
            {loading ? (
              <button type="button" className="btn-secondary" onClick={onCancel}>
                {t('form.cancel')}
              </button>
            ) : (
              <button type="button" className="btn-ghost" onClick={onClear} disabled={!terms && !expectation}>
                {t('form.clear')}
              </button>
            )}
          </div>
          <p className="text-xs text-muted">{t('form.privacy')}</p>
        </div>
      </div>
    </form>
  )
}
