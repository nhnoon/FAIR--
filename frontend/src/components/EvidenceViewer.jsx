import { useEffect, useMemo } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, evidenceFieldLabel, highlightRanges } from '../lib/evidence.js'
import { buildSegments } from '../lib/format.js'
import { CheckIcon } from './icons.jsx'

/** One entry per distinct quoted span, listing every finding it supports (no repeated quotes). */
export function groupVerified(verified) {
  const groups = new Map()
  for (const it of verified) {
    const key = Number.isInteger(it.evidence.start) ? `${it.evidence.start}-${it.evidence.end}` : `q:${it.evidence.quote}`
    if (!groups.has(key)) groups.set(key, { key, quote: it.evidence.quote, start: it.evidence.start ?? Infinity, items: [] })
    groups.get(key).items.push(it)
  }
  return [...groups.values()].sort((a, b) => a.start - b.start)
}

// Verified evidence only. Rejected claims are shown separately (UncertaintyPanel).
export default function EvidenceViewer({ data, sourceText, activeId, onActivate }) {
  const { t } = useLang()
  const { verified } = useMemo(() => collectEvidence(data), [data])
  const groups = useMemo(() => groupVerified(verified), [verified])
  const segments = useMemo(() => buildSegments(sourceText, highlightRanges(verified)), [sourceText, verified])
  const billing = data.extracted_terms?.billing_period

  // Several findings can share one sentence, so look the finding up among each mark's ids.
  useEffect(() => {
    if (!activeId) return
    document.querySelector(`[data-evidence-ids~="${activeId}"]`)?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [activeId])

  return (
    <section aria-labelledby="evidence-heading" className="card p-5 sm:p-6">
      <h2 id="evidence-heading" className="section-title">
        {t('evidence.heading')}
      </h2>
      <p className="mt-0.5 text-sm text-muted">{t('evidence.subtitle')}</p>

      <div className="mt-4 grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-fg">{t('evidence.source')}</h3>
          <div
            dir="auto"
            data-testid="source-text"
            tabIndex={0}
            aria-label={t('evidence.source')}
            className="mt-2 max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded-xl border border-line bg-subtle p-4 text-[15px] leading-relaxed text-fg"
          >
            {segments.map((seg, i) => {
              if (seg.ids.length === 0) return <span key={i}>{seg.text}</span>
              const active = activeId && seg.ids.includes(activeId)
              return (
                <mark
                  key={i}
                  data-evidence-ids={seg.ids.join(' ')}
                  data-active={active ? 'true' : undefined}
                  className={`rounded px-0.5 text-fg underline decoration-link/50 decoration-2 underline-offset-4 ${
                    active ? 'bg-mark-active ring-2 ring-focus' : 'bg-mark'
                  }`}
                >
                  {seg.text}
                </mark>
              )
            })}
          </div>
        </div>

        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-fg">{t('evidence.verifiedList')}</h3>
          {groups.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t('evidence.noneVerified')}</p>
          ) : (
            <ul className="mt-2 space-y-2" data-testid="verified-evidence">
              {groups.map((g) => {
                const ids = g.items.map((it) => it.id)
                const pressed = ids.includes(activeId)
                return (
                  <li key={g.key}>
                    <button
                      type="button"
                      onClick={() => onActivate(ids[0])}
                      aria-pressed={pressed}
                      className={`w-full rounded-xl border p-3 text-start transition-colors ${
                        pressed ? 'border-focus bg-mark' : 'border-line bg-surface hover:bg-subtle'
                      }`}
                    >
                      <span className="flex items-start justify-between gap-2">
                        <span className="text-xs font-semibold text-muted">
                          {g.items.map((it) => evidenceFieldLabel(t, it, billing)).join(' · ')}
                        </span>
                        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-link">
                          <CheckIcon width={14} height={14} />
                          {t('evidence.verified')}
                        </span>
                      </span>
                      <q dir="auto" className="mt-1 block break-words text-sm text-fg">
                        {g.quote}
                      </q>
                      <span className="sr-only">{t('evidence.showInText')}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}
