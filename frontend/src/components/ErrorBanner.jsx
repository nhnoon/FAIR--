import { useEffect, useRef } from 'react'
import { REQUEST_TIMEOUT_MS } from '../api/client.js'
import { lookup, useLang } from '../i18n/LanguageContext.jsx'
import { AlertIcon } from './icons.jsx'

const CONFIG_CODES = new Set(['model_not_configured', 'live_calls_disabled'])

export default function ErrorBanner({ error, onRetry, onDismiss }) {
  const { t, lang } = useLang()
  const code = lookup(lang, `errors.${error.code}.title`) ? error.code : 'unknown'
  const isConfig = CONFIG_CODES.has(error.code)
  // Nothing went wrong with the user's text in these cases, so they read as a notice and carry no code.
  // The same text would fail again in a recorded demo, so it offers no retry either.
  const demoLimit = error.code === 'replay_unsupported'
  const isNotice = isConfig || demoLimit || error.code === 'network'
  const tone = isNotice ? 'border-line bg-surface text-fg' : 'border-contra-line bg-contra-bg text-contra-fg'
  const ref = useRef(null)
  // On a phone the banner renders below the form, out of sight of the button that was pressed.
  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [error])
  return (
    <div ref={ref} role="alert" className={`rise rounded-xl border p-4 ${tone}`}>
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
          {isNotice ? null : (
            <p className="mt-2 text-xs opacity-80">
              {t('errors.code', { code: error.code })}
              {error.status ? ` · HTTP ${error.status}` : ''}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {onRetry && !isConfig && !demoLimit ? (
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
