import { useEffect, useMemo } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, evidenceFieldLabel, highlightRanges } from '../lib/evidence.js'
import { buildSegments } from '../lib/format.js'
import Chapter from './Chapter.jsx'
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
    <Chapter id="evidence-heading" title={t('evidence.heading')} testId="evidence">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-fg">{t('evidence.source')}</h3>
          <div
            dir="auto"
            data-testid="source-text"
            tabIndex={0}
            aria-label={t('evidence.source')}
            className="mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-xl bg-paper p-4 text-[15px] leading-relaxed text-paper-fg"
          >
            {segments.map((seg, i) => {
              if (seg.ids.length === 0) return <span key={i}>{seg.text}</span>
              const active = activeId && seg.ids.includes(activeId)
              return (
                <mark
                  key={i}
                  data-evidence-ids={seg.ids.join(' ')}
                  data-active={active ? 'true' : undefined}
                  className={`rounded px-0.5 text-paper-fg transition-colors ${active ? 'bg-mark-active ring-2 ring-focus' : 'bg-mark'}`}
                >
                  {seg.text}
                </mark>
              )
            })}
          </div>
        </div>

        <div className="min-w-0">
          <h3 className="text-sm font-medium text-fg">{t('evidence.verifiedList')}</h3>
          {groups.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t('evidence.noneVerified')}</p>
          ) : (
            <ul className="mt-2 divide-y divide-line border-y border-line" data-testid="verified-evidence">
              {groups.map((g) => {
                const ids = g.items.map((it) => it.id)
                const pressed = ids.includes(activeId)
                return (
                  <li key={g.key}>
                    <button
                      type="button"
                      onClick={() => onActivate(ids[0])}
                      aria-pressed={pressed}
                      className={`w-full px-2 py-3 text-start transition-colors ${pressed ? 'bg-mark' : 'hover:bg-subtle'}`}
                    >
                      <span className="flex items-start justify-between gap-2">
                        <span className="text-xs text-muted">
                          {g.items.map((it) => evidenceFieldLabel(t, it, billing)).join(' · ')}
                        </span>
                        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-link">
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
    </Chapter>
  )
}
