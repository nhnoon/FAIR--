import { useMemo } from 'react'
import { isEarlierPromptReplay } from '../api/client.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, missingKeyTerms } from '../lib/evidence.js'
import Chapter from './Chapter.jsx'
import { ProvenanceTag } from './Provenance.jsx'
import { AlertIcon, CheckIcon } from './icons.jsx'

function Row({ ok, children, testId }) {
  const Icon = ok ? CheckIcon : AlertIcon
  return (
    <li className="flex gap-2" data-testid={testId}>
      <Icon width={16} height={16} className={`mt-0.5 shrink-0 ${ok ? 'text-link' : 'text-unknown-fg'}`} />
      <span className="min-w-0">{children}</span>
    </li>
  )
}

function Tally({ kind, label, count }) {
  return (
    <div className="flex min-w-0 items-baseline gap-1.5 text-xs text-muted" data-testid={`audit-count-${kind}`}>
      <p className="font-semibold tabular-nums text-fg">{count}</p>
      <p>{label}</p>
      <span className="sr-only">
        <ProvenanceTag kind={kind} />
      </span>
    </div>
  )
}

// Reports what happened to this one answer. Every line is read from the response: it makes no claim about other answers.
export default function TrustAudit({ data }) {
  const { t } = useLang()
  const { verified, unverified } = useMemo(() => collectEvidence(data), [data])
  const overall = data.claims_summary.overall
  const answered = data.model_verdict || data.verdict
  const changed = answered !== overall
  const downgraded = data.claims.find((c) => c.downgraded && c.reason)
  const withheld = data.cost.withheld || []
  const horizons = data.decision?.continue_path?.horizons || []
  const hasTotal = horizons.some((h) => h.total != null && h.status !== 'unavailable')
  const assumed = new Set([...(data.decision?.continue_path?.assumption_codes || []), ...(data.decision?.cancel_path?.assumption_codes || [])]).size
  const unknown = data.claims.filter((c) => c.verdict === 'UNKNOWN').length + withheld.length + missingKeyTerms(data.extracted_terms).length

  return (
    <Chapter id="audit-heading" title={t('audit.title')} testId="trust-audit" attrs={{ 'data-changed': changed }}>
      <p className="text-sm text-muted">{t('audit.subtitle')}</p>

      {changed ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-2" data-testid="audit-changed">
          <div className="min-w-0 border-s-2 border-line ps-4">
            <p className="text-xs font-semibold text-muted">{t('audit.modelAnswered')}</p>
            {isEarlierPromptReplay(data.model) ? <p className="mt-0.5 text-xs font-semibold text-unknown-fg" data-testid="audit-historical">{t('audit.historical')}</p> : null}
            <p className="mt-1 text-base font-semibold text-fg">{t(`mirror.verdict.${answered}`)}</p>
          </div>
          <div className="min-w-0 border-s-2 border-fg ps-4">
            <p className="text-xs font-semibold text-muted">{t('audit.fairShows')}</p>
            <p className="mt-1 text-base font-semibold text-fg">{t(`mirror.verdict.${overall}`)}</p>
            {downgraded ? <p className="mt-1 text-sm text-fg">{t(`mirror.reasons.${downgraded.reason}`)}</p> : null}
          </div>
        </div>
      ) : null}

      <ul className="mt-4 space-y-2 text-sm text-fg">
        {changed ? null : <Row ok testId="audit-unchanged">{t('audit.unchanged', { verdict: t(`mirror.verdict.${overall}`) })}</Row>}
        <Row ok={!unverified.length} testId="audit-quotes">
          {t('audit.passages', { ok: verified.length, total: verified.length + unverified.length })}
        </Row>
        {withheld.length ? (
          <Row testId="audit-money">{t('audit.withheld')}</Row>
        ) : (
          <Row ok={hasTotal} testId="audit-money">{t(hasTotal ? 'audit.calculated' : 'audit.noTotal')}</Row>
        )}
      </ul>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-3">
        <Tally kind="terms" label={t('audit.verified')} count={verified.length} />
        <Tally kind="assumption" label={t('audit.assumed')} count={assumed} />
        <Tally kind="unknown" label={t('audit.unknown')} count={unknown} />
      </div>
    </Chapter>
  )
}
