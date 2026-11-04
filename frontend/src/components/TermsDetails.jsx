import { useLang } from '../i18n/LanguageContext.jsx'
import { factEvidenceId } from '../lib/evidence.js'
import { formatMoney, plural } from '../lib/format.js'
import { ChevronIcon, QuoteIcon } from './icons.jsx'

function NotStated() {
  const { t } = useLang()
  return (
    <span className="inline-flex items-center rounded-md border border-dashed border-line bg-subtle px-2 py-0.5 text-sm font-medium text-muted">
      {t('details.notStated')}
    </span>
  )
}

function QuoteButton({ evidenceId, fieldLabel, onShowEvidence }) {
  const { t } = useLang()
  if (!evidenceId) return null
  return (
    <button
      type="button"
      onClick={() => onShowEvidence(evidenceId)}
      aria-label={t('details.showQuoteAria', { field: fieldLabel })}
      className="inline-flex min-h-[28px] shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-link hover:bg-subtle"
    >
      <QuoteIcon width={14} height={14} />
      {t('details.showQuote')}
    </button>
  )
}

function Row({ label, children, evidenceId, onShowEvidence }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-4">
      <dt className="text-sm font-medium text-muted sm:w-48 sm:shrink-0">{label}</dt>
      <dd className="flex min-w-0 flex-1 flex-wrap items-start justify-between gap-2 text-[15px] font-medium text-fg">
        <span className="min-w-0 break-words">{children}</span>
        <QuoteButton evidenceId={evidenceId} fieldLabel={label} onShowEvidence={onShowEvidence} />
      </dd>
    </div>
  )
}

export default function TermsDetails({ data, onShowEvidence }) {
  const { t, lang } = useLang()
  const x = data.extracted_terms
  const verifiedFields = new Set(data.facts.filter((f) => f.evidence?.verified).map((f) => f.field))
  const ev = (field) => (verifiedFields.has(field) ? factEvidenceId(field) : null)
  const money = (v) => formatMoney(v, x.currency, lang)

  const intro =
    x.intro_price != null ? (
      <>
        <bdi>{money(x.intro_price)}</bdi>{' '}
        <span className="font-normal text-muted">
          {x.intro_periods
            ? t('details.introFor', { periods: plural(lang, 'period', x.intro_periods) })
            : `(${t('details.introDurationUnknown')})`}
        </span>
      </>
    ) : null

  // Without a stated billing period the price must not be presented as recurring.
  const periodKnown = x.billing_period !== 'unknown'
  const recurring =
    x.recurring_price != null ? (
      <>
        <bdi>{money(x.recurring_price)}</bdi>{' '}
        <span className="font-normal text-muted">
          {periodKnown ? t(`details.perPeriod.${x.billing_period}`) : `(${t('details.periodNotStated')})`}
        </span>
      </>
    ) : null

  const rows = [
    { key: 'trial', value: x.trial_days != null ? plural(lang, 'day', x.trial_days) : null, field: 'trial_days' },
    { key: 'intro', value: intro, field: 'intro_price' },
    { key: periodKnown || x.recurring_price == null ? 'recurring' : 'price', value: recurring, field: 'recurring_price' },
    {
      key: 'billing',
      value: x.billing_period !== 'unknown' ? t(`details.billingValues.${x.billing_period}`) : null,
      field: 'billing_period',
    },
    {
      key: 'renewal',
      value: x.auto_renewal !== 'not_stated' ? t(`details.renewalValues.${x.auto_renewal}`) : null,
      field: 'auto_renewal',
    },
    {
      key: 'cancellation',
      value: x.cancellation_requirement ? <bdi dir="auto">{x.cancellation_requirement}</bdi> : null,
      field: 'cancellation_requirement',
    },
  ]

  return (
    <section aria-labelledby="details-heading">
      <details className="group" data-testid="details-disclosure">
        <summary className="flex min-h-[60px] cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-5 sm:px-6">
          <span className="min-w-0">
            <h2 id="details-heading" className="text-base font-semibold text-fg">
              {t('details.heading')}
            </h2>
          </span>
          <ChevronIcon width={18} height={18} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>
      <dl className="px-5 pb-4 sm:px-6">
        {rows.map((r) => (
          <Row
            key={r.key}
            label={t(`details.${r.key}`)}
            evidenceId={r.value != null ? ev(r.field) : null}
            onShowEvidence={onShowEvidence}
          >
            {r.value != null ? r.value : <NotStated />}
          </Row>
        ))}
        <Row label={t('details.fees')}>
          {x.one_time_fees.length === 0 ? (
            <span className="font-medium text-muted">{t('details.noFees')}</span>
          ) : (
            <ul className="space-y-1.5">
              {x.one_time_fees.map((fee, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <span dir="auto" className="font-normal text-muted">
                    {fee.label}
                  </span>
                  <bdi>{money(fee.amount)}</bdi>
                  <QuoteButton
                    evidenceId={fee.evidence?.verified ? `fee-${i}` : null}
                    fieldLabel={t('fields.one_time_fee', { label: fee.label })}
                    onShowEvidence={onShowEvidence}
                  />
                </li>
              ))}
            </ul>
          )}
        </Row>
      </dl>
      </details>
    </section>
  )
}
