import { useEffect, useRef } from 'react'
import { REQUEST_TIMEOUT_MS } from '../api/client.js'
import { lookup, useLang } from '../i18n/LanguageContext.jsx'
import { AlertIcon } from './icons.jsx'

const CONFIG_CODES = new Set(['model_not_configured', 'live_calls_disabled'])

export default function ErrorBanner({ error, onRetry, onDismiss }) {
  const { t, lang } = useLang()
  const code = lookup(lang, `errors.${error.code}.title`) ? error.code : 'unknown'
  const isConfig = CONFIG_CODES.has(error.code)
  const tone = isConfig ? 'border-unknown-line bg-unknown-bg text-unknown-fg' : 'border-contra-line bg-contra-bg text-contra-fg'
  const ref = useRef(null)
  // On a phone the banner renders below the form, out of sight of the button that was pressed.
  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [error])
  return (
    <div ref={ref} role="alert" className={`rounded-2xl border p-5 ${tone}`}>
      <div className="flex gap-3">
        <AlertIcon className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{t(`errors.${code}.title`)}</h2>
          <p className="mt-1 text-sm">{t(`errors.${code}.body`, { seconds: Math.round(REQUEST_TIMEOUT_MS / 1000) })}</p>
          {/* Raw server text is developer-facing English; show it only when we have no translation for the code. */}
          {code === 'unknown' && error.message && error.message !== error.code ? (
            <p dir="ltr" lang="en" className="mt-2 break-words text-start text-xs opacity-80">
              {error.message}
            </p>
          ) : null}
          <p className="mt-2 text-xs opacity-80">
            {t('errors.code', { code: error.code })}
            {error.status ? ` · HTTP ${error.status}` : ''}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {onRetry && !isConfig ? (
              <button type="button" className="btn-secondary" onClick={onRetry}>
                {t('errors.retry')}
              </button>
            ) : null}
            <button type="button" className="btn-secondary" onClick={onDismiss}>
              {t('errors.dismiss')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
