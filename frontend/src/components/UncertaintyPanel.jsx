import { useMemo } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, evidenceFieldLabel, missingKeyTerms } from '../lib/evidence.js'
import Chapter from './Chapter.jsx'
import { AlertIcon, CheckIcon, ChevronIcon, QuestionIcon, XIcon } from './icons.jsx'

// What FAIR could not confirm. The summary is always visible (material uncertainty is
// never hidden); the rejected-claim list is a disclosure, open by default when a
// rejected claim changed the verdict.
export function hasUncertainty(data) {
  return !!(collectEvidence(data).unverified.length || missingKeyTerms(data.extracted_terms).length || data.cost.projections.some((p) => p.status !== 'complete') || (data.claims || []).some((c) => c.verdict === 'UNKNOWN'))
}

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
    <Chapter id="uncertain-heading" title={t('uncertain.title')} testId="uncertain">

      {nothing ? (
        <p className="flex items-center gap-2 text-sm font-medium text-fg">
          <CheckIcon width={16} height={16} />
          {t('uncertain.none')}
        </p>
      ) : (
        <ul className="space-y-2 text-sm text-fg">
          {unsettled ? (
            <li className="flex gap-2" data-testid="unsettled-claims">
              <QuestionIcon width={16} height={16} className="mt-0.5 shrink-0 text-unknown-fg" />
              <span>{t('uncertain.unsettledLine', { n: unsettled })}</span>
            </li>
          ) : null}
          {missing.length ? (
            <li className="flex gap-2" data-testid="not-stated">
              <QuestionIcon width={16} height={16} className="mt-0.5 shrink-0 text-unknown-fg" />
              <span>{t('uncertain.notStatedLine', { fields: missing.map((f) => t(`uncertain.fields.${f}`)).join(sep) })}</span>
            </li>
          ) : null}
          {unverified.length ? (
            <li className="flex gap-2">
              <XIcon width={16} height={16} className="mt-0.5 shrink-0 text-contra-fg" />
              <span>{t('uncertain.rejectedLine', { n: unverified.length })}</span>
            </li>
          ) : null}
          {costUncertain ? (
            <li className="flex gap-2">
              <AlertIcon width={16} height={16} className="mt-0.5 shrink-0 text-unknown-fg" />
              <span>{t('uncertain.costLine')}</span>
            </li>
          ) : null}
        </ul>
      )}

      {unverified.length ? (
        <details className="group/rejected mt-4 border-y border-line" open={data.verdict_downgraded || undefined}>
          <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-2 text-sm font-medium text-fg">
            {t('uncertain.rejectedTitle')}
            <ChevronIcon width={16} height={16} className="transition-transform group-open/rejected:rotate-180" />
          </summary>
          <div className="pb-4" data-testid="unverified-evidence">
            <p className="text-xs text-muted">{t('uncertain.rejectedBody')}</p>
            <ul className="mt-3 space-y-2">
              {unverified.map((it) => (
                <li key={it.id} className="border-s-2 border-contra-solid ps-3 text-sm">
                  <span className="block text-xs font-medium text-muted">{evidenceFieldLabel(t, it, billing)}</span>
                  <span dir="auto" className="mt-1 block break-words text-muted line-through decoration-contra-solid/70">
                    {it.evidence?.quote ? `“${it.evidence.quote}”` : t('evidence.noQuote')}
                  </span>
                  <span className="mt-1 block text-xs text-fg">
                    {t(`evidence.reasons.${it.evidence?.reason || 'quote_not_found_in_source'}`)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </details>
      ) : null}
    </Chapter>
  )
}
