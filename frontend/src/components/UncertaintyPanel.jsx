import { useMemo } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, evidenceFieldLabel, missingKeyTerms } from '../lib/evidence.js'
import { AlertIcon, CheckIcon, ChevronIcon, QuestionIcon, XIcon } from './icons.jsx'

// What FAIR could not confirm. The summary is always visible (material uncertainty is
// never hidden); the rejected-claim list is a disclosure, open by default when a
// rejected claim changed the verdict.
export default function UncertaintyPanel({ data }) {
  const { t, lang } = useLang()
  const { unverified } = useMemo(() => collectEvidence(data), [data])
  const missing = missingKeyTerms(data.extracted_terms)
  const costUncertain = data.cost.projections.some((p) => p.status !== 'complete')
  const billing = data.extracted_terms?.billing_period
  // Claims the terms do not settle are material uncertainty too.
  const unsettled = (data.claims || []).filter((c) => c.verdict === 'UNKNOWN').length
  const nothing = !missing.length && !unverified.length && !costUncertain && !unsettled
  const sep = lang === 'ar' ? '، ' : ', '

  return (
    <section
      aria-labelledby="uncertain-heading"
      data-testid="uncertain"
      className={`rounded-2xl border p-5 sm:p-6 ${nothing ? 'border-line bg-surface' : 'border-unknown-line bg-unknown-bg'}`}
    >
      <h2 id="uncertain-heading" className="section-title flex items-center gap-2">
        <QuestionIcon width={18} height={18} className={nothing ? 'text-link' : 'text-unknown-fg'} />
        {t('uncertain.title')}
      </h2>

      {nothing ? (
        <p className="mt-2 flex items-center gap-2 text-sm font-medium text-link">
          <CheckIcon width={16} height={16} />
          {t('uncertain.none')}
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5 text-sm text-unknown-fg">
          {unsettled ? (
            <li className="flex gap-2" data-testid="unsettled-claims">
              <QuestionIcon width={16} height={16} className="mt-0.5 shrink-0" />
              <span>{t('uncertain.unsettledLine', { n: unsettled })}</span>
            </li>
          ) : null}
          {missing.length ? (
            <li className="flex gap-2" data-testid="not-stated">
              <QuestionIcon width={16} height={16} className="mt-0.5 shrink-0" />
              <span>{t('uncertain.notStatedLine', { fields: missing.map((f) => t(`uncertain.fields.${f}`)).join(sep) })}</span>
            </li>
          ) : null}
          {unverified.length ? (
            <li className="flex gap-2">
              <XIcon width={16} height={16} className="mt-0.5 shrink-0" />
              <span>{t('uncertain.rejectedLine', { n: unverified.length })}</span>
            </li>
          ) : null}
          {costUncertain ? (
            <li className="flex gap-2">
              <AlertIcon width={16} height={16} className="mt-0.5 shrink-0" />
              <span>{t('uncertain.costLine')}</span>
            </li>
          ) : null}
        </ul>
      )}

      {unverified.length ? (
        <details className="group mt-4 rounded-xl border border-contra-line bg-surface" open={data.verdict_downgraded || undefined}>
          <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-2 rounded-xl px-4 text-sm font-semibold text-contra-fg">
            {t('uncertain.rejectedTitle')}
            <ChevronIcon width={16} height={16} className="transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4" data-testid="unverified-evidence">
            <p className="text-xs text-contra-fg">{t('uncertain.rejectedBody')}</p>
            <ul className="mt-3 space-y-2">
              {unverified.map((it) => (
                <li key={it.id} className="rounded-lg bg-contra-bg p-3 text-sm">
                  <span className="block text-xs font-semibold text-contra-fg">{evidenceFieldLabel(t, it, billing)}</span>
                  <span dir="auto" className="mt-1 block break-words text-muted line-through decoration-contra-solid/70">
                    {it.evidence?.quote ? `“${it.evidence.quote}”` : t('evidence.noQuote')}
                  </span>
                  <span className="mt-1 block text-xs font-medium text-contra-fg">
                    {t(`evidence.reasons.${it.evidence?.reason || 'quote_not_found_in_source'}`)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </details>
      ) : null}
    </section>
  )
}
